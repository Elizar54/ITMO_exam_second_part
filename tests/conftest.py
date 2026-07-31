from __future__ import annotations

import pytest

from src.config import Settings
from src.schemas import RetrievalResult, RetrievedChunk, ScopeResult, ScopeStatus
from src.templates import TemplateMatch


@pytest.fixture()
def test_config(tmp_path):
    return Settings(
        primary_audit_path=tmp_path / "audit.db",
        backup_audit_path=tmp_path / "backup" / "audit_backup.jsonl",
        template_score_threshold=0.72,
        template_margin_threshold=0.05,
    )


@pytest.fixture()
def support_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="kb-password-reset",
        text="Восстановление пароля",
        source="kb",
        score=0.95,
    )


@pytest.fixture()
def in_scope() -> ScopeResult:
    return ScopeResult(
        status=ScopeStatus.IN_SCOPE,
        positive_score=0.9,
        negative_score=0.1,
        margin=0.8,
    )


@pytest.fixture()
def relevant_retrieval(support_chunk: RetrievedChunk) -> RetrievalResult:
    return RetrievalResult(chunks=[support_chunk], top_score=0.95, margin=0.5)


@pytest.fixture()
def reliable_template() -> TemplateMatch:
    return TemplateMatch(
        template_id="tpl-password-reset",
        title="Пароль",
        answer="Откройте экран входа и запустите восстановление пароля.",
        score=0.9,
        margin=0.4,
        auto_reply_allowed=True,
        risk="low",
        is_active=True,
    )
