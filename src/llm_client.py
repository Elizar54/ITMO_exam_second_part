"""LLM client contract and OpenRouter implementation."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from src.config import Settings, settings
from src.exceptions import LLMRateLimitError, LLMTimeoutError, LLMUnavailableError
from src.schemas import RetrievedChunk


@dataclass(frozen=True)
class LLMRawResponse:
    raw_content: str
    model: str
    latency_seconds: float
    token_usage: dict[str, int] = field(default_factory=dict)
    estimated_cost_usd: float = 0.0


class LLMClient(Protocol):
    def generate(
        self,
        redacted_text: str,
        retrieved_chunks: list[RetrievedChunk],
    ) -> LLMRawResponse:
        """Generate an answer from redacted user text and retrieved context."""

    def corrective_generate(
        self,
        redacted_text: str,
        retrieved_chunks: list[RetrievedChunk],
        validation_errors: list[str],
    ) -> LLMRawResponse:
        """Generate a corrected answer after validation feedback."""


class OpenRouterClient:
    """OpenRouter chat-completions client.

    The client sends only redacted user text and retrieved KB chunks. It does
    not log prompts, raw responses, or credentials.
    """

    def __init__(
        self,
        config: Settings = settings,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self.http_client = http_client
        self.mock_mode = not bool(config.openrouter_api_key)

    @property
    def mode_label(self) -> str:
        return "mock mode" if self.mock_mode else "real OpenRouter mode"

    def generate(
        self,
        redacted_text: str,
        retrieved_chunks: list[RetrievedChunk],
    ) -> LLMRawResponse:
        return self._request(redacted_text, retrieved_chunks, validation_errors=None)

    def corrective_generate(
        self,
        redacted_text: str,
        retrieved_chunks: list[RetrievedChunk],
        validation_errors: list[str],
    ) -> LLMRawResponse:
        return self._request(redacted_text, retrieved_chunks, validation_errors=validation_errors)

    def _request(
        self,
        redacted_text: str,
        retrieved_chunks: list[RetrievedChunk],
        validation_errors: list[str] | None,
    ) -> LLMRawResponse:
        if self.mock_mode:
            return self._mock_response(retrieved_chunks)

        started = time.perf_counter()
        client = self.http_client or httpx.Client(timeout=self.config.openrouter_timeout_seconds)
        close_client = self.http_client is None
        try:
            response = client.post(
                self.config.openrouter_endpoint,
                headers=self._headers(),
                json=self._payload(redacted_text, retrieved_chunks, validation_errors),
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("OpenRouter request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 429:
                raise LLMRateLimitError("OpenRouter rate limit reached.") from exc
            if status_code >= 500:
                raise LLMUnavailableError("OpenRouter server error.") from exc
            raise LLMUnavailableError(f"OpenRouter returned HTTP {status_code}.") from exc
        except (httpx.NetworkError, httpx.TransportError) as exc:
            raise LLMUnavailableError("OpenRouter network error.") from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMUnavailableError("OpenRouter response format is invalid.") from exc
        finally:
            if close_client:
                client.close()

        latency = time.perf_counter() - started
        choice = payload["choices"][0]
        message = choice["message"]
        raw_content = message["content"]
        usage = payload.get("usage") or {}
        token_usage = {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
        }
        return LLMRawResponse(
            raw_content=raw_content,
            model=str(payload.get("model") or self.config.openrouter_model),
            latency_seconds=latency,
            token_usage=token_usage,
            estimated_cost_usd=self._estimated_cost(token_usage),
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.openrouter_api_key}",
            "Content-Type": "application/json",
        }

    def _payload(
        self,
        redacted_text: str,
        retrieved_chunks: list[RetrievedChunk],
        validation_errors: list[str] | None,
    ) -> dict[str, Any]:
        allowed_ids = [chunk.chunk_id for chunk in retrieved_chunks]
        system_prompt = (
            "You are a support assistant. Return only JSON matching this schema: "
            '{"answer": "string", "citations": ["document_id"], "needs_operator": boolean}. '
            "Use only provided KB chunks. Do not ask for passwords, OTP codes, or full card numbers."
        )
        user_payload: dict[str, Any] = {
            "redacted_text": redacted_text,
            "allowed_document_ids": allowed_ids,
            "retrieved_chunks": [
                {
                    "document_id": chunk.chunk_id,
                    "source": chunk.source,
                    "text": chunk.text,
                }
                for chunk in retrieved_chunks
            ],
        }
        if validation_errors is not None:
            user_payload["validation_errors"] = validation_errors
            user_payload["instruction"] = "Correct the previous answer using the same context."

        return {
            "model": self.config.openrouter_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "temperature": 0,
            "max_tokens": self.config.openrouter_max_tokens,
            "response_format": {"type": "json_object"},
        }

    def _estimated_cost(self, token_usage: dict[str, int]) -> float:
        if (
            self.config.openrouter_prompt_cost_per_1k <= 0
            and self.config.openrouter_completion_cost_per_1k <= 0
        ):
            return 0.0
        prompt_cost = (
            token_usage.get("prompt_tokens", 0)
            / 1000
            * self.config.openrouter_prompt_cost_per_1k
        )
        completion_cost = (
            token_usage.get("completion_tokens", 0)
            / 1000
            * self.config.openrouter_completion_cost_per_1k
        )
        return round(prompt_cost + completion_cost, 8)

    @staticmethod
    def _mock_response(retrieved_chunks: list[RetrievedChunk]) -> LLMRawResponse:
        citations = [retrieved_chunks[0].chunk_id] if retrieved_chunks else []
        return LLMRawResponse(
            raw_content=json.dumps(
                {
                    "answer": "Mock mode is active because OPENROUTER_API_KEY is not configured.",
                    "citations": citations,
                    "needs_operator": not bool(citations),
                }
            ),
            model="mock-openrouter",
            latency_seconds=0.0,
            token_usage={"prompt_tokens": 0, "completion_tokens": 0},
            estimated_cost_usd=0.0,
        )
