import json

import pytest
from asgi_client import TestClient

from second_brain.app import create_app

client = TestClient(create_app())


def test_only_loopback_hosts_are_answered():
    """DNS rebinding sends a foreign domain as Host; the app refuses it.
    Every loopback spelling, with or without a port, is accepted."""
    for host in ("127.0.0.1", "127.0.0.1:8765", "localhost:8765", "[::1]:8765"):
        assert client.get("/kb/stats", headers={"host": host}).status_code == 200, host
    for host in ("attacker.example", "attacker.example:8765", "192.168.1.20:8765", ""):
        assert client.get("/kb/stats", headers={"host": host}).status_code == 421, host
    # A scripted LAN client can forge Host, so the peer address is checked too.
    lan = TestClient(create_app(), peer="192.168.1.20")
    assert lan.get("/kb/stats", headers={"host": "127.0.0.1"}).status_code == 421


def test_index_serves_ui():
    r = client.get("/")
    assert r.status_code == 200
    assert "<title>second-brain</title>" in r.text


def test_static_files_served():
    for path in ("/ui/app.js", "/ui/style.css", "/ui/kb-graph-hud.js",
                 "/ui/lib/marked.min.js"):
        assert client.get(path).status_code == 200


def test_path_traversal_confined():
    r = client.get("/ui/../../../etc/passwd")
    assert r.status_code == 404


# --- brain model CLI ---

def _model_cli(monkeypatch, tmp_path):
    from second_brain import app as app_module, chat, config
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    monkeypatch.setattr(chat, "available_models",
                        lambda: (["claude-code", "llama3:8b",
                                  "qwen3:4b"], "claude-code"))
    return app_module, config


def test_cmd_model_lists_without_arg(monkeypatch, tmp_path, capsys):
    app_module, _ = _model_cli(monkeypatch, tmp_path)
    assert app_module.cmd_model(None) == 0
    out = capsys.readouterr().out
    assert "current: claude-code" in out and "qwen3:4b" in out


def test_cmd_model_sets_persistent_default(monkeypatch, tmp_path):
    app_module, config = _model_cli(monkeypatch, tmp_path)
    assert app_module.cmd_model("qwen3:4b") == 0
    assert config.model_default() == "qwen3:4b"
    # rewrites preserve other stored keys
    assert app_module.cmd_model("llama3:8b") == 0
    assert config.model_default() == "llama3:8b"


def test_cmd_model_rejects_unknown(monkeypatch, tmp_path):
    app_module, config = _model_cli(monkeypatch, tmp_path)
    assert app_module.cmd_model("gpt-99") == 1
    assert config.model_default() == ""


def test_cmd_seat_bare_lists_roster(monkeypatch, tmp_path, capsys):
    from second_brain import app as app_module
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    assert app_module.cmd_seat([]) == 0
    assert "no seats in the roster" in capsys.readouterr().out


def test_cmd_seat_guest_requires_name(monkeypatch, tmp_path):
    from second_brain import app as app_module
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    assert app_module.cmd_seat(["only-a-cid"]) == 1


def test_cmd_seat_roster_add_list_remove(monkeypatch, tmp_path, capsys):
    from second_brain import app as app_module, config
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    repo = tmp_path / "repo"
    repo.mkdir()
    config.save_file({"seat_roots": str(tmp_path)})  # seats are confined
    assert app_module.cmd_seat(["add", "Scribe", str(repo)]) == 0
    assert config.seats_roster() == [{"name": "Scribe",
                                      "cwd": str(repo)}]
    assert app_module.cmd_seat([]) == 0
    assert "@scribe" in capsys.readouterr().out
    # re-add updates in place, case-insensitive on name
    assert app_module.cmd_seat(["add", "scribe", str(repo),
                                "claude", "sonnet"]) == 0
    roster = config.seats_roster()
    assert len(roster) == 1 and roster[0]["model"] == "sonnet"
    assert app_module.cmd_seat(["remove", "Scribe"]) == 0
    assert config.seats_roster() == []
    assert app_module.cmd_seat(["remove", "Scribe"]) == 1


