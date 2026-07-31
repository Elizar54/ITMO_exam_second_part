"""Response template search."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.config import Settings, settings
from src.schemas import RiskLevel
from src.vector_store import iter_query_rows


@dataclass(frozen=True)
class TemplateMatch:
    template_id: str
    title: str
    answer: str
    score: float
    margin: float
    auto_reply_allowed: bool
    risk: str
    is_active: bool

    @property
    def is_allowed(self) -> bool:
        return self.auto_reply_allowed and self.risk.lower() == RiskLevel.LOW.value.lower() and self.is_active


class TemplateRetriever:
    def __init__(self, collection: Any, config: Settings = settings) -> None:
        self.collection = collection
        self.config = config

    def search(self, redacted_text: str) -> TemplateMatch | None:
        raw_result = self.collection.query(
            query_texts=[redacted_text],
            n_results=10,
            include=["documents", "metadatas", "distances"],
        )

        best_by_template: dict[str, TemplateMatch] = {}
        for _, _, metadata, distance in iter_query_rows(raw_result):
            template_id = str(metadata.get("template_id", ""))
            if not template_id:
                continue
            score = max(0.0, min(1.0, 1.0 - distance))
            current = best_by_template.get(template_id)
            match = TemplateMatch(
                template_id=template_id,
                title=str(metadata.get("title", "")),
                answer=str(metadata.get("answer", "")),
                score=score,
                margin=0.0,
                auto_reply_allowed=bool(metadata.get("auto_reply_allowed", False)),
                risk=str(metadata.get("risk", "")),
                is_active=bool(metadata.get("is_active", False)),
            )
            if current is None or match.score > current.score:
                best_by_template[template_id] = match

        matches = sorted(best_by_template.values(), key=lambda item: item.score, reverse=True)
        if not matches:
            return None

        top = matches[0]
        second_score = matches[1].score if len(matches) > 1 else 0.0
        margin = top.score - second_score
        top = TemplateMatch(**{**top.__dict__, "margin": margin})

        if top.score < self.config.template_score_threshold:
            return top
        if margin < self.config.template_margin_threshold:
            return top
        if not top.is_allowed:
            return top
        return top
