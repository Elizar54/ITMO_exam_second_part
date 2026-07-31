"""Knowledge-base retrieval over a Chroma collection."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.config import Settings, settings
from src.exceptions import RetrievalUnavailableError
from src.schemas import RetrievalResult, RetrievedChunk
from src.vector_store import cosine_distance_to_similarity, iter_query_rows


class KnowledgeRetriever:
    def __init__(
        self,
        collection: Any,
        config: Settings = settings,
        data_path: Path = Path("data/knowledge_base.json"),
    ) -> None:
        self.collection = collection
        self.config = config
        self.data_path = data_path

    def search(self, redacted_text: str) -> RetrievalResult:
        vector_error: Exception | None = None
        try:
            raw_result = self.collection.query(
                query_texts=[redacted_text],
                n_results=max(self.config.retrieval_top_k, 2),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raw_result = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
            vector_error = exc

        candidates: list[RetrievedChunk] = []
        for row_id, document, metadata, distance in iter_query_rows(raw_result):
            if not metadata.get("is_active", False):
                continue
            score = cosine_distance_to_similarity(distance)
            candidates.append(
                RetrievedChunk(
                    chunk_id=str(metadata.get("document_id") or row_id),
                    text=document,
                    source=str(metadata.get("title") or row_id),
                    score=score,
                    metadata=metadata,
                )
            )

        candidates = self._merge_candidates(candidates, self._lexical_candidates(redacted_text))
        if vector_error is not None and not candidates:
            raise RetrievalUnavailableError("Knowledge retrieval is unavailable.") from vector_error

        candidates.sort(key=lambda chunk: chunk.score, reverse=True)
        top_score = candidates[0].score if candidates else None
        second_score = candidates[1].score if len(candidates) > 1 else 0.0
        margin = (top_score - second_score) if top_score is not None else None

        if top_score is None or top_score < self.config.retrieval_score_threshold:
            return RetrievalResult(chunks=[], top_score=top_score, margin=margin)

        return RetrievalResult(
            chunks=candidates[: self.config.retrieval_top_k],
            top_score=top_score,
            margin=margin,
        )

    def _lexical_candidates(self, redacted_text: str) -> list[RetrievedChunk]:
        if not self.data_path.exists():
            return []

        query_tokens = self._tokens(redacted_text)
        if not query_tokens:
            return []

        records = json.loads(self.data_path.read_text(encoding="utf-8"))
        candidates: list[RetrievedChunk] = []
        for record in records:
            if not record.get("is_active", False):
                continue
            document_text = f"{record['title']} {record['topic']} {record['text']}"
            document_tokens = self._tokens(document_text)
            if not document_tokens:
                continue

            matched = sum(
                1 for token in query_tokens if self._token_matches(token, document_tokens)
            )
            if matched == 0:
                continue

            score = matched / len(query_tokens)
            candidates.append(
                RetrievedChunk(
                    chunk_id=record["document_id"],
                    text=f"{record['title']}. {record['text']}",
                    source=record["title"],
                    score=score,
                    metadata={
                        "document_id": record["document_id"],
                        "title": record["title"],
                        "topic": record["topic"],
                        "auto_reply_allowed": record["auto_reply_allowed"],
                        "version": record["version"],
                        "is_active": record["is_active"],
                        "retrieval_mode": "lexical",
                    },
                )
            )
        return candidates

    @staticmethod
    def _merge_candidates(
        vector_candidates: list[RetrievedChunk],
        lexical_candidates: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        merged: dict[str, RetrievedChunk] = {}
        for candidate in [*vector_candidates, *lexical_candidates]:
            existing = merged.get(candidate.chunk_id)
            if existing is None or candidate.score > existing.score:
                merged[candidate.chunk_id] = candidate
        return list(merged.values())

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-zа-яё0-9]+", text.lower())
            if len(token) >= 4
        }

    @staticmethod
    def _token_matches(query_token: str, document_tokens: set[str]) -> bool:
        for document_token in document_tokens:
            prefix_length = min(6, len(query_token), len(document_token))
            if prefix_length >= 4 and query_token[:prefix_length] == document_token[:prefix_length]:
                return True
        return False
