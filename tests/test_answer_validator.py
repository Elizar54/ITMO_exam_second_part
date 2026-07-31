from src.answer_validator import AnswerValidator
from src.schemas import RetrievedChunk
from tests.fakes import FAKE_CITATION, FORBIDDEN_CLAIM, INVALID_JSON, VALID_RESPONSE


def chunks() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id="kb-password-reset",
            text="Восстановление пароля",
            source="kb",
            score=0.9,
        )
    ]


def test_valid_grounded_json_passes() -> None:
    result = AnswerValidator().validate(VALID_RESPONSE, chunks())

    assert result.is_valid is True
    assert result.errors == []


def test_invalid_json_is_blocked() -> None:
    result = AnswerValidator().validate(INVALID_JSON, chunks())

    assert result.is_valid is False
    assert "invalid json" in result.errors


def test_unknown_citation_is_blocked() -> None:
    result = AnswerValidator().validate(FAKE_CITATION, chunks())

    assert result.is_valid is False
    assert any("unknown citations" in error for error in result.errors)


def test_pii_in_answer_is_blocked() -> None:
    raw = (
        '{"answer": "Напишите на user@example.com.", '
        '"citations": ["kb-password-reset"], "needs_operator": false}'
    )

    result = AnswerValidator().validate(raw, chunks())

    assert result.is_valid is False
    assert "answer contains pii" in result.errors


def test_password_request_is_blocked() -> None:
    raw = (
        '{"answer": "Сообщите ваш пароль оператору.", '
        '"citations": ["kb-password-reset"], "needs_operator": false}'
    )

    result = AnswerValidator().validate(raw, chunks())

    assert result.is_valid is False
    assert any("asks for password" in error for error in result.errors)


def test_forbidden_claim_is_blocked() -> None:
    result = AnswerValidator().validate(FORBIDDEN_CLAIM, chunks())

    assert result.is_valid is False
    assert any("forbidden claim" in error for error in result.errors)


def test_needs_operator_blocks_auto_reply() -> None:
    raw = '{"answer": "Нужен оператор.", "citations": [], "needs_operator": true}'

    result = AnswerValidator().validate(raw, chunks(), allow_auto_reply=True)

    assert result.is_valid is False
    assert "needs_operator=True blocks auto reply" in result.errors
