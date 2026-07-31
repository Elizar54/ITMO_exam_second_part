"""PII masking based on local regular expressions."""

from __future__ import annotations

import re
from collections.abc import Callable

from src.schemas import PrivacyResult


class PIIMaskingService:
    """Detect and replace sensitive values without storing raw mappings."""

    _EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
    _PHONE_RE = re.compile(r"(?<!\d)(?:\+7|7|8)[\s\-()]*(?:\d[\s\-()]*){10}(?!\d)")
    _CARD_RE = re.compile(r"(?<!\d)\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}(?!\d)")
    _IPV4_RE = re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}"
        r"(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
    )
    _BEARER_TOKEN_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
    _API_TOKEN_RE = re.compile(
        r"\b(?:api[_\s-]?token|token)\s*[:=]\s*[A-Za-z0-9._~+/=-]{8,}\b",
        re.IGNORECASE,
    )
    _OTP_BEFORE_RE = re.compile(
        r"(?i)\b(?:код|otp|подтверждение)\b(?P<context>[^\d]{0,24})(?P<otp>\d{4,8})\b"
    )
    _OTP_AFTER_RE = re.compile(
        r"(?i)\b(?P<otp>\d{4,8})(?P<context>[^\d]{0,24})\b(?:код|otp|подтверждение)\b"
    )

    def mask(self, text: str) -> PrivacyResult:
        counters: dict[str, int] = {}
        detected_entities: list[str] = []
        redacted_text = text

        def placeholder(entity_type: str) -> str:
            counters[entity_type] = counters.get(entity_type, 0) + 1
            value = f"[{entity_type}_{counters[entity_type]}]"
            detected_entities.append(value)
            return value

        redacted_text = self._replace(redacted_text, self._BEARER_TOKEN_RE, "TOKEN", placeholder)
        redacted_text = self._replace(redacted_text, self._API_TOKEN_RE, "TOKEN", placeholder)
        redacted_text = self._replace(redacted_text, self._EMAIL_RE, "EMAIL", placeholder)
        redacted_text = self._replace(redacted_text, self._CARD_RE, "CARD", placeholder)
        redacted_text = self._replace(redacted_text, self._PHONE_RE, "PHONE", placeholder)
        redacted_text = self._replace(redacted_text, self._IPV4_RE, "IP_ADDRESS", placeholder)
        redacted_text = self._replace_otp(redacted_text, self._OTP_BEFORE_RE, placeholder)
        redacted_text = self._replace_otp(redacted_text, self._OTP_AFTER_RE, placeholder)

        return PrivacyResult(
            redacted_text=redacted_text,
            has_pii=bool(detected_entities),
            detected_entities=detected_entities,
        )

    @staticmethod
    def _replace(
        text: str,
        pattern: re.Pattern[str],
        entity_type: str,
        placeholder: Callable[[str], str],
    ) -> str:
        return pattern.sub(lambda _: placeholder(entity_type), text)

    @staticmethod
    def _replace_otp(
        text: str,
        pattern: re.Pattern[str],
        placeholder: Callable[[str], str],
    ) -> str:
        result: list[str] = []
        cursor = 0
        for match in pattern.finditer(text):
            start, end = match.span("otp")
            result.append(text[cursor:start])
            result.append(placeholder("OTP_CODE"))
            cursor = end
        result.append(text[cursor:])
        return "".join(result)


def mask_pii(text: str) -> PrivacyResult:
    """Convenience wrapper for one-off masking."""

    return PIIMaskingService().mask(text)
