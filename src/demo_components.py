"""Dependency-injected demo components for UI and CLI scenarios."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass

from src.answer_validator import AnswerValidator
from src.config import Settings
from src.exceptions import AuditUnavailableError, LLMTimeoutError
from src.llm_client import LLMRawResponse
from src.pii import PIIMaskingService
from src.pipeline import SupportPipeline
from src.risk import RiskService
from src.schemas import (
    AuditStorage,
    RetrievalResult,
    RetrievedChunk,
    ScopeResult,
    ScopeStatus,
)
from src.storage import AuditRepository
from src.templates import TemplateMatch


VALID_LLM_RESPONSE = json.dumps(
    {
        "answer": "Откройте экран входа и запустите восстановление пароля.",
        "citations": ["kb-password-reset"],
        "needs_operator": False,
    },
    ensure_ascii=False,
)
INVALID_LLM_RESPONSE = '{"answer": "broken"'


class DemoScopeGate:
    def classify(self, redacted_text: str) -> ScopeResult:
        text = redacted_text.lower()
        if any(word in text for word in ("погода", "пример", "фильм", "анекдот")):
            return ScopeResult(
                status=ScopeStatus.OUT_OF_SCOPE,
                positive_score=0.1,
                negative_score=0.9,
                margin=0.8,
            )
        if "ничего не работает" in text:
            return ScopeResult(
                status=ScopeStatus.UNCERTAIN,
                positive_score=0.45,
                negative_score=0.35,
                margin=0.1,
            )
        return ScopeResult(
            status=ScopeStatus.IN_SCOPE,
            positive_score=0.9,
            negative_score=0.1,
            margin=0.8,
        )


class DemoKnowledgeRetriever:
    def search(self, redacted_text: str) -> RetrievalResult:
        text = redacted_text.lower()
        if "ничего не работает" in text or "неизвестная" in text:
            return RetrievalResult(chunks=[], top_score=0.2, margin=0.0)
        if any(word in text for word in ("пароль", "письмо", "войти", "подпис")):
            chunk = RetrievedChunk(
                chunk_id="kb-password-reset",
                text="Для восстановления пароля откройте экран входа и следуйте ссылке из письма.",
                source="Восстановление пароля",
                score=0.92,
            )
            return RetrievalResult(chunks=[chunk], top_score=0.92, margin=0.5)
        return RetrievalResult(chunks=[], top_score=0.1, margin=0.0)


class DemoTemplateRetriever:
    def __init__(self, low_score: bool = False) -> None:
        self.low_score = low_score
        self.call_count = 0

    def search(self, redacted_text: str) -> TemplateMatch | None:
        self.call_count += 1
        text = redacted_text.lower()
        if not any(word in text for word in ("пароль", "письмо", "подпис", "войти", "блокиров", "вход")):
            return None
        if "блокиров" in text or "вход" in text:
            return TemplateMatch(
                template_id="tpl-login-temporary-lock",
                title="Временная блокировка входа",
                answer=(
                    "Если вход временно заблокирован, подождите 15 минут, "
                    "запросите новый код или ссылку восстановления и попробуйте снова."
                ),
                score=0.4 if self.low_score else 0.9,
                margin=0.2,
                auto_reply_allowed=True,
                risk="low",
                is_active=True,
            )
        return TemplateMatch(
            template_id="tpl-password-reset",
            title="Восстановление пароля",
            answer="Откройте экран входа, нажмите восстановление пароля и проверьте письмо.",
            score=0.4 if self.low_score else 0.9,
            margin=0.2,
            auto_reply_allowed=True,
            risk="low",
            is_active=True,
        )


class DemoLLMClient:
    def __init__(self, responses: Iterable[str | Exception]) -> None:
        self.responses = list(responses)
        self.call_count = 0

    def generate(
        self,
        redacted_text: str,
        retrieved_chunks: list[RetrievedChunk],
    ) -> LLMRawResponse:
        return self._next()

    def corrective_generate(
        self,
        redacted_text: str,
        retrieved_chunks: list[RetrievedChunk],
        validation_errors: list[str],
    ) -> LLMRawResponse:
        return self._next()

    def _next(self) -> LLMRawResponse:
        self.call_count += 1
        if not self.responses:
            response: str | Exception = VALID_LLM_RESPONSE
        else:
            response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return LLMRawResponse(
            raw_content=response,
            model="demo-mock",
            latency_seconds=0.01,
            token_usage={"prompt_tokens": 12, "completion_tokens": 8},
            estimated_cost_usd=0.0,
        )


class PrimaryAuditFailureRepository(AuditRepository):
    def _save_sqlite(self, record):
        raise OSError("simulated primary audit failure")


class AllAuditFailureRepository(AuditRepository):
    def save(self, record):
        raise AuditUnavailableError("simulated audit failure")


@dataclass(frozen=True)
class DemoMode:
    label: str
    llm_responses: tuple[str | Exception, ...]
    audit_mode: str = "normal"


DEMO_MODES: dict[str, DemoMode] = {
    "Normal / Mock success": DemoMode("Normal / Mock success", (VALID_LLM_RESPONSE,)),
    "Simulate LLM timeout": DemoMode("Simulate LLM timeout", (LLMTimeoutError("timeout"),)),
    "Simulate first invalid LLM response": DemoMode(
        "Simulate first invalid LLM response",
        (INVALID_LLM_RESPONSE, VALID_LLM_RESPONSE),
    ),
    "Simulate two invalid LLM responses": DemoMode(
        "Simulate two invalid LLM responses",
        (INVALID_LLM_RESPONSE, INVALID_LLM_RESPONSE),
    ),
    "Simulate primary audit failure": DemoMode(
        "Simulate primary audit failure",
        (VALID_LLM_RESPONSE,),
        audit_mode="primary_failure",
    ),
    "Simulate all audit failures": DemoMode(
        "Simulate all audit failures",
        (VALID_LLM_RESPONSE,),
        audit_mode="all_failure",
    ),
}


def build_demo_pipeline(mode_label: str, config: Settings) -> SupportPipeline:
    mode = DEMO_MODES[mode_label]
    if mode.audit_mode == "primary_failure":
        audit_repository = PrimaryAuditFailureRepository(config)
    elif mode.audit_mode == "all_failure":
        audit_repository = AllAuditFailureRepository(config)
    else:
        audit_repository = AuditRepository(config)

    return SupportPipeline(
        pii_service=PIIMaskingService(),
        scope_gate=DemoScopeGate(),
        risk_service=RiskService(),
        knowledge_retriever=DemoKnowledgeRetriever(),
        template_retriever=DemoTemplateRetriever(),
        llm_client=DemoLLMClient(mode.llm_responses),
        answer_validator=AnswerValidator(),
        audit_repository=audit_repository,
        config=config,
    )
