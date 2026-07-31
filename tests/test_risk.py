import pytest

from src.pii import PIIMaskingService
from src.risk import RiskService
from src.schemas import RiskLevel


@pytest.fixture()
def risk_service() -> RiskService:
    return RiskService()


@pytest.mark.parametrize(
    "text",
    [
        "Не могу восстановить пароль",
        "Как изменить настройки уведомлений?",
        "Хочу уточнить условия подписки",
        "Приложение не открывается после обновления",
    ],
)
def test_regular_support_questions_are_low_risk(risk_service: RiskService, text: str) -> None:
    result = risk_service.assess(text)

    assert result.level == RiskLevel.LOW
    assert result.matched_rules == []


def test_pii_does_not_mean_high_risk(risk_service: RiskService) -> None:
    privacy = PIIMaskingService().mask("Не приходит письмо на user@example.com")
    result = risk_service.assess(privacy.redacted_text)

    assert result.level == RiskLevel.LOW


@pytest.mark.parametrize(
    ("text", "expected_rule"),
    [
        ("Кажется, был чужой вход в аккаунт", "account_takeover_or_fraud"),
        ("Я не узнаю списание за подписку", "unknown_financial_operation"),
        ("Если не ответите, подам в суд", "legal_claim"),
        ("Нужно удалить все данные из аккаунта", "critical_account_action"),
    ],
)
def test_high_risk_rules_are_detected(
    risk_service: RiskService,
    text: str,
    expected_rule: str,
) -> None:
    result = risk_service.assess(text)

    assert result.level == RiskLevel.HIGH
    assert expected_rule in result.matched_rules
    assert result.reasons
