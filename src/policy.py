"""Central policy decisions shared by later pipeline stages."""

from __future__ import annotations

from src.risk import HIGH_RISK_RULES
from src.schemas import RiskLevel, RiskResult, ScopeResult, ScopeStatus
from src.templates import TemplateMatch


def can_auto_reply(risk: RiskResult, scope: ScopeResult, has_relevant_context: bool) -> bool:
    return (
        risk.level == RiskLevel.LOW
        and scope.status != ScopeStatus.OUT_OF_SCOPE
        and has_relevant_context
    )


def can_use_template(match: TemplateMatch | None, risk: RiskResult) -> bool:
    return match is not None and match.is_allowed and risk.level == RiskLevel.LOW


def is_high_risk(risk: RiskResult) -> bool:
    return risk.level == RiskLevel.HIGH


def is_out_of_scope(scope: ScopeResult) -> bool:
    return scope.status == ScopeStatus.OUT_OF_SCOPE


def out_of_scope_message() -> str:
    return "Я могу помогать только с вопросами поддержки сервиса."


def clarification_message() -> str:
    return "Уточните, пожалуйста, что именно не работает в сервисе."


def operator_review_message() -> str:
    return "Передам обращение оператору для безопасной проверки."


def audit_unavailable_message() -> str:
    return "Передам обращение оператору, чтобы не потерять важные детали."