def test_self_mutation_commands_refuse_inside_a_seat(monkeypatch, tmp_path,
                                                     capsys):
    """The --disallowedTools prefix only sees the literal command; a seat
    repo granting a broad shell reaches `brain seat` through a compound
    command or a subprocess. The entry point itself refuses when the
    spawn env marks the process as a seat (security review 2026-09-03)."""
    from second_brain import app as app_module, config
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    repo = tmp_path / "repo"
    repo.mkdir()
    config.save_file({"seat_roots": str(tmp_path)})
    monkeypatch.setenv("BRAIN_SEAT", "worker")
    assert app_module.cmd_seat(["add", "Scribe", str(repo)]) == 1
    assert config.seats_roster() == []
    assert app_module.cmd_config_set("model", "sonnet") == 1
    err = capsys.readouterr().err
    assert "seat" in err and "user" in err
    monkeypatch.delenv("BRAIN_SEAT")
    assert app_module.cmd_seat(["add", "Scribe", str(repo)]) == 0


def test_seat_policy_endpoint_is_the_spawner_view_read_only(monkeypatch, tmp_path):
    """PLAN-SEAT-HARDENING-V1 P5: the card is built by the same resolver
    the spawner uses, so what it shows cannot drift from the flags. It
    attributes every allow and deny to its source and lists the hooks
    that will fire with their headless meaning. GET only."""
    from asgi_client import TestClient

    from second_brain import chat, config, conversations
    from second_brain.app import create_app

    monkeypatch.setenv("SECOND_BRAIN_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path / "home"))
    config.save_file({"seat_roots": str(tmp_path)})
    seat_dir = tmp_path / "seat"
    (seat_dir / ".claude").mkdir(parents=True)
    (seat_dir / ".claude" / "settings.local.json").write_text(json.dumps({
        "permissions": {"allow": ["Edit(./**)"], "deny": ["Read(./secret)"]},
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "bash guard.sh"},
            {"type": "command", "command": "/opt/hooks/one-word"},
            {"type": "prompt", "prompt": "safe?"}]}]}}))
    global_settings = tmp_path / "global.json"
    global_settings.write_text(json.dumps({
        "permissions": {"deny": ["Read(**/.ssh/**)"]},
        "hooks": {"SessionStart": [{"hooks": [
            {"type": "command", "command": "python3 start.py"}]}]}}))
    monkeypatch.setattr(chat, "_global_settings_path", lambda: global_settings)
    monkeypatch.setattr(chat, "_trusted", lambda cwd: False)
    monkeypatch.setattr(chat, "_gate_state", lambda: {"level": 1, "ack_fresh": False})
    config.save_seats_roster([{"name": "Scout", "cwd": str(seat_dir),
                               "model": "opus", "effort": "medium"}])

    client = TestClient(create_app())
    cid = conversations.create()["id"]
    conversations.add_participant(cid, "Scout", str(seat_dir), model="opus")

    r = client.get(f"/conversations/{cid}/participants/scout/policy")
    assert r.status_code == 200
    policy = r.json()
    assert policy["cwd"] == str(seat_dir) and policy["trusted"] is False
    assert policy["readonly"] is False
    assert {"rule": "Edit(./**)", "source": "settings.local.json"} in policy["allow"]
    assert {"rule": "Read(./secret)", "source": "settings.local.json"} in policy["deny"]
    assert {"rule": "Read(**/.ssh/**)", "source": "global"} in policy["deny"]
    assert {"rule": "Bash(git reset:*)", "source": "spawn-flag"} in policy["deny"]
    assert "Bash(git push:*)" not in {row["rule"] for row in policy["deny"]}
    assert not [row for row in policy["allow"] if row["source"] == "spawn-flag"]
    hooks = {(h["source"], h["event"], h["command"], h["headless"]) for h in policy["hooks"]}
    assert ("settings.local.json", "PreToolUse", "bash guard.sh", "ask becomes deny") in hooks
    # one-word commands and prompt hooks render without crashing the card
    assert ("settings.local.json", "PreToolUse", "one-word", "ask becomes deny") in hooks
    assert ("settings.local.json", "PreToolUse", "safe?", "ask becomes deny") in hooks
    assert ("global", "SessionStart", "python3 start.py", "") in hooks
    assert policy["model"] == {"declared": "opus", "resolved": "opus", "source": "seat"}
    assert policy["effort"] == {"declared": "medium", "resolved": chat.SEAT_EFFORT,
                                "source": "seat default"}
    assert policy["gate"] == {"level": 1, "ack_fresh": False}

    assert client.get(f"/conversations/{cid}/participants/ghost/policy").status_code == 404
    assert client.post(f"/conversations/{cid}/participants/scout/policy").status_code == 405


