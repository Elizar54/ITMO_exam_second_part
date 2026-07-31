"""Transparent high-risk rules for support tickets."""

from __future__ import annotations

from dataclasses import dataclass
import re

from src.schemas import RiskLevel, RiskResult


@dataclass(frozen=True)
class RiskRule:
    rule_id: str
    patterns: tuple[str, ...]
    reason: str


HIGH_RISK_RULES: tuple[RiskRule, ...] = (
    RiskRule(
        rule_id="account_takeover_or_fraud",
        patterns=("взломали", "чужой вход", "кто-то вошёл", "кто-то вошел", "украли аккаунт", "мошенник"),
        reason="Possible account takeover or fraud.",
    ),
    RiskRule(
        rule_id="unknown_financial_operation",
        patterns=("не узнаю списание", "списали без меня", "неизвестный платёж", "неизвестный платеж", "чарджбэк"),
        reason="Unknown financial operation.",
    ),
    RiskRule(
        rule_id="legal_claim",
        patterns=("подам в суд", "прокуратура", "роскомнадзор", "адвокат", "официальная претензия"),
        reason="Legal claim or regulator escalation.",
    ),
    RiskRule(
        rule_id="critical_account_action",
        patterns=("удалить все данные", "удалить аккаунт", "блокировка аккаунта"),
        reason="Critical account action.",
    ),
)


class RiskService:
    """Apply explicit risk rules to already redacted text."""

    def assess(self, redacted_text: str) -> RiskResult:
        matched_rules: list[str] = []
        reasons: list[str] = []

        for rule in HIGH_RISK_RULES:
            if any(self._contains_phrase(redacted_text, pattern) for pattern in rule.patterns):
                matched_rules.append(rule.rule_id)
                reasons.append(rule.reason)

        level = RiskLevel.HIGH if matched_rules else RiskLevel.LOW
        return RiskResult(level=level, reasons=reasons, matched_rules=matched_rules)

    @staticmethod
    def _contains_phrase(text: str, phrase: str) -> bool:
        pattern = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", re.IGNORECASE)
        return bool(pattern.search(text))
