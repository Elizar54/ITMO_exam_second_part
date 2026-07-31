from src.schemas import RetrievedChunk
from tests.fakes import FakeLLMClient, VALID_RESPONSE


def chunks() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id="kb-password-reset",
            text="Восстановление пароля",
            source="kb",
            score=0.9,
        )
    ]


def test_fake_llm_counts_calls() -> None:
    client = FakeLLMClient([VALID_RESPONSE])

    response = client.generate("Не могу восстановить пароль", chunks())

    assert response.raw_content == VALID_RESPONSE
    assert client.call_count == 1


def test_llm_receives_only_redacted_text() -> None:
    client = FakeLLMClient([VALID_RESPONSE])

    client.generate("Письмо не приходит на [EMAIL_1]", chunks())

    assert client.safe_calls[0]["redacted_text"] == "Письмо не приходит на [EMAIL_1]"
    assert "user@example.com" not in str(client.safe_calls)
