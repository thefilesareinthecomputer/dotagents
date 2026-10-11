from agents_app import config


def _write_config(tmp_path, monkeypatch, body):
    monkeypatch.setenv("AGENTS_APP_HOME", str(tmp_path))
    (tmp_path / "config").write_text(body)


def test_file_values_used_when_env_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTS_APP_HOST", raising=False)
    monkeypatch.delenv("AGENTS_APP_PORT", raising=False)
    _write_config(tmp_path, monkeypatch,
                  "# comment\nname = Sam\nhost = 10.0.0.5\nport = 9001\n"
                  "gitignored = _USER, PROJECTS/private\n")
    assert config.host() == "10.0.0.5"
    assert config.port() == 9001
    assert config.preferred_name() == "Sam"
    assert config.ignored_folders("gitignored") == ["_USER", "PROJECTS/private"]
    assert config.ignored_folders("agentignored") == []


def test_env_overrides_stored_value(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, "host = 10.0.0.5\nport = 9001\n")
    monkeypatch.setenv("AGENTS_APP_HOST", "0.0.0.0")
    monkeypatch.setenv("AGENTS_APP_PORT", "7000")
    assert config.host() == "0.0.0.0"
    assert config.port() == 7000


def test_malformed_values_fall_back(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTS_APP_PORT", raising=False)
    monkeypatch.delenv("AGENTS_APP_HOST", raising=False)
    _write_config(tmp_path, monkeypatch, "port = not-a-number\nhost =\njunk line\n")
    assert config.port() == 8765
    assert config.host() == "127.0.0.1"


def test_missing_file_yields_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTS_APP_HOME", str(tmp_path))
    monkeypatch.delenv("AGENTS_APP_PORT", raising=False)
    assert config.load_file() == {}
    assert config.port() == 8765
    assert config.model_default() == ""
