import pytest
from pydantic import ValidationError

from src.schemas import LLMAnswer, TicketInput


def test_empty_ticket_rejected() -> None:
    with pytest.raises(ValidationError):
        TicketInput(session_id="session-1", channel="web", text="")


def test_short_ticket_rejected() -> None:
    with pytest.raises(ValidationError):
        TicketInput(session_id="session-1", channel="web", text="ab")


def test_too_long_ticket_rejected() -> None:
    with pytest.raises(ValidationError):
        TicketInput(session_id="session-1", channel="web", text="a" * 5001)


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        TicketInput(
            session_id="session-1",
            channel="web",
            text="valid ticket text",
            unexpected="value",
        )


def test_llm_answer_without_citations_rejected_when_operator_not_needed() -> None:
    with pytest.raises(ValidationError):
        LLMAnswer(answer="Use the password reset form.", citations=[], needs_operator=False)


def test_llm_answer_without_citations_allowed_when_operator_needed() -> None:
    answer = LLMAnswer(answer="Operator review is needed.", needs_operator=True)

    assert answer.citations == []