def test_cmd_seat_add_readonly_flag(monkeypatch, tmp_path):
    """`brain seat add <name> <repo> [harness] [model] [effort] [readonly]`:
    the trailing word marks a seat that may only read, which is the only
    way a rules-source directory can be seated."""
    from second_brain import app as app_module, config
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    repo = tmp_path / "repo"
    repo.mkdir()
    config.save_file({"seat_roots": str(tmp_path)})
    assert app_module.cmd_seat(["add", "Dot", str(repo), "claude", "",
                                "", "readonly"]) == 0
    assert config.seats_roster()[0]["readonly"] is True
    assert app_module.cmd_seat(["add", "Dot", str(repo), "claude", "",
                                "", "sideways"]) == 1


def test_cmd_seat_add_rejects_missing_dir(monkeypatch, tmp_path):
    from second_brain import app as app_module, config
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    assert app_module.cmd_seat(["add", "Ghost",
                                str(tmp_path / "nope")]) == 1
    assert config.seats_roster() == []


def test_cmd_down_signals_the_whole_process_group(monkeypatch, tmp_path):
    """User requirement 2026-08-27: closing the app must close every
    spawned CLI - down signals the server's process group (pgid == pid
    because up starts it with start_new_session), not just the pid."""
    import os as os_module
    import signal as signal_module
    from second_brain import app as app_module
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    (tmp_path / "pid").write_text("4242\n8765\n")

    sent = []
    alive = iter([True, True, False])  # alive at check, dead after TERM
    monkeypatch.setattr(app_module, "_alive", lambda pid: next(alive, False))
    monkeypatch.setattr(os_module, "killpg",
                        lambda pgid, sig: sent.append(("pg", pgid, sig)))
    monkeypatch.setattr(app_module, "_release_local_models", lambda: None)

    assert app_module.cmd_down() == 0
    assert ("pg", 4242, signal_module.SIGTERM) in sent
    assert not (tmp_path / "pid").exists()


def test_agents_snapshot_endpoint():
    from second_brain import registry
    registry._rows.clear()
    assert client.get("/agents").json() == {"agents": []}
    registry.begin("c1", "main", "Main", "/repo", "sonnet")
    try:
        rows = client.get("/agents").json()["agents"]
        assert rows[0]["actor"] == "main" and rows[0]["state"] == "starting"
    finally:
        registry._rows.clear()


def test_claude_settings_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    monkeypatch.delenv("SECOND_BRAIN_CLAUDE_MODEL", raising=False)
    monkeypatch.delenv("SECOND_BRAIN_CLAUDE_EFFORT", raising=False)
    r = client.get("/settings/claude")
    assert r.json()["model"] == "sonnet" and r.json()["effort"] == "medium"

    r = client.post("/settings/claude", json={"model": "haiku",
                                              "effort": "low"})
    assert r.status_code == 200
    r = client.get("/settings/claude")
    assert r.json() == {"model": "haiku", "effort": "low",
                        "efforts": ["low", "medium", "high", "xhigh",
                                    "max"]}
    # partial update keeps the other key
    assert client.post("/settings/claude",
                       json={"effort": "high"}).status_code == 200
    assert client.get("/settings/claude").json()["model"] == "haiku"
    assert client.post("/settings/claude",
                       json={"effort": "extreme"}).status_code == 422
    assert client.post("/settings/claude",
                       json={"model": "bad model; rm"}).status_code == 422


