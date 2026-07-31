import json

import httpx
import pytest

from src.config import Settings
from src.exceptions import LLMRateLimitError, LLMTimeoutError, LLMUnavailableError
from src.llm_client import OpenRouterClient
from src.schemas import RetrievedChunk


def chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="kb-password-reset",
        text="Восстановление пароля",
        source="kb",
        score=0.9,
    )


def config(api_key: str = "test-key") -> Settings:
    return Settings(
        openrouter_api_key=api_key,
        openrouter_model="test/model",
        openrouter_endpoint="https://openrouter.test/chat",
        openrouter_timeout_seconds=2,
        openrouter_max_tokens=123,
    )


def test_mock_mode_when_api_key_missing() -> None:
    client = OpenRouterClient(config(api_key=""))

    response = client.generate("Не могу войти", [chunk()])

    assert client.mock_mode is True
    assert client.mode_label == "mock mode"
    assert response.model == "mock-openrouter"


def test_openrouter_payload_uses_only_redacted_text_and_chunks() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "test/model",
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"answer": "Откройте восстановление.", '
                                '"citations": ["kb-password-reset"], '
                                '"needs_operator": false}'
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            },
        )

    client = OpenRouterClient(config(), httpx.Client(transport=httpx.MockTransport(handler)))

    response = client.generate("Письмо не приходит на [EMAIL_1]", [chunk()])

    assert captured["authorization"] == "Bearer test-key"
    assert captured["payload"]["temperature"] == 0
    assert captured["payload"]["max_tokens"] == 123
    user_content = captured["payload"]["messages"][1]["content"]
    assert "[EMAIL_1]" in user_content
    assert "user@example.com" not in user_content
    assert "kb-password-reset" in user_content
    assert response.token_usage == {"prompt_tokens": 11, "completion_tokens": 7}
    assert response.estimated_cost_usd == 0.0


def test_corrective_generate_includes_validation_errors_and_allowed_ids() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured["user"] = json.loads(payload["messages"][1]["content"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"answer": "Откройте восстановление.", '
                                '"citations": ["kb-password-reset"], '
                                '"needs_operator": false}'
                            )
                        }
                    }
                ]
            },
        )

    client = OpenRouterClient(config(), httpx.Client(transport=httpx.MockTransport(handler)))

    client.corrective_generate("Письмо на [EMAIL_1]", [chunk()], ["unknown citations"])

    assert captured["user"]["validation_errors"] == ["unknown citations"]
    assert captured["user"]["allowed_document_ids"] == ["kb-password-reset"]


def test_timeout_maps_to_domain_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    client = OpenRouterClient(config(), httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(LLMTimeoutError):
        client.generate("text", [chunk()])


def test_429_maps_to_rate_limit_error() -> None:
    client = OpenRouterClient(
        config(),
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(429))),
    )

    with pytest.raises(LLMRateLimitError):
        client.generate("text", [chunk()])


def test_5xx_maps_to_unavailable_error() -> None:
    client = OpenRouterClient(
        config(),
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))),
    )

    with pytest.raises(LLMUnavailableError):
        client.generate("text", [chunk()])


@pytest.mark.integration
def test_openrouter_integration_skips_without_api_key() -> None:
    real_config = Settings()
    if not real_config.openrouter_api_key:
        pytest.skip("OPENROUTER_API_KEY is not configured")
    client = OpenRouterClient(real_config)
    response = client.generate("Как восстановить пароль?", [chunk()])
    assert response.raw_content
