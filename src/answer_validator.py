"""Validation for structured LLM answers."""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from src.pii import PIIMaskingService
from src.schemas import LLMAnswer, RetrievedChunk, ValidationResult


class AnswerValidator:
    def __init__(self, pii_service: PIIMaskingService | None = None) -> None:
        self.pii_service = pii_service or PIIMaskingService()

    def validate(
        self,
        raw_content: str,
        retrieved_chunks: list[RetrievedChunk],
        *,
        allow_auto_reply: bool = True,
        attempt: int = 1,
    ) -> ValidationResult:
        errors: list[str] = []
        answer = self._parse_answer(raw_content, errors)
        if answer is None:
            return ValidationResult(is_valid=False, errors=errors, attempt=attempt)

        allowed_citations = {chunk.chunk_id for chunk in retrieved_chunks}
        unknown_citations = [citation for citation in answer.citations if citation not in allowed_citations]
        if unknown_citations:
            errors.append(f"unknown citations: {', '.join(unknown_citations)}")

        if self.pii_service.mask(answer.answer).has_pii:
            errors.append("answer contains pii")

        if self._asks_for_secret(answer.answer):
            errors.append("answer asks for password, otp, or full card number")

        forbidden_claim = self._find_forbidden_claim(answer.answer)
        if forbidden_claim:
            errors.append(f"forbidden claim: {forbidden_claim}")

        if answer.needs_operator and allow_auto_reply:
            errors.append("needs_operator=True blocks auto reply")

        return ValidationResult(is_valid=not errors, errors=errors, attempt=attempt)

    @staticmethod
    def _parse_answer(raw_content: str, errors: list[str]) -> LLMAnswer | None:
        try:
            payload = json.loads(raw_content)
        except json.JSONDecodeError:
            errors.append("invalid json")
            return None

        try:
            return LLMAnswer.model_validate(payload)
        except ValidationError as exc:
            errors.extend(error["msg"] for error in exc.errors())
            return None

    @staticmethod
    def _asks_for_secret(answer: str) -> bool:
        patterns = (
            r"(пришлите|отправьте|назовите|укажите|сообщите).{0,40}(пароль|otp|код)",
            r"(пришлите|отправьте|назовите|укажите|сообщите).{0,40}полный номер карты",
        )
        return any(re.search(pattern, answer, re.IGNORECASE) for pattern in patterns)

    @staticmethod
    def _find_forbidden_claim(answer: str) -> str | None:
        claims = (
            "вернула деньги",
            "изменил email",
            "изменила email",
            "изменил телефон",
            "изменила телефон",
            "разблокировал аккаунт",
            "разблокировала аккаунт",
            "отменил платёж",
            "отменила платёж",
            "отменил платеж",
            "отменила платеж",
            "удалил аккаунт",
            "удалила аккаунт",
            "удалил данные",
            "удалила данные",
        )
        lowered = answer.lower()
        for claim in claims:
            if claim in lowered:
                return claim
        return None