def test_cmd_search_requires_query(monkeypatch, tmp_path):
    from second_brain import app as app_module
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    assert app_module.cmd_search([]) == 1


def test_cmd_search_reports_server_down(monkeypatch, tmp_path):
    from second_brain import app as app_module
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    monkeypatch.setenv("SECOND_BRAIN_PORT", "9")  # nothing listens here
    assert app_module.cmd_search(["bronze", "layer"]) == 1


def test_cmd_seat_reports_server_down(monkeypatch, tmp_path):
    from second_brain import app as app_module
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    monkeypatch.setenv("SECOND_BRAIN_PORT", "9")  # nothing listens here
    assert app_module.cmd_seat(["cid123", "Zed"]) == 1


# --- brain config get / set (the agent-facing config surface) ---

def _config_cli(monkeypatch, tmp_path):
    from second_brain import app as app_module, config
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    for var in ("SECOND_BRAIN_HOST", "SECOND_BRAIN_PORT",
                "SECOND_BRAIN_HARNESS"):
        monkeypatch.delenv(var, raising=False)
    return app_module, config


def test_config_get_lists_all_keys(monkeypatch, tmp_path, capsys):
    app_module, _ = _config_cli(monkeypatch, tmp_path)
    assert app_module.cmd_config_get(None) == 0
    out = capsys.readouterr().out
    assert "host = 127.0.0.1" in out and "harness = claude" in out


def test_config_get_single_key_prints_effective_value(monkeypatch, tmp_path,
                                                      capsys):
    app_module, config = _config_cli(monkeypatch, tmp_path)
    config.save_file({"name": "Sam"})
    assert app_module.cmd_config_get("name") == 0
    assert capsys.readouterr().out.strip() == "Sam"


def test_config_get_rejects_unknown_key(monkeypatch, tmp_path):
    app_module, _ = _config_cli(monkeypatch, tmp_path)
    assert app_module.cmd_config_get("nope") == 1


def test_config_set_writes_and_preserves_other_keys(monkeypatch, tmp_path,
                                                    capsys):
    app_module, config = _config_cli(monkeypatch, tmp_path)
    config.save_file({"name": "Sam"})
    assert app_module.cmd_config_set("harness", "copilot") == 0
    stored = config.load_file()
    assert stored["harness"] == "copilot" and stored["name"] == "Sam"


def test_config_set_flags_restart_keys(monkeypatch, tmp_path, capsys):
    app_module, _ = _config_cli(monkeypatch, tmp_path)
    assert app_module.cmd_config_set("port", "9001") == 0
    assert "restart" in capsys.readouterr().out


def test_config_set_validates(monkeypatch, tmp_path):
    app_module, config = _config_cli(monkeypatch, tmp_path)
    assert app_module.cmd_config_set("nope", "x") == 1
    assert app_module.cmd_config_set("port", "not-a-number") == 1
    assert app_module.cmd_config_set("harness", "hal9000") == 1
    assert app_module.cmd_config_set("claude_effort", "extreme") == 1
    assert app_module.cmd_config_set(None, None) == 1
    assert config.load_file() == {}


def test_seat_roots_are_human_only(monkeypatch, tmp_path, capsys):
    """The one setting that bounds an agent's authority: readable by
    agents, never settable by one (security review 2026-08-29)."""
    app_module, config = _config_cli(monkeypatch, tmp_path)
    assert app_module.cmd_config_set("seat_roots", "/") == 1
    assert "seat_roots" not in config.load_file()
    assert "roots" in capsys.readouterr().err
    # readable, and the guided path writes nothing
    assert app_module.cmd_config_get("seat_roots") == 0
    before = config.config_file().read_text() \
        if config.config_file().exists() else None
    assert app_module.cmd_config_roots(print_only=True) == 0
    out = capsys.readouterr().out
    assert str(config.config_file()) in out and "seat_roots = " in out
    after = config.config_file().read_text() \
        if config.config_file().exists() else None
    assert before == after


