import pytest

from src.pii import PIIMaskingService


@pytest.fixture()
def pii_service() -> PIIMaskingService:
    return PIIMaskingService()


@pytest.mark.parametrize(
    ("text", "placeholder", "raw_value"),
    [
        ("Ответьте на user@example.com по заявке", "[EMAIL_1]", "user@example.com"),
        ("Позвоните на +7 913 123-45-67 сегодня", "[PHONE_1]", "+7 913 123-45-67"),
        ("Оплата картой 4111-1111-1111-1111 не проходит", "[CARD_1]", "4111-1111-1111-1111"),
        ("Адрес сервера 192.168.1.10 не открывается", "[IP_ADDRESS_1]", "192.168.1.10"),
        ("Authorization: Bearer abcdef1234567890", "[TOKEN_1]", "Bearer abcdef1234567890"),
    ],
)
def test_pii_values_are_masked(
    pii_service: PIIMaskingService,
    text: str,
    placeholder: str,
    raw_value: str,
) -> None:
    result = pii_service.mask(text)

    assert placeholder in result.redacted_text
    assert raw_value not in result.redacted_text
    assert result.has_pii is True


def test_same_pii_types_are_numbered_sequentially(pii_service: PIIMaskingService) -> None:
    result = pii_service.mask("Пишите на first@example.com или second@example.com")

    assert "[EMAIL_1]" in result.redacted_text
    assert "[EMAIL_2]" in result.redacted_text


def test_otp_is_masked_only_in_code_context(pii_service: PIIMaskingService) -> None:
    with_context = pii_service.mask("Код подтверждение 123456 не принимается")
    without_context = pii_service.mask("Мой заказ 123456 не отображается")

    assert "[OTP_CODE_1]" in with_context.redacted_text
    assert "123456" not in with_context.redacted_text
    assert without_context.redacted_text == "Мой заказ 123456 не отображается"
    assert without_context.has_pii is False


def test_original_values_are_absent_from_redacted_text(pii_service: PIIMaskingService) -> None:
    result = pii_service.mask(
        "Email user@example.com, телефон 8 913 123 45 67, код 765432, ip 10.0.0.1"
    )

    for raw_value in ("user@example.com", "8 913 123 45 67", "765432", "10.0.0.1"):
        assert raw_value not in result.redacted_text
