from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.answer_validator import AnswerValidator
from src.config import Settings
from src.exceptions import AuditUnavailableError
from src.pipeline import SupportPipeline
from src.pii import PIIMaskingService
from src.risk import RiskService
from src.schemas import (
    AuditStorage,
    DecisionAction,
    FallbackReason,
    RetrievalResult,
    RiskLevel,
    ScopeResult,
    ScopeStatus,
    TicketInput,
)
from src.templates import TemplateMatch
from tests.fakes import FakeLLMClient, INVALID_JSON, VALID_RESPONSE


class FakeScopeGate:
    def __init__(self, result: ScopeResult) -> None:
        self.result = result

    def classify(self, redacted_text: str) -> ScopeResult:
        return self.result


class FakeKnowledgeRetriever:
    def __init__(self, result: RetrievalResult) -> None:
        self.result = result
        self.call_count = 0

    def search(self, redacted_text: str) -> RetrievalResult:
        self.call_count += 1
        return self.result


class FakeTemplateRetriever:
    def __init__(self, match: TemplateMatch | None) -> None:
        self.match = match
        self.call_count = 0

    def search(self, redacted_text: str) -> TemplateMatch | None:
        self.call_count += 1
        return self.match


class FakeAuditRepository:
    def __init__(self, storage: AuditStorage = AuditStorage.PRIMARY_SQLITE, fail: bool = False) -> None:
        self.storage = storage
        self.fail = fail
        self.records = []

    def save(self, record):
        if self.fail:
            raise AuditUnavailableError("audit down")
        saved = record.model_copy(update={"audit_storage": self.storage})
        if self.storage == AuditStorage.BACKUP_JSONL:
            saved = saved.model_copy(
                update={"degradation_events": [*saved.degradation_events, "primary_audit_unavailable"]}
            )
        self.records.append(saved)
        return saved


@dataclass
class PipelineParts:
    pipeline: SupportPipeline
    llm: FakeLLMClient
    template: FakeTemplateRetriever
    audit: FakeAuditRepository


def ticket(text: str = "Не могу восстановить пароль") -> TicketInput:
    return TicketInput(session_id="session-1", channel="web", text=text)


def make_scope(status: ScopeStatus) -> ScopeResult:
    return ScopeResult(status=status, positive_score=0.9, negative_score=0.1, margin=0.8)


def make_pipeline(
    config: Settings,
    scope: ScopeResult,
    retrieval: RetrievalResult,
    template_match: TemplateMatch | None,
    llm: FakeLLMClient | None = None,
    audit: FakeAuditRepository | None = None,
) -> PipelineParts:
    llm = llm or FakeLLMClient.valid()
    template = FakeTemplateRetriever(template_match)
    audit = audit or FakeAuditRepository()
    pipeline = SupportPipeline(
        pii_service=PIIMaskingService(),
        scope_gate=FakeScopeGate(scope),
        risk_service=RiskService(),
        knowledge_retriever=FakeKnowledgeRetriever(retrieval),
        template_retriever=template,
        llm_client=llm,
        answer_validator=AnswerValidator(),
        audit_repository=audit,
        config=config,
    )
    return PipelineParts(pipeline=pipeline, llm=llm, template=template, audit=audit)


def test_pii_does_not_cause_escalation(test_config, in_scope, relevant_retrieval, reliable_template) -> None:
    parts = make_pipeline(test_config, in_scope, relevant_retrieval, reliable_template)

    result = parts.pipeline.process(ticket("Не приходит письмо на user@example.com"))

    assert result.action == DecisionAction.AUTO_REPLY
    assert result.redacted_text is not None
    assert "user@example.com" not in result.redacted_text


def test_llm_receives_only_redacted_text(test_config, in_scope, relevant_retrieval, reliable_template) -> None:
    parts = make_pipeline(test_config, in_scope, relevant_retrieval, reliable_template)

    parts.pipeline.process(ticket("Не приходит письмо на user@example.com"))

    assert "[EMAIL_1]" in str(parts.llm.safe_calls)
    assert "user@example.com" not in str(parts.llm.safe_calls)


def test_high_risk_never_calls_llm(test_config, in_scope, relevant_retrieval, reliable_template) -> None:
    parts = make_pipeline(test_config, in_scope, relevant_retrieval, reliable_template)

    result = parts.pipeline.process(ticket("Кажется, был чужой вход"))

    assert result.action == DecisionAction.OPERATOR_REVIEW
    assert result.fallback_reason == FallbackReason.HIGH_RISK
    assert parts.llm.call_count == 0


def test_out_of_scope_does_not_call_llm_or_operator(test_config, relevant_retrieval, reliable_template) -> None:
    parts = make_pipeline(
        test_config,
        make_scope(ScopeStatus.OUT_OF_SCOPE),
        relevant_retrieval,
        reliable_template,
    )

    result = parts.pipeline.process(ticket("Какая погода?"))

    assert result.action == DecisionAction.OUT_OF_SCOPE_RESPONSE
    assert parts.llm.call_count == 0


def test_uncertain_without_context_asks_clarification(test_config, reliable_template) -> None:
    parts = make_pipeline(
        test_config,
        make_scope(ScopeStatus.UNCERTAIN),
        RetrievalResult(chunks=[], top_score=0.1, margin=0.0),
        None,
    )

    result = parts.pipeline.process(ticket("У меня ничего не работает"))

    assert result.action == DecisionAction.CLARIFICATION_REQUEST