@pytest.mark.real_seat_roots
def test_seat_add_confined_to_roots(monkeypatch, tmp_path, capsys):
    from second_brain import app as app_module, config
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    allowed_root = tmp_path / "workspaces"
    (allowed_root / "worker").mkdir(parents=True)
    outside = tmp_path / "elsewhere" / "secrets"
    outside.mkdir(parents=True)
    config.save_file({"seat_roots": str(allowed_root)})

    assert app_module.cmd_seat(["add", "Worker",
                                str(allowed_root / "worker")]) == 0
    assert [e["name"] for e in config.seats_roster()] == ["Worker"]

    assert app_module.cmd_seat(["add", "Sneak", str(outside)]) == 1
    err = capsys.readouterr().err
    assert "outside the permitted seat roots" in err
    assert "brain config roots" in err
    assert [e["name"] for e in config.seats_roster()] == ["Worker"]


@pytest.mark.real_seat_roots
def test_seat_roots_default_keeps_an_existing_roster_working(monkeypatch,
                                                             tmp_path):
    """Absent the key, roots derive from the roster - so turning the
    control on never strands a seat that already works."""
    from second_brain import config
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    seated = tmp_path / "far" / "away" / "repo"
    seated.mkdir(parents=True)
    config.save_seats_roster([{"name": "Far", "cwd": str(seated)}])
    assert config.seat_root_allowed(seated)
    assert config.seat_root_allowed(seated.parent / "sibling")
    assert not config.seat_root_allowed(tmp_path / "unrelated")


@pytest.mark.real_seat_roots
def test_derived_roots_never_open_the_whole_home(monkeypatch, tmp_path):
    """A seat living directly in $HOME must root only itself - taking its
    parent would permit nearly anywhere."""
    from second_brain import config
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    home = tmp_path / "home"
    (home / ".agents").mkdir(parents=True)
    monkeypatch.setattr(config.Path, "home", staticmethod(lambda: home))
    config.save_seats_roster([{"name": "Dot", "cwd": str(home / ".agents")}])
    roots = config.seat_roots()
    assert home not in roots
    assert (home / ".agents") in roots
    assert not config.seat_root_allowed(home / "Documents")


def test_config_set_refuses_nonloopback_host(monkeypatch, tmp_path):
    # an agent-reachable command must never publish this auth-less server
    app_module, config = _config_cli(monkeypatch, tmp_path)
    assert app_module.cmd_config_set("host", "0.0.0.0") == 1
    assert app_module.cmd_config_set("host", "192.168.1.20") == 1
    assert "host" not in config.load_file()
    assert app_module.cmd_config_set("host", "127.0.0.1") == 0


def test_config_set_refuses_remote_ollama(monkeypatch, tmp_path):
    app_module, config = _config_cli(monkeypatch, tmp_path)
    assert app_module.cmd_config_set("ollama_url",
                                     "http://10.0.0.5:11434") == 1
    assert app_module.cmd_config_set("ollama_url",
                                     "http://127.0.0.1:11434") == 0
    assert config.load_file()["ollama_url"] == "http://127.0.0.1:11434"


def test_config_set_model_uses_model_validation(monkeypatch, tmp_path):
    from second_brain import chat
    app_module, config = _config_cli(monkeypatch, tmp_path)
    monkeypatch.setattr(chat, "available_models",
                        lambda: (["qwen3:4b"], "qwen3:4b"))
    assert app_module.cmd_config_set("model", "gpt-99") == 1
    assert app_module.cmd_config_set("model", "qwen3:4b") == 0
    assert config.model_default() == "qwen3:4b"


