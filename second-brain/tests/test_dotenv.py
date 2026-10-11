from second_brain import config


def test_dotenv_loads_and_env_wins(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nDOTENV_NEW=from-file\nDOTENV_SET='quoted'\nPRESET=file-value\n")
    monkeypatch.delenv("DOTENV_NEW", raising=False)
    monkeypatch.delenv("DOTENV_SET", raising=False)
    monkeypatch.setenv("PRESET", "env-value")
    config.load_dotenv(env_file)
    import os
    assert os.environ["DOTENV_NEW"] == "from-file"
    assert os.environ["DOTENV_SET"] == "quoted"
    assert os.environ["PRESET"] == "env-value"
    monkeypatch.delenv("DOTENV_NEW", raising=False)
    monkeypatch.delenv("DOTENV_SET", raising=False)


def test_dotenv_missing_file_is_noop(tmp_path):
    config.load_dotenv(tmp_path / "absent.env")
