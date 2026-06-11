from scripts.config import AppConfig


def test_app_config_has_serpapi_key():
    """AppConfig must expose serpapi_key for job scanner use."""
    cfg = AppConfig(serpapi_key="test-key-123")
    assert cfg.serpapi_key == "test-key-123"


def test_app_config_serpapi_key_accepts_none():
    """serpapi_key can be set to None explicitly."""
    cfg = AppConfig(serpapi_key=None)
    assert cfg.serpapi_key is None


def test_app_config_has_anthropic_api_key():
    """AppConfig must expose anthropic_api_key for marops CLI use."""
    cfg = AppConfig(anthropic_api_key="anth-key-abc")
    assert cfg.anthropic_api_key == "anth-key-abc"


def test_app_config_anthropic_api_key_accepts_none():
    """anthropic_api_key can be set to None explicitly."""
    cfg = AppConfig(anthropic_api_key=None)
    assert cfg.anthropic_api_key is None
