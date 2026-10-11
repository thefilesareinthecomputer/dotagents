from pathlib import Path

from second_brain import config


def test_defaults(monkeypatch):
    for var in ("SECOND_BRAIN_VAULT", "SECOND_BRAIN_DATA", "SECOND_BRAIN_HOST",
                "SECOND_BRAIN_PORT", "OLLAMA_URL"):
        monkeypatch.delenv(var, raising=False)
    assert config.vault_path().name == "vault"
    assert config.data_path().name == "data"
    assert config.host() == "127.0.0.1"
    assert config.port() == 8765
    assert config.ollama_url() == "http://localhost:11434"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("SECOND_BRAIN_VAULT", "/tmp/v")
    monkeypatch.setenv("SECOND_BRAIN_DATA", "/tmp/d")
    monkeypatch.setenv("SECOND_BRAIN_HOST", "0.0.0.0")
    monkeypatch.setenv("SECOND_BRAIN_PORT", "9999")
    monkeypatch.setenv("OLLAMA_URL", "http://example:1")
    assert config.vault_path() == Path("/tmp/v")
    assert config.data_path() == Path("/tmp/d")
    assert config.host() == "0.0.0.0"
    assert config.port() == 9999
    assert config.ollama_url() == "http://example:1"