def test_happy_path_returns_auto_reply(test_config, in_scope, relevant_retrieval, reliable_template) -> None:
    result = make_pipeline(test_config, in_scope, relevant_retrieval, reliable_template).pipeline.process(ticket())

    assert result.action == DecisionAction.AUTO_REPLY
    assert result.llm_attempts == 1


def test_llm_timeout_uses_template(test_config, in_scope, relevant_retrieval, reliable_template) -> None:
    parts = make_pipeline(
        test_config,
        in_scope,
        relevant_retrieval,
        reliable_template,
        llm=FakeLLMClient.timeout(),
    )

    result = parts.pipeline.process(ticket())

    assert result.action == DecisionAction.TEMPLATE_RESPONSE
    assert result.fallback_reason == FallbackReason.LLM_TIMEOUT


def test_low_template_score_sends_operator(test_config, in_scope) -> None:
    low_template = TemplateMatch(
        template_id="tpl-low",
        title="low",
        answer="low",
        score=0.1,
        margin=0.1,
        auto_reply_allowed=True,
        risk="low",
        is_active=True,
    )
    parts = make_pipeline(test_config, in_scope, RetrievalResult(chunks=[]), low_template)

    result = parts.pipeline.process(ticket())

    assert result.action == DecisionAction.OPERATOR_REVIEW
    assert result.fallback_reason == FallbackReason.TEMPLATE_LOW_SCORE


def test_first_invalid_response_triggers_one_retry(
    test_config,
    in_scope,
    relevant_retrieval,
    reliable_template,
) -> None:
    parts = make_pipeline(
        test_config,
        in_scope,
        relevant_retrieval,
        reliable_template,
        llm=FakeLLMClient([INVALID_JSON, VALID_RESPONSE]),
    )

    result = parts.pipeline.process(ticket())

    assert parts.llm.call_count == 2
    assert result.action == DecisionAction.AUTO_REPLY
    assert result.llm_attempts == 2
    assert "first_llm_response_invalid" in result.degradation_events


def test_two_invalid_responses_send_operator(test_config, in_scope, relevant_retrieval, reliable_template) -> None:
    parts = make_pipeline(
        test_config,
        in_scope,
        relevant_retrieval,
        reliable_template,
        llm=FakeLLMClient([INVALID_JSON, INVALID_JSON]),
    )

    result = parts.pipeline.process(ticket())

    assert result.action == DecisionAction.OPERATOR_REVIEW
    assert result.fallback_reason == FallbackReason.LLM_VALIDATION_FAILED_TWICE


def test_after_two_invalid_responses_template_not_called(
    test_config,
    in_scope,
    relevant_retrieval,
    reliable_template,
) -> None:
    parts = make_pipeline(
        test_config,
        in_scope,
        relevant_retrieval,
        reliable_template,
        llm=FakeLLMClient([INVALID_JSON, INVALID_JSON]),
    )

    parts.pipeline.process(ticket())

    assert parts.template.call_count == 0


def test_primary_audit_failure_uses_jsonl(test_config, in_scope, relevant_retrieval, reliable_template) -> None:
    parts = make_pipeline(
        test_config,
        in_scope,
        relevant_retrieval,
        reliable_template,
        audit=FakeAuditRepository(storage=AuditStorage.BACKUP_JSONL),
    )

    result = parts.pipeline.process(ticket())

    assert result.audit_storage == AuditStorage.BACKUP_JSONL
    assert "primary_audit_unavailable" in result.degradation_events


def test_successful_jsonl_does_not_block_auto_reply(test_config, in_scope, relevant_retrieval, reliable_template) -> None:
    parts = make_pipeline(
        test_config,
        in_scope,
        relevant_retrieval,
        reliable_template,
        audit=FakeAuditRepository(storage=AuditStorage.BACKUP_JSONL),
    )

    result = parts.pipeline.process(ticket())

    assert result.action == DecisionAction.AUTO_REPLY


def test_both_audit_failures_block_auto_reply(test_config, in_scope, relevant_retrieval, reliable_template) -> None:
    parts = make_pipeline(
        test_config,
        in_scope,
        relevant_retrieval,
        reliable_template,
        audit=FakeAuditRepository(fail=True),
    )

    result = parts.pipeline.process(ticket())

    assert result.action == DecisionAction.OPERATOR_REVIEW
    assert result.audit_storage == AuditStorage.UNAVAILABLE
    assert result.fallback_reason == FallbackReason.ALL_AUDIT_STORAGES_UNAVAILABLE


def test_raw_pii_absent_from_audit_payload(test_config, in_scope, relevant_retrieval, reliable_template) -> None:
    parts = make_pipeline(test_config, in_scope, relevant_retrieval, reliable_template)

    parts.pipeline.process(ticket("Не приходит письмо на user@example.com"))

    assert "user@example.com" not in str(parts.audit.records)


def test_unexpected_internal_error_has_separate_reason(
    test_config,
    in_scope,
    relevant_retrieval,
    reliable_template,
) -> None:
    class BrokenPIIService:
        def mask(self, text: str):
            raise RuntimeError("boom")

    parts = make_pipeline(test_config, in_scope, relevant_retrieval, reliable_template)
    parts.pipeline.pii_service = BrokenPIIService()

    result = parts.pipeline.process(ticket())

    assert result.action == DecisionAction.OPERATOR_REVIEW
    assert result.fallback_reason == FallbackReason.UNEXPECTED_INTERNAL_ERROR
