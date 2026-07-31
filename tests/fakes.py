from __future__ import annotations

from collections.abc import Iterable

from src.exceptions import LLMRateLimitError, LLMTimeoutError
from src.llm_client import LLMRawResponse
from src.schemas import RetrievedChunk


VALID_RESPONSE = (
    '{"answer": "Откройте экран входа и запустите восстановление пароля.", '
    '"citations": ["kb-password-reset"], "needs_operator": false}'
)
INVALID_JSON = '{"answer": "broken"'
FAKE_CITATION = (
    '{"answer": "Откройте экран входа.", '
    '"citations": ["kb-missing"], "needs_operator": false}'
)
FORBIDDEN_CLAIM = (
    '{"answer": "Я изменила email в аккаунте.", '
    '"citations": ["kb-password-reset"], "needs_operator": false}'
)


class FakeLLMClient:
    def __init__(self, responses: Iterable[str | Exception]) -> None:
        self.responses = list(responses)
        self.call_count = 0
        self.safe_calls: list[dict[str, object]] = []

    def generate(
        self,
        redacted_text: str,
        retrieved_chunks: list[RetrievedChunk],
    ) -> LLMRawResponse:
        return self._next(redacted_text, retrieved_chunks)

    def corrective_generate(
        self,
        redacted_text: str,
        retrieved_chunks: list[RetrievedChunk],
        validation_errors: list[str],
    ) -> LLMRawResponse:
        self.safe_calls.append({"validation_errors": list(validation_errors)})
        return self._next(redacted_text, retrieved_chunks)

    def _next(self, redacted_text: str, retrieved_chunks: list[RetrievedChunk]) -> LLMRawResponse:
        self.call_count += 1
        self.safe_calls.append(
            {
                "redacted_text": redacted_text,
                "chunk_ids": [chunk.chunk_id for chunk in retrieved_chunks],
            }
        )
        if not self.responses:
            raise RuntimeError("FakeLLMClient response sequence is exhausted.")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return LLMRawResponse(
            raw_content=response,
            model="fake-llm",
            latency_seconds=0.01,
            token_usage={"prompt_tokens": 10, "completion_tokens": 10},
        )

    @classmethod
    def valid(cls) -> "FakeLLMClient":
        return cls([VALID_RESPONSE])

    @classmethod
    def invalid_json(cls) -> "FakeLLMClient":
        return cls([INVALID_JSON])

    @classmethod
    def fake_citation(cls) -> "FakeLLMClient":
        return cls([FAKE_CITATION])

    @classmethod
    def forbidden_claim(cls) -> "FakeLLMClient":
        return cls([FORBIDDEN_CLAIM])

    @classmethod
    def timeout(cls) -> "FakeLLMClient":
        return cls([LLMTimeoutError("timeout")])

    @classmethod
    def rate_limit(cls) -> "FakeLLMClient":
        return cls([LLMRateLimitError("rate limit")])
