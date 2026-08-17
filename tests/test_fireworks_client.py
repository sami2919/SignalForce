"""Tests for the Fireworks AI client integration.

Tests verify:
- Config resolution (API key, base URL, model)
- Client construction (AsyncOpenAI pointed at Fireworks)
- OpenAIChatCompletionsModel construction (the key pattern from the reference repo)
- Agent building
- Error handling when API key is missing

Network calls are NOT made — tests use mocks for the OpenAI client and Runner.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scripts.fireworks_client import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    _get_base_url,
    _get_fireworks_api_key,
    _get_model,
    build_chat_model,
    build_fireworks_agent,
    build_openai_client,
    fireworks_completion,
    run_agent_sync,
)


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------


class TestConfigResolution:
    """Test the config/env resolution helpers."""

    def test_get_api_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FIREWORKS_API_KEY", "fw-test-key-123")
        assert _get_fireworks_api_key() == "fw-test-key-123"

    def test_get_api_key_missing_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
        # Also need to ensure config doesn't have it
        with patch("scripts.fireworks_client.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.fireworks_api_key = None
            mock_config.return_value = mock_cfg
            with pytest.raises(RuntimeError, match="No Fireworks API key"):
                _get_fireworks_api_key()

    def test_get_base_url_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FIREWORKS_BASE_URL", raising=False)
        assert _get_base_url() == DEFAULT_BASE_URL

    def test_get_base_url_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FIREWORKS_BASE_URL", "https://custom.fireworks.ai/v2")
        assert _get_base_url() == "https://custom.fireworks.ai/v2"

    def test_get_model_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FIREWORKS_MODEL", raising=False)
        assert _get_model() == DEFAULT_MODEL

    def test_get_model_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FIREWORKS_MODEL", "accounts/fireworks/models/llama-v3-70b")
        assert _get_model() == "accounts/fireworks/models/llama-v3-70b"


# ---------------------------------------------------------------------------
# Client / model construction
# ---------------------------------------------------------------------------


class TestClientConstruction:
    """Test the OpenAI client and chat model construction."""

    def test_build_openai_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FIREWORKS_API_KEY", "fw-test-key")
        monkeypatch.setenv("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")
        client = build_openai_client()
        assert client is not None
        assert client.base_url.host == "api.fireworks.ai"

    def test_build_chat_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FIREWORKS_API_KEY", "fw-test-key")
        model = build_chat_model(model="accounts/fireworks/models/test-model")
        assert model is not None
        assert model.model == "accounts/fireworks/models/test-model"

    def test_build_chat_model_with_custom_client(self) -> None:
        mock_client = MagicMock()
        model = build_chat_model(
            model="accounts/fireworks/models/custom",
            client=mock_client,
        )
        assert model.model == "accounts/fireworks/models/custom"

    def test_build_fireworks_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FIREWORKS_API_KEY", "fw-test-key")
        agent = build_fireworks_agent(
            name="TestAgent",
            instructions="You are a test agent.",
        )
        assert agent.name == "TestAgent"
        assert "test agent" in agent.instructions.lower()


# ---------------------------------------------------------------------------
# Sync runner
# ---------------------------------------------------------------------------


class TestRunnerSync:
    """Test the synchronous runner with mocked Runner."""

    def test_run_agent_sync(self) -> None:
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.final_output = "Test output from Fireworks"
        with patch("scripts.fireworks_client.Runner") as mock_runner:
            mock_runner.run_sync.return_value = mock_result
            result = run_agent_sync(mock_agent, "Hello")
            assert result == "Test output from Fireworks"
            mock_runner.run_sync.assert_called_once_with(mock_agent, "Hello")


# ---------------------------------------------------------------------------
# Completion helper
# ---------------------------------------------------------------------------


class TestFireworksCompletion:
    """Test the fireworks_completion sync helper."""

    def test_completion_returns_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FIREWORKS_API_KEY", "fw-test-key")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Fireworks generated text"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client):
            result = fireworks_completion("Write a poem")
            assert result == "Fireworks generated text"

    def test_completion_empty_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FIREWORKS_API_KEY", "fw-test-key")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client):
            result = fireworks_completion("Write a poem")
            assert result == ""


# ---------------------------------------------------------------------------
# AppConfig integration
# ---------------------------------------------------------------------------


class TestAppConfigIntegration:
    """Test that Fireworks config fields are properly on AppConfig."""

    def test_appconfig_has_fireworks_fields(self) -> None:
        from scripts.config import AppConfig

        cfg = AppConfig(
            fireworks_api_key="fw-config-key",
            fireworks_base_url="https://config.fireworks.ai/v1",
            fireworks_model="accounts/fireworks/models/config-model",
        )
        assert cfg.fireworks_api_key == "fw-config-key"
        assert cfg.fireworks_base_url == "https://config.fireworks.ai/v1"
        assert cfg.fireworks_model == "accounts/fireworks/models/config-model"

    def test_appconfig_fireworks_defaults_none(self) -> None:
        from scripts.config import AppConfig

        cfg = AppConfig()
        assert cfg.fireworks_api_key is None
        assert cfg.fireworks_base_url is None
        assert cfg.fireworks_model is None