# --- brain chat SSE rendering ---
# Frames come from the real encoder (chat.sse), so these tests pin the
# renderer to the actual wire contract - token/thinking percent-encoded,
# error plain text, the rest JSON.

def _frames(*pairs):
    from second_brain.chat import sse
    return b"".join(sse(event, payload) for event, payload in pairs) \
        .splitlines(keepends=True)


def test_render_sse_decodes_tokens_inline(capsys):
    from second_brain import app as app_module
    app_module._render_sse(_frames(("token", "Hello! "), ("token", "How?\n"),
                                   ("done", {})))
    out = capsys.readouterr().out
    assert "Hello! How?" in out
    assert "%" not in out  # percent-encoding never reaches the terminal


def test_render_sse_shows_tools_heartbeats_errors(capsys):
    from second_brain import app as app_module
    app_module._render_sse(_frames(
        ("tool_call", {"tool": "search_kb", "args": {"query": "drip"}}),
        ("tool_call", {"tool": "Bash",
                       "args": {"command": "brain search x",
                                "description": "search"}}),
        ("heartbeat", {"phase": "tool", "iteration": 0,
                       "label": "Running Bash"}),
        ("heartbeat", {"phase": "ready", "iteration": 0,
                       "label": "Session ready"}),
        ("heartbeat", {"phase": "seated", "iteration": 0,
                       "label": "zed joined the conversation"}),
        ("error", "lane exploded"),
        ("done", {})))
    out = capsys.readouterr().out
    assert "[search_kb] drip" in out  # humanized arg, not the JSON dump
    assert "[Bash] brain search x" in out
    assert "[Running Bash]" not in out  # duplicates the tool_call line
    assert "[Session ready]" not in out  # turn start is already visible
    assert "[zed joined the conversation]" in out
    assert "[error] lane exploded" in out
    assert "\033[" not in out  # capsys is not a tty: plain text, no ANSI


def test_first_run_writes_defaults_without_prompting(monkeypatch, tmp_path,
                                                     capsys):
    from second_brain import app as app_module, config
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    app_module._first_run_check()
    out = capsys.readouterr().out
    assert "wrote defaults" in out and "brain config" in out
    stored = config.load_file()
    assert stored["harness"] == "claude" and stored["gitignored"] == "_USER"
    # second call is silent - config exists now
    app_module._first_run_check()
    assert capsys.readouterr().out == ""


def test_backend_line_names_gap_when_nothing_installed(monkeypatch, tmp_path):
    from second_brain import app as app_module, chat
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    monkeypatch.setattr(chat, "harness_bin", lambda name: None)
    monkeypatch.setattr(chat, "ollama_tags", lambda: [])
    assert "none found" in app_module._backend_line()
    monkeypatch.setattr(chat, "harness_bin",
                        lambda name: "/usr/local/bin/claude"
                        if name == "claude" else None)
    assert "claude CLI" in app_module._backend_line()


def test_render_sse_attributes_speakers_on_attributed_frames(capsys):
    from second_brain import app as app_module
    app_module._render_sse(_frames(
        ("tool_call", {"tool": "Bash", "args": {"command": "ls"},
                       "speaker": "zed"}),
        ("token", "zed output"),
        ("seat_done", {"speaker": "zed", "state": "done"}),
        ("tool_call", {"tool": "Read", "args": {}, "speaker": "main"}),
        ("done", {})))
    out = capsys.readouterr().out
    assert out.count("[zed]") == 1 and "[main]" in out
    assert "zed output" in out


def test_cmd_chat_rejects_unknown_conversation(monkeypatch, tmp_path):
    from second_brain import app as app_module
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path))
    # pid file pointing at this process, port where nothing listens: the
    # resume probe must fail loudly instead of opening a dead REPL
    import os
    (tmp_path / "pid").write_text(f"{os.getpid()}\n9\n")
    monkeypatch.setenv("SECOND_BRAIN_PORT", "9")
    assert app_module.cmd_chat("no-such-conversation") == 1
