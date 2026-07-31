"""LLM client contract for later provider integrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from src.schemas import RetrievedChunk


@dataclass(frozen=True)
class LLMRawResponse:
    raw_content: str
    model: str
    latency_seconds: float
    token_usage: dict[str, int] = field(default_factory=dict)


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
