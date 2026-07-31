"""Knowledge-base retrieval over a Chroma collection."""

from __future__ import annotations

from typing import Any

from src.config import Settings, settings
from src.exceptions import RetrievalUnavailableError
from src.schemas import RetrievalResult, RetrievedChunk
from src.vector_store import iter_query_rows


def distance_to_similarity(distance: float) -> float:
    return max(0.0, min(1.0, 1.0 - distance))


class KnowledgeRetriever:
    def __init__(self, collection: Any, config: Settings = settings) -> None:
        self.collection = collection
        self.config = config

    def search(self, redacted_text: str) -> RetrievalResult:
        try:
            raw_result = self.collection.query(
                query_texts=[redacted_text],
                n_results=max(self.config.retrieval_top_k, 2),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raise RetrievalUnavailableError("Knowledge retrieval is unavailable.") from exc

        candidates: list[RetrievedChunk] = []
        for row_id, document, metadata, distance in iter_query_rows(raw_result):
            if not metadata.get("is_active", False):
                continue
            score = distance_to_similarity(distance)
            candidates.append(
                RetrievedChunk(
                    chunk_id=str(metadata.get("document_id") or row_id),
                    text=document,
                    source=str(metadata.get("title") or row_id),
                    score=score,
                    metadata=metadata,
                )
            )

        candidates.sort(key=lambda chunk: chunk.score, reverse=True)
        top_score = candidates[0].score if candidates else None
        second_score = candidates[1].score if len(candidates) > 1 else 0.0
        margin = (top_score - second_score) if top_score is not None else None

        if top_score is None or top_score < self.config.retrieval_score_threshold:
            return RetrievalResult(chunks=[], top_score=top_score, margin=margin)
        if margin is not None and margin < self.config.retrieval_margin_threshold:
            return RetrievalResult(chunks=[], top_score=top_score, margin=margin)

        return RetrievalResult(
            chunks=candidates[: self.config.retrieval_top_k],
            top_score=top_score,
            margin=margin,
        )
