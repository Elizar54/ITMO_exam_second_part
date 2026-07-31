"""Service scope gate based on positive and negative examples."""

from __future__ import annotations

from typing import Any

from src.config import Settings, settings
from src.schemas import ScopeResult, ScopeStatus
from src.vector_store import cosine_distance_to_similarity, iter_query_rows


class ScopeGate:
    def __init__(self, collection: Any, config: Settings = settings) -> None:
        self.collection = collection
        self.config = config

    def classify(self, redacted_text: str) -> ScopeResult:
        raw_result = self.collection.query(
            query_texts=[redacted_text],
            n_results=8,
            include=["documents", "metadatas", "distances"],
        )

        positive_score = 0.0
        negative_score = 0.0
        for _, _, metadata, distance in iter_query_rows(raw_result):
            if not metadata.get("is_active", False):
                continue
            score = cosine_distance_to_similarity(distance)
            if metadata.get("label") == "positive":
                positive_score = max(positive_score, score)
            if metadata.get("label") == "negative":
                negative_score = max(negative_score, score)

        margin = abs(positive_score - negative_score)
        if (
            negative_score >= self.config.scope_negative_threshold
            and negative_score > positive_score
            and margin >= self.config.scope_margin_threshold
        ):
            return ScopeResult(
                status=ScopeStatus.OUT_OF_SCOPE,
                positive_score=positive_score,
                negative_score=negative_score,
                margin=margin,
                reason="Negative service-scope examples are stronger.",
            )
        if (
            positive_score >= self.config.scope_positive_threshold
            and positive_score > negative_score
            and margin >= self.config.scope_margin_threshold
        ):
            return ScopeResult(
                status=ScopeStatus.IN_SCOPE,
                positive_score=positive_score,
                negative_score=negative_score,
                margin=margin,
                reason="Positive service-scope examples are stronger.",
            )
        return ScopeResult(
            status=ScopeStatus.UNCERTAIN,
            positive_score=positive_score,
            negative_score=negative_score,
            margin=margin,
            reason="Scope confidence is insufficient.",
        )
