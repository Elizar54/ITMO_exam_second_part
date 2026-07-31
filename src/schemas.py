"""Pydantic contracts for the support ticket processing system."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RiskLevel(StrEnum):
    LOW = "LOW"
    HIGH = "HIGH"


class ScopeStatus(StrEnum):
    IN_SCOPE = "IN_SCOPE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    UNCERTAIN = "UNCERTAIN"


class DecisionAction(StrEnum):
    AUTO_REPLY = "AUTO_REPLY"
    TEMPLATE_RESPONSE = "TEMPLATE_RESPONSE"
    OPERATOR_REVIEW = "OPERATOR_REVIEW"
    OUT_OF_SCOPE_RESPONSE = "OUT_OF_SCOPE_RESPONSE"
    CLARIFICATION_REQUEST = "CLARIFICATION_REQUEST"
    INPUT_REJECTED = "INPUT_REJECTED"


class ResponseSource(StrEnum):
    RAG_LLM = "RAG_LLM"
    TEMPLATE = "TEMPLATE"
    OPERATOR = "OPERATOR"
    SYSTEM = "SYSTEM"


class AuditStorage(StrEnum):
    PRIMARY_SQLITE = "PRIMARY_SQLITE"
    BACKUP_JSONL = "BACKUP_JSONL"
    UNAVAILABLE = "UNAVAILABLE"


class FallbackReason(StrEnum):
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    SCOPE_UNCERTAIN = "SCOPE_UNCERTAIN"
    HIGH_RISK = "HIGH_RISK"
    NO_RELEVANT_CONTEXT = "NO_RELEVANT_CONTEXT"
    RETRIEVAL_UNAVAILABLE = "RETRIEVAL_UNAVAILABLE"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_RATE_LIMIT = "LLM_RATE_LIMIT"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_RETRY_UNAVAILABLE = "LLM_RETRY_UNAVAILABLE"
    LLM_VALIDATION_FAILED_TWICE = "LLM_VALIDATION_FAILED_TWICE"
    TEMPLATE_NOT_FOUND = "TEMPLATE_NOT_FOUND"
    TEMPLATE_LOW_SCORE = "TEMPLATE_LOW_SCORE"
    TEMPLATE_AMBIGUOUS = "TEMPLATE_AMBIGUOUS"
    TEMPLATE_NOT_ALLOWED = "TEMPLATE_NOT_ALLOWED"
    ALL_AUDIT_STORAGES_UNAVAILABLE = "ALL_AUDIT_STORAGES_UNAVAILABLE"
    USER_NOT_HELPED = "USER_NOT_HELPED"
    UNEXPECTED_INTERNAL_ERROR = "UNEXPECTED_INTERNAL_ERROR"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TicketInput(StrictModel):
    ticket_id: UUID = Field(default_factory=uuid4)
    session_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    text: str = Field(min_length=3, max_length=5000)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("text", mode="before")
    @classmethod
    def trim_text(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value


class PrivacyResult(StrictModel):
    redacted_text: str = Field(min_length=0, max_length=5000)
    has_pii: bool
    detected_entities: list[str] = Field(default_factory=list)


class RiskResult(StrictModel):
    level: RiskLevel
    reasons: list[str] = Field(default_factory=list)
    matched_rules: list[str] = Field(default_factory=list)


class ScopeResult(StrictModel):
    status: ScopeStatus
    positive_score: float = Field(ge=0.0, le=1.0)
    negative_score: float = Field(ge=0.0, le=1.0)
    margin: float = Field(ge=0.0, le=1.0)
    reason: str | None = None


class RetrievedChunk(StrictModel):
    chunk_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(StrictModel):
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    top_score: float | None = Field(default=None, ge=0.0, le=1.0)
    margin: float | None = Field(default=None, ge=0.0, le=1.0)
    unavailable: bool = False


class LLMAnswer(StrictModel):
    answer: str = Field(min_length=1, max_length=3000)
    citations: list[str] = Field(default_factory=list)
    needs_operator: bool

    @model_validator(mode="after")
    def require_citations_for_final_answer(self) -> "LLMAnswer":
        if not self.needs_operator and not self.citations:
            raise ValueError("citations are required when needs_operator is False")
        return self


class ValidationResult(StrictModel):
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    attempt: int = Field(default=1, ge=1)


class DecisionRecord(StrictModel):
    event_id: UUID = Field(default_factory=uuid4)
    decision_id: UUID = Field(default_factory=uuid4)
    ticket_id: UUID
    session_id: str = Field(min_length=1)
    action: DecisionAction
    response_source: ResponseSource
    risk_level: RiskLevel
    scope_status: ScopeStatus
    fallback_reason: FallbackReason | None = None
    redacted_text: str | None = Field(default=None, max_length=5000)
    pii_detected: bool = False
    pii_types: list[str] = Field(default_factory=list)
    scope_positive_score: float | None = Field(default=None, ge=0.0, le=1.0)
    scope_negative_score: float | None = Field(default=None, ge=0.0, le=1.0)
    scope_margin: float | None = Field(default=None, ge=0.0, le=1.0)
    matched_risk_rules: list[str] = Field(default_factory=list)
    retrieval_top_score: float | None = Field(default=None, ge=0.0, le=1.0)
    retrieval_margin: float | None = Field(default=None, ge=0.0, le=1.0)
    retrieved_document_ids: list[str] = Field(default_factory=list)
    answer: str | None = Field(default=None, max_length=3000)
    citations: list[str] = Field(default_factory=list)
    template_id: str | None = None
    llm_used: bool = False
    llm_attempts: int = Field(default=0, ge=0)
    llm_latency_seconds: float | None = Field(default=None, ge=0.0)
    token_usage: dict[str, int] = Field(default_factory=dict)
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)
    processing_latency_seconds: float | None = Field(default=None, ge=0.0)
    resolved_without_operator: bool | None = None
    degradation_events: list[str] = Field(default_factory=list)
    audit_storage: AuditStorage
    created_at: datetime = Field(default_factory=utc_now)
