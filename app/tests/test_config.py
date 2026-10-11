from pathlib import Path

from agents_app import config


def test_defaults(monkeypatch):
    for var in ("AGENTS_APP_VAULT", "AGENTS_APP_DATA", "AGENTS_APP_HOST",
                "AGENTS_APP_PORT", "OLLAMA_URL"):
        monkeypatch.delenv(var, raising=False)
    assert config.vault_path().name == "vault"
    assert config.data_path().name == "data"
    assert config.host() == "127.0.0.1"
    assert config.port() == 8765
    assert config.ollama_url() == "http://localhost:11434"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("AGENTS_APP_VAULT", "/tmp/v")
    monkeypatch.setenv("AGENTS_APP_DATA", "/tmp/d")
    monkeypatch.setenv("AGENTS_APP_HOST", "0.0.0.0")
    monkeypatch.setenv("AGENTS_APP_PORT", "9999")
    monkeypatch.setenv("OLLAMA_URL", "http://example:1")
    assert config.vault_path() == Path("/tmp/v")
    assert config.data_path() == Path("/tmp/d")
    assert config.host() == "0.0.0.0"
    assert config.port() == 9999
    assert config.ollama_url() == "http://example:1"
