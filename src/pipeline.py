"""Support ticket processing pipeline with resilient fallbacks."""

from __future__ import annotations

import json
from typing import Any

from src.answer_validator import AnswerValidator
from src.config import Settings, settings
from src.exceptions import (
    AuditUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
    RetrievalUnavailableError,
)
from src.logging_config import logger
from src.llm_client import LLMClient
from src.pii import PIIMaskingService
from src.policy import (
    audit_unavailable_message,
    clarification_message,
    operator_review_message,
    out_of_scope_message,
)
from src.risk import RiskService
from src.schemas import (
    AuditStorage,
    DecisionAction,
    DecisionRecord,
    FallbackReason,
    LLMAnswer,
    RetrievalResult,
    RiskLevel,
    RiskResult,
    ResponseSource,
    ScopeResult,
    ScopeStatus,
    TicketInput,
)
from src.templates import TemplateMatch


class SupportPipeline:
    def __init__(
        self,
        pii_service: PIIMaskingService,
        scope_gate: Any,
        risk_service: RiskService,
        knowledge_retriever: Any,
        template_retriever: Any,
        llm_client: LLMClient,
        answer_validator: AnswerValidator,
        audit_repository: Any,
        config: Settings = settings,
    ) -> None:
        self.pii_service = pii_service
        self.scope_gate = scope_gate
        self.risk_service = risk_service
        self.knowledge_retriever = knowledge_retriever
        self.template_retriever = template_retriever
        self.llm_client = llm_client
        self.answer_validator = answer_validator
        self.audit_repository = audit_repository
        self.config = config

    def process(self, ticket: TicketInput) -> DecisionRecord:
        try:
            return self._process(ticket)
        except Exception as exc:
            logger.exception("Unexpected internal error while processing ticket_id=%s", ticket.ticket_id)
            fallback = DecisionRecord(
                ticket_id=ticket.ticket_id,
                session_id=ticket.session_id,
                action=DecisionAction.OPERATOR_REVIEW,
                response_source=ResponseSource.OPERATOR,
                risk_level=RiskLevel.LOW,
                scope_status=ScopeStatus.UNCERTAIN,
                fallback_reason=FallbackReason.UNEXPECTED_INTERNAL_ERROR,
                answer=operator_review_message(),
                audit_storage=AuditStorage.UNAVAILABLE,
                degradation_events=["unexpected_internal_error"],
            )
            return self._save_or_block(fallback)

    def _process(self, ticket: TicketInput) -> DecisionRecord:
        privacy = self.pii_service.mask(ticket.text)
        scope = self.scope_gate.classify(privacy.redacted_text)

        if scope.status == ScopeStatus.OUT_OF_SCOPE:
            return self._save_or_block(
                self._record(
                    ticket=ticket,
                    scope=scope,
                    risk=RiskResult(level=RiskLevel.LOW),
                    action=DecisionAction.OUT_OF_SCOPE_RESPONSE,
                    response_source=ResponseSource.SYSTEM,
                    fallback_reason=FallbackReason.OUT_OF_SCOPE,
                    redacted_text=privacy.redacted_text,
                    answer=out_of_scope_message(),
                )
            )

        risk = self.risk_service.assess(privacy.redacted_text)
        if risk.level == RiskLevel.HIGH:
            return self._save_or_block(
                self._record(
                    ticket=ticket,
                    scope=scope,
                    risk=risk,
                    action=DecisionAction.OPERATOR_REVIEW,
                    response_source=ResponseSource.OPERATOR,
                    fallback_reason=FallbackReason.HIGH_RISK,
                    redacted_text=privacy.redacted_text,
                    answer=operator_review_message(),
                )
            )

        retrieval = self._retrieve(privacy.redacted_text)
        if not retrieval.chunks:
            return self._template_fallback(
                ticket=ticket,
                scope=scope,
                risk=risk,
                redacted_text=privacy.redacted_text,
                fallback_reason=(
                    FallbackReason.RETRIEVAL_UNAVAILABLE
                    if retrieval.unavailable
                    else FallbackReason.NO_RELEVANT_CONTEXT
                ),
            )

        return self._llm_path(ticket, scope, risk, privacy.redacted_text, retrieval)

    def _retrieve(self, redacted_text: str) -> RetrievalResult:
        try:
            return self.knowledge_retriever.search(redacted_text)
        except RetrievalUnavailableError:
            return RetrievalResult(unavailable=True)

    def _llm_path(
        self,
        ticket: TicketInput,
        scope: ScopeResult,
        risk: RiskResult,
        redacted_text: str,
        retrieval: RetrievalResult,
    ) -> DecisionRecord:
        try:
            first_response = self.llm_client.generate(redacted_text, retrieval.chunks)
        except LLMTimeoutError:
            return self._template_fallback(ticket, scope, risk, redacted_text, FallbackReason.LLM_TIMEOUT)
        except LLMRateLimitError:
            return self._template_fallback(ticket, scope, risk, redacted_text, FallbackReason.LLM_RATE_LIMIT)
        except LLMUnavailableError:
            return self._template_fallback(ticket, scope, risk, redacted_text, FallbackReason.LLM_UNAVAILABLE)

        first_validation = self.answer_validator.validate(
            first_response.raw_content,
            retrieval.chunks,
            attempt=1,
        )
        if first_validation.is_valid:
            answer = LLMAnswer.model_validate(json.loads(first_response.raw_content))
            return self._save_or_block(
                self._record(
                    ticket=ticket,
                    scope=scope,
                    risk=risk,
                    action=DecisionAction.AUTO_REPLY,
                    response_source=ResponseSource.RAG_LLM,
                    redacted_text=redacted_text,
                    answer=answer.answer,
                    citations=answer.citations,
                    llm_attempts=1,
                )
            )

        try:
            second_response = self.llm_client.corrective_generate(
                redacted_text,
                retrieval.chunks,
                first_validation.errors,
            )
        except (LLMTimeoutError, LLMRateLimitError, LLMUnavailableError):
            return self._save_or_block(
                self._record(
                    ticket=ticket,
                    scope=scope,
                    risk=risk,
                    action=DecisionAction.OPERATOR_REVIEW,
                    response_source=ResponseSource.OPERATOR,
                    fallback_reason=FallbackReason.LLM_RETRY_UNAVAILABLE,
                    redacted_text=redacted_text,
                    answer=operator_review_message(),
                    llm_attempts=2,
                    degradation_events=["first_llm_response_invalid"],
                )
            )

        second_validation = self.answer_validator.validate(
            second_response.raw_content,
            retrieval.chunks,
            attempt=2,
        )
        if second_validation.is_valid:
            answer = LLMAnswer.model_validate(json.loads(second_response.raw_content))
            return self._save_or_block(
                self._record(
                    ticket=ticket,
                    scope=scope,
                    risk=risk,
                    action=DecisionAction.AUTO_REPLY,
                    response_source=ResponseSource.RAG_LLM,
                    redacted_text=redacted_text,
                    answer=answer.answer,
                    citations=answer.citations,
                    llm_attempts=2,
                    degradation_events=["first_llm_response_invalid"],
                )
            )

        return self._save_or_block(
            self._record(
                ticket=ticket,
                scope=scope,
                risk=risk,
                action=DecisionAction.OPERATOR_REVIEW,
                response_source=ResponseSource.OPERATOR,
                fallback_reason=FallbackReason.LLM_VALIDATION_FAILED_TWICE,
                redacted_text=redacted_text,
                answer=operator_review_message(),
                llm_attempts=2,
                degradation_events=["first_llm_response_invalid", "second_llm_response_invalid"],
            )
        )

    def _template_fallback(
        self,
        ticket: TicketInput,
        scope: ScopeResult,
        risk: RiskResult,
        redacted_text: str,
        fallback_reason: FallbackReason,
    ) -> DecisionRecord:
        match = self.template_retriever.search(redacted_text)
        if self._template_is_reliable(match):
            return self._save_or_block(
                self._record(
                    ticket=ticket,
                    scope=scope,
                    risk=risk,
                    action=DecisionAction.TEMPLATE_RESPONSE,
                    response_source=ResponseSource.TEMPLATE,
                    fallback_reason=fallback_reason,
                    redacted_text=redacted_text,
                    answer=match.answer if match else None,
                )
            )

        if scope.status == ScopeStatus.UNCERTAIN:
            return self._save_or_block(
                self._record(
                    ticket=ticket,
                    scope=scope,
                    risk=risk,
                    action=DecisionAction.CLARIFICATION_REQUEST,
                    response_source=ResponseSource.SYSTEM,
                    fallback_reason=FallbackReason.SCOPE_UNCERTAIN,
                    redacted_text=redacted_text,
                    answer=clarification_message(),
                )
            )

        return self._save_or_block(
            self._record(
                ticket=ticket,
                scope=scope,
                risk=risk,
                action=DecisionAction.OPERATOR_REVIEW,
                response_source=ResponseSource.OPERATOR,
                fallback_reason=self._template_failure_reason(match),
                redacted_text=redacted_text,
                answer=operator_review_message(),
            )
        )

    def _template_is_reliable(self, match: TemplateMatch | None) -> bool:
        return (
            match is not None
            and match.is_allowed
            and match.score >= self.config.template_score_threshold
            and match.margin >= self.config.template_margin_threshold
        )

    def _template_failure_reason(self, match: TemplateMatch | None) -> FallbackReason:
        if match is None:
            return FallbackReason.TEMPLATE_NOT_FOUND
        if not match.is_active or not match.auto_reply_allowed or match.risk.lower() != "low":
            return FallbackReason.TEMPLATE_NOT_ALLOWED
        if match.score < self.config.template_score_threshold:
            return FallbackReason.TEMPLATE_LOW_SCORE
        return FallbackReason.TEMPLATE_AMBIGUOUS

    def _save_or_block(self, record: DecisionRecord) -> DecisionRecord:
        try:
            return self.audit_repository.save(record)
        except AuditUnavailableError:
            logger.exception("All audit storages unavailable for ticket_id=%s", record.ticket_id)
            return record.model_copy(
                update={
                    "action": DecisionAction.OPERATOR_REVIEW,
                    "response_source": ResponseSource.OPERATOR,
                    "fallback_reason": FallbackReason.ALL_AUDIT_STORAGES_UNAVAILABLE,
                    "answer": audit_unavailable_message(),
                    "audit_storage": AuditStorage.UNAVAILABLE,
                    "degradation_events": [
                        *record.degradation_events,
                        "all_audit_storages_unavailable",
                    ],
                }
            )

    def _record(
        self,
        ticket: TicketInput,
        scope: ScopeResult,
        risk: RiskResult,
        action: DecisionAction,
        response_source: ResponseSource,
        redacted_text: str | None = None,
        fallback_reason: FallbackReason | None = None,
        answer: str | None = None,
        citations: list[str] | None = None,
        llm_attempts: int = 0,
        degradation_events: list[str] | None = None,
    ) -> DecisionRecord:
        return DecisionRecord(
            ticket_id=ticket.ticket_id,
            session_id=ticket.session_id,
            action=action,
            response_source=response_source,
            risk_level=risk.level,
            scope_status=scope.status,
            fallback_reason=fallback_reason,
            redacted_text=redacted_text,
            answer=answer,
            citations=citations or [],
            llm_attempts=llm_attempts,
            degradation_events=degradation_events or [],
            audit_storage=AuditStorage.UNAVAILABLE,
        )
