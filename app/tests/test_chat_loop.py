"""Lane router, Claude Code lane and Ollama lane tests. STORY-000037 (M4).

The claude subprocess is replaced by a fake whose stdout replays canned
stream-json lines, and the Ollama lane reads canned chunks through a
patched _ollama_events, so no test shells out, bills anything or needs a
daemon. Every lane has to fail loudly rather than hang.
"""

import asyncio
import json
import urllib.parse

import pytest
from asgi_client import TestClient

from agents_app import chat, config, conversations
from agents_app.app import create_app


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTS_APP_DATA", str(tmp_path))
    monkeypatch.setenv("AGENTS_APP_HARNESS", "claude")
    # Isolate from the developer's real ~/.agents-app/config (model default,
    # claude_model) so routing tests see a blank slate.
    monkeypatch.setenv("AGENTS_APP_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AGENTS_APP_CLAUDE_MODEL", raising=False)
    monkeypatch.setattr(chat, "_current_model", None)


class FakeProcess:
    def __init__(self, lines, returncode=0, stderr=b""):
        self.stdout = asyncio.StreamReader()
        for line in lines:
            self.stdout.feed_data(json.dumps(line).encode() + b"\n")
        self.stdout.feed_eof()
        self.stderr = asyncio.StreamReader()
        self.stderr.feed_data(stderr)
        self.stderr.feed_eof()
        self.returncode = returncode

    async def wait(self):
        return self.returncode


def fake_spawn(monkeypatch, lines, returncode=0, stderr=b""):
    """Patch _spawn_claude; returns the list of spawned commands. The cwd
    each spawn received rides on spawn_cwds (same indexes as commands)."""
    commands = []

    async def spawn(cmd, cwd=None, seat=None):
        commands.append(cmd)
        fake_spawn.spawn_cwds.append(cwd)
        return FakeProcess(lines, returncode, stderr)

    fake_spawn.spawn_cwds = []
    monkeypatch.setattr(chat, "_spawn_claude", spawn)
    return commands


def run_stream(message, conversation_id):
    async def gather():
        return [frame async for frame in chat.stream_chat(message, conversation_id)]
    return asyncio.run(gather())


def parse(frames):
    events = []
    for frame in frames:
        text = frame.decode()
        assert text.endswith("\n\n")
        event_line, data_line = text[:-2].split("\n")
        events.append((event_line[7:], data_line[6:]))
    return events


INIT = {"type": "system", "subtype": "init", "session_id": "sess-1"}
TEXT = {"type": "assistant",
        "message": {"content": [{"type": "text", "text": "Hello from the vault"}],
                    "usage": {"input_tokens": 90, "cache_read_input_tokens": 20,
                              "output_tokens": 10}}}
# result usage aggregates the whole turn; the driver must prefer the last
# assistant message's usage (the actual context size) over it.
RESULT = {"type": "result", "subtype": "success", "result": "Hello from the vault",
          "usage": {"input_tokens": 300_000, "output_tokens": 20},
          "session_id": "sess-1"}


# --- lane router ---

def test_router_prefers_claude_code(monkeypatch):
    monkeypatch.setattr(chat, "claude_cli", lambda: "/usr/local/bin/claude")
    assert chat.pick_lane() == "claude_code"


def test_router_falls_back_to_ollama(monkeypatch):
    monkeypatch.setattr(chat, "claude_cli", lambda: None)
    assert chat.pick_lane() == "ollama"


def test_lane_for_routes_harness_entries_and_everything_else_to_ollama():
    assert chat.lane_for("claude-code") == "claude_code"
    assert chat.lane_for("codex") == "codex"
    # a claude-looking name that is not a harness entry is not special
    assert chat.lane_for("claude-sonnet-5") == "ollama"
    assert chat.lane_for("qwen3:latest") == "ollama"


# --- claude_code lane ---

def test_cli_env_is_an_allowlist_not_a_denylist(monkeypatch):
    """R28: spawned CLIs bill the subscription - an inherited
    ANTHROPIC_API_KEY silently flips claude onto metered API billing
    (live 2026-08-27: web turns drained API credits). Every other
    provider credential is the same hazard plus a secret leak into a
    third-party CLI, so the env is built by allowlist (security review
    2026-08-29) and unknown names never reach a spawn."""
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                 "OPENAI_API_KEY", "CURSOR_API_KEY", "GH_TOKEN",
                 "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "SOME_MCP_SECRET"):
        monkeypatch.setenv(name, "leak-me")
    monkeypatch.setenv("AGENTS_APP_HOME", "/tmp/apphome")
    env = chat._cli_env()
    assert not [name for name in env if "KEY" in name or "TOKEN" in name
                or "SECRET" in name]
    assert env.get("PATH") and env.get("HOME")
    # app config still rides through, and the user-controlled escape
    # hatch passes a named extra
    assert env.get("AGENTS_APP_HOME") == "/tmp/apphome"
    monkeypatch.setenv("AGENTS_APP_SPAWN_PASSTHROUGH", "MY_HARNESS_VAR")
    monkeypatch.setenv("MY_HARNESS_VAR", "ok")
    assert chat._cli_env().get("MY_HARNESS_VAR") == "ok"


def test_error_result_is_error_frame_not_reply(monkeypatch):
    """An error result ('Credit balance is too low') surfaces as an error
    frame; it must never persist as an assistant turn."""
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    fake_spawn(monkeypatch, [INIT,
                             {"type": "result",
                              "subtype": "error_during_execution",
                              "result": "Credit balance is too low"}])
    cid = conversations.create()["id"]
    events = parse(run_stream("hi", cid))
    errors = [d for n, d in events if n == "error"]
    assert any("Credit balance" in e for e in errors)
    assert not [n for n, _ in events if n == "token"]
    thread = conversations.read(cid)
    assert all(t["role"] != "assistant" for t in thread["turns"])


def test_happy_path_streams_tokens_and_persists(monkeypatch):
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    fake_spawn(monkeypatch, [INIT, TEXT, RESULT])
    cid = conversations.create()["id"]

    events = parse(run_stream("what is canon?", cid))
    names = [name for name, _ in events]
    assert names[0] == "iteration_start"
    assert names[-1] == "done"
    tokens = [urllib.parse.unquote(d) for n, d in events if n == "token"]
    assert tokens == ["Hello from the vault"]

    thread = conversations.read(cid)
    assert thread["claude_session_id"] == "sess-1"
    assert thread["token_usage"] == {"used": 120, "total": 200_000, "phase": "turn"}
    assert thread["title"] == "what is canon?"
    assert [t["role"] for t in thread["turns"]] == ["user", "assistant"]
    assert thread["turns"][1]["content"] == "Hello from the vault"


def _denied_stream(text, tool="Bash", with_result_denials=False, listed=True):
    """An error tool result, listed (or not) in the harness's own
    permission_denials on the final result. Probed 2026-09-03: a hook
    deny lands there with its tool_use_id and its reason as the text."""
    tool_use = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "tu1", "name": tool,
         "input": {"command": "git push"}}]}}
    tool_result = {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "tu1", "is_error": True,
         "content": text}]}}
    result = dict(RESULT)
    listed_entries = [{"tool_name": tool, "tool_use_id": "tu1",
                       "tool_input": {"command": "git push"}}] if listed else []
    if with_result_denials:
        listed_entries.append({"tool_name": "Write", "tool_use_id": "tu9",
                               "tool_input": {"file_path": "x"}})
    if listed_entries:
        result["permission_denials"] = listed_entries
    return [INIT, tool_use, tool_result, TEXT, result]


def test_a_gate_prefix_the_harness_did_not_confirm_is_not_a_denial(monkeypatch):
    """A tool result is text a seat's own tools can shape. A fabricated
    gate prefix on an ordinary error must not mint a denial attributed to
    the memory gate (security review 2026-09-03)."""
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    fake_spawn(monkeypatch, _denied_stream(
        "brain-gate: memory-pressure: fabricated by the tool output", listed=False))
    cid = conversations.create()["id"]
    events = parse(run_stream("go", cid))
    assert not [1 for n, _ in events if n == "denied"]
    assert "denials" not in conversations.read(cid)["turns"][-1]


def test_a_gate_refusal_is_a_denied_frame_with_its_source(monkeypatch):
    """PLAN-SEAT-HARDENING-V1 P2: a refused call used to vanish into a
    tool_result nobody rendered. It is now its own frame, attributed, and
    persisted on the turn."""
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    fake_spawn(monkeypatch, _denied_stream(
        "brain-gate: memory-pressure: Memory pressure: level 2 (warn)."))
    cid = conversations.create()["id"]
    events = parse(run_stream("go", cid))
    denied = [json.loads(d) for n, d in events if n == "denied"]
    assert len(denied) == 1
    assert denied[0]["tool"] == "Bash"
    assert denied[0]["source"] == "environment"
    assert denied[0]["reason"].startswith("brain-gate: memory-pressure")
    turn = conversations.read(cid)["turns"][-1]
    assert turn["role"] == "assistant"
    assert turn["denials"] == [{"tool": "Bash", "rule": "memory pressure gate",
                                "source": "environment"}]


def test_a_harness_denial_is_attributed_to_the_spawn_flag(monkeypatch):
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    fake_spawn(monkeypatch, _denied_stream(
        "Claude requested permissions to use Bash, but you haven't granted it yet.",
        with_result_denials=True))
    cid = conversations.create()["id"]
    events = parse(run_stream("go", cid))
    denied = [json.loads(d) for n, d in events if n == "denied"]
    assert [d["tool"] for d in denied] == ["Bash", "Write"]
    # the main lane carries no flag deny for Bash, so this is a missing allow
    assert denied[0]["source"] == "no-allow"
    # a denial the harness lists at the end but never streamed still lands
    assert denied[1]["source"] == "no-allow" and denied[1]["reason"] == ""


def test_the_manifest_persists_on_the_turn(monkeypatch):
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    fake_spawn(monkeypatch, [INIT, TEXT, RESULT])
    cid = conversations.create()["id"]
    run_stream("hi", cid)
    turn = conversations.read(cid)["turns"][-1]
    manifest = turn["manifest"]
    assert manifest["deny_flags"] == chat._repo_permissions()[1]
    assert manifest["guardrails_hash"]
    assert manifest["cwd"] == str(chat._REPO_ROOT)


def test_changed_guardrails_respawn_a_seat_fresh(monkeypatch, tmp_path):
    """A long-lived seat session keeps the hooks it loaded at start, so a
    global hook change between turns would leave it running under old
    rules. When the manifest hash moves, the turn says so and the seat
    starts a fresh session instead of resuming."""
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    monkeypatch.setattr(chat.config, "seat_roots", lambda: [tmp_path])
    cid = conversations.create()["id"]
    seat_dir = tmp_path / "seat"
    seat_dir.mkdir()
    seat = conversations.add_participant(cid, "Scout", str(seat_dir))
    conversations.update_participant(cid, "scout", {
        "session_id": "sess-old", "guardrails_hash": "stale"})
    seat = conversations.read(cid)["participants"][0]

    commands = fake_spawn(monkeypatch, [INIT, TEXT, RESULT])
    events = parse(asyncio.run(_collect(
        chat._claude_code_lane("go", cid, seat=seat))))
    assert "--resume" not in commands[0]
    changed = [json.loads(d) for n, d in events if n == "guardrails"]
    assert changed == [{"speaker": "scout", "seat": "scout", "changed": True}]
    stored = conversations.read(cid)["participants"][0]
    assert stored["guardrails_hash"] not in ("", "stale")

    # same guardrails next turn: resumes, no frame
    seat = dict(stored, session_id="sess-new")
    commands = fake_spawn(monkeypatch, [INIT, TEXT, RESULT])
    events = parse(asyncio.run(_collect(
        chat._claude_code_lane("again", cid, seat=seat))))
    assert "--resume" in commands[0]
    assert not [1 for n, _ in events if n == "guardrails"]


async def _collect(lane):
    return [frame async for frame in lane]


def test_an_ordinary_tool_error_is_not_a_denial(monkeypatch):
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    fake_spawn(monkeypatch, _denied_stream("No such file or directory", listed=False))
    cid = conversations.create()["id"]
    events = parse(run_stream("go", cid))
    assert not [1 for n, _ in events if n == "denied"]
    assert "denials" not in conversations.read(cid)["turns"][-1]


def test_tool_turn_emits_kb_file_and_tool_events(monkeypatch):
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    vault_file = str(config.vault_path() / "KNOWLEDGE-BASE" / "a.md")
    tool_use = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "tu1", "name": "Read",
         "input": {"file_path": vault_file}}]}}
    tool_result = {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "tu1", "content": "file text"}]}}
    fake_spawn(monkeypatch, [INIT, tool_use, tool_result, TEXT, RESULT])
    cid = conversations.create()["id"]

    events = parse(run_stream("read a note", cid))
    names = [name for name, _ in events]
    for required in ("tool_call", "tool_executing", "tool_done", "tool_result"):
        assert required in names
    assert names.index("tool_call") < names.index("tool_executing") \
        < names.index("tool_done") < names.index("tool_result")

    kb_files = [json.loads(d) for n, d in events if n == "kb_file"]
    assert kb_files == [{"path": "KNOWLEDGE-BASE/a.md", "score": 1.0}]
    tool_done = next(json.loads(d) for n, d in events if n == "tool_done")
    assert tool_done["tool"] == "Read" and tool_done["executed"] is True
    tool_result_ev = next(json.loads(d) for n, d in events if n == "tool_result")
    assert tool_result_ev["result"] == "file text"
    assert tool_result_ev["info"]["delivered_chars"] == len("file text")


def test_partial_deltas_stream_without_duplication(monkeypatch):
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    start = {"type": "stream_event", "event": {"type": "message_start"}}
    d1 = {"type": "stream_event", "event": {"type": "content_block_delta",
          "delta": {"type": "text_delta", "text": "Hello from "}}}
    d2 = {"type": "stream_event", "event": {"type": "content_block_delta",
          "delta": {"type": "text_delta", "text": "the vault"}}}
    fake_spawn(monkeypatch, [INIT, start, d1, d2, TEXT, RESULT])
    cid = conversations.create()["id"]

    events = parse(run_stream("hi", cid))
    tokens = [urllib.parse.unquote(d) for n, d in events if n == "token"]
    assert tokens == ["Hello from ", "the vault"]  # full message not re-emitted
    starts = [d for n, d in events if n == "iteration_start"]
    assert len(starts) == 1  # message_start consumed by the pre-emitted block
    thread = conversations.read(cid)
    assert thread["turns"][1]["content"] == "Hello from the vault"


def test_directory_args_emit_no_kb_file(monkeypatch):
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    listing = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "tu1", "name": "Glob",
         "input": {"path": str(config.vault_path() / "KNOWLEDGE-BASE")}}]}}
    fake_spawn(monkeypatch, [INIT, listing, TEXT, RESULT])
    cid = conversations.create()["id"]
    events = parse(run_stream("list the canon", cid))
    assert not [name for name, _ in events if name == "kb_file"]


def test_claude_model_passthrough(monkeypatch):
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    monkeypatch.setenv("AGENTS_APP_CLAUDE_MODEL", "qwen3:4b")
    commands = fake_spawn(monkeypatch, [INIT, TEXT, RESULT])
    cid = conversations.create()["id"]
    run_stream("hi", cid)
    model_at = commands[0].index("--model")
    assert commands[0][model_at + 1] == "qwen3:4b"


def test_unconfigured_lane_defaults_to_sonnet_medium(monkeypatch):
    """Speed default (user decision 2026-08-27): launched claude agents
    run sonnet at medium effort unless configured otherwise."""
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    commands = fake_spawn(monkeypatch, [INIT, TEXT, RESULT])
    cid = conversations.create()["id"]
    run_stream("hi", cid)
    assert commands[0][commands[0].index("--model") + 1] == "sonnet"
    assert commands[0][commands[0].index("--effort") + 1] == "medium"


def test_config_default_model_picks_lane(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config").write_text("model = qwen3:4b\n")
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    assert chat.pick_lane() == "ollama"  # explicit default beats the harness


def test_second_turn_resumes_the_stored_session(monkeypatch):
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    commands = fake_spawn(monkeypatch, [INIT, TEXT, RESULT])
    cid = conversations.create()["id"]

    run_stream("first", cid)
    assert "--resume" not in commands[0]
    assert "--append-system-prompt" in commands[0]
    run_stream("second", cid)
    resume_at = commands[1].index("--resume")
    assert commands[1][resume_at + 1] == "sess-1"


def test_subprocess_death_emits_error_then_done(monkeypatch):
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    fake_spawn(monkeypatch, [INIT, TEXT], returncode=1, stderr=b"boom")
    cid = conversations.create()["id"]

    events = parse(run_stream("hi", cid))
    names = [name for name, _ in events]
    assert "error" in names
    assert names[-1] == "done"
    assert names.index("error") < names.index("done")
    error = next(d for n, d in events if n == "error")
    assert "boom" in error


def test_ollama_floor_without_daemon_fails_loudly(monkeypatch):
    monkeypatch.setattr(chat, "claude_cli", lambda: None)
    monkeypatch.setattr(chat, "harness_bin", lambda name: None)
    monkeypatch.setattr(chat, "ollama_tags", lambda: [])
    cid = conversations.create()["id"]

    events = parse(run_stream("hi", cid))
    names = [name for name, _ in events]
    assert "error" in names and names[-1] == "done"
    assert "Ollama" in next(d for n, d in events if n == "error")


# --- ollama lane (STORY-000039 remainder / STORY-000040) ---

def ollama_text_batch(text):
    return [
        {"message": {"role": "assistant", "content": text}, "done": False},
        {"message": {"role": "assistant", "content": ""}, "done": True,
         "prompt_eval_count": 30, "eval_count": 12},
    ]


def ollama_tool_batch():
    return [
        {"message": {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "search_kb",
                          "arguments": {"query": "certification"}}}]},
         "done": False},
        {"done": True, "prompt_eval_count": 20, "eval_count": 5},
    ]


def fake_ollama(monkeypatch, batches):
    """Patch _ollama_events; a batch is a chunk list or an exception to
    raise. Returns the recorded calls [{model, messages, tools}]."""
    calls = []

    async def events(model, messages, tool_specs):
        calls.append({"model": model,
                      "messages": json.loads(json.dumps(messages)),
                      "tools": tool_specs})
        batch = batches.pop(0)
        if isinstance(batch, Exception):
            raise batch
        for chunk in batch:
            yield chunk

    monkeypatch.setattr(chat, "_ollama_events", events)
    return calls


def ollama_lane(monkeypatch):
    monkeypatch.setattr(chat, "claude_cli", lambda: None)
    monkeypatch.setattr(chat, "harness_bin", lambda name: None)
    monkeypatch.setattr(chat, "ollama_tags", lambda: ["qwen3:latest"])


def test_ollama_lane_streams_and_persists(monkeypatch):
    ollama_lane(monkeypatch)
    calls = fake_ollama(monkeypatch, [ollama_text_batch("Hello offline")])
    cid = conversations.create()["id"]

    events = parse(run_stream("what is canon?", cid))
    names = [name for name, _ in events]
    assert names[0] == "iteration_start" and names[-1] == "done"
    tokens = [urllib.parse.unquote(d) for n, d in events if n == "token"]
    assert tokens == ["Hello offline"]
    assert calls[0]["model"] == "qwen3:latest"
    assert calls[0]["tools"], "first call attaches the KB tools"

    thread = conversations.read(cid)
    assert thread["token_usage"] == {"used": 42, "total": 200_000,
                                     "phase": "turn"}
    assert thread["turns"][1]["content"] == "Hello offline"


def test_ollama_tool_loop_events_and_followup(monkeypatch):
    ollama_lane(monkeypatch)
    calls = fake_ollama(monkeypatch,
                        [ollama_tool_batch(), ollama_text_batch("Certified.")])
    monkeypatch.setattr(chat.tools, "execute", lambda name, args: {
        "result": [{"path": "KNOWLEDGE-BASE/a.md"}],
        "info": {"hits": 1},
        "kb_files": [{"path": "KNOWLEDGE-BASE/a.md", "score": 2.5}],
    })
    cid = conversations.create()["id"]

    events = parse(run_stream("search the canon", cid))
    names = [name for name, _ in events]
    assert names.index("tool_call") < names.index("tool_executing") \
        < names.index("tool_done") < names.index("tool_result")
    kb_files = [json.loads(d) for n, d in events if n == "kb_file"]
    assert kb_files == [{"path": "KNOWLEDGE-BASE/a.md", "score": 2.5}]

    followup = calls[1]["messages"]
    assert followup[-2]["role"] == "assistant"
    assert followup[-2]["tool_calls"][0]["function"]["name"] == "search_kb"
    assert followup[-1]["role"] == "tool"


def test_ollama_degrades_to_plain_chat_without_tool_support(monkeypatch):
    ollama_lane(monkeypatch)
    calls = fake_ollama(monkeypatch, [
        chat.ollama.OllamaError(400, "qwen2:0.5b does not support tools"),
        ollama_text_batch("plain answer"),
    ])
    cid = conversations.create()["id"]

    events = parse(run_stream("hi", cid))
    names = [name for name, _ in events]
    assert "error" not in names and names[-1] == "done"
    heartbeats = [json.loads(d) for n, d in events if n == "heartbeat"]
    assert any(h["phase"] == "degrade" for h in heartbeats)
    tokens = [urllib.parse.unquote(d) for n, d in events if n == "token"]
    assert tokens == ["plain answer"]
    assert calls[0]["tools"] and calls[1]["tools"] is None


def test_ollama_provider_error_emits_error_then_done(monkeypatch):
    ollama_lane(monkeypatch)
    fake_ollama(monkeypatch, [chat.ollama.OllamaError(500, "boom")])
    cid = conversations.create()["id"]

    events = parse(run_stream("hi", cid))
    names = [name for name, _ in events]
    assert "error" in names and names[-1] == "done"
    assert "boom" in next(d for n, d in events if n == "error")


def test_ollama_tool_error_is_reported_not_executed(monkeypatch):
    ollama_lane(monkeypatch)
    batch = ollama_tool_batch()
    batch[0]["message"]["tool_calls"] = [
        {"function": {"name": "read_file", "arguments": {"filename": "../x"}}}]
    calls = fake_ollama(monkeypatch, [batch, ollama_text_batch("Blocked.")])
    cid = conversations.create()["id"]

    events = parse(run_stream("read something", cid))
    tool_done = next(json.loads(d) for n, d in events if n == "tool_done")
    assert tool_done["executed"] is False
    assert calls[1]["messages"][-1]["role"] == "tool"
    assert [name for name, _ in events][-1] == "done"


def test_ollama_tool_budget_cutoff(monkeypatch):
    ollama_lane(monkeypatch)
    monkeypatch.setattr(chat, "_TOOL_BUDGET", 1)
    fake_ollama(monkeypatch, [ollama_tool_batch(), ollama_tool_batch(),
                              ollama_text_batch("never reached")])
    monkeypatch.setattr(chat.tools, "execute", lambda name, args: {
        "result": "x", "info": {}, "kb_files": []})
    cid = conversations.create()["id"]

    events = parse(run_stream("loop forever", cid))
    names = [name for name, _ in events]
    assert "error" in names and names[-1] == "done"
    assert "budget" in next(d for n, d in events if n == "error")


def test_ollama_history_is_token_bounded(monkeypatch):
    ollama_lane(monkeypatch)
    monkeypatch.setattr(chat, "_HISTORY_CHAR_BUDGET", 40)
    calls = fake_ollama(monkeypatch, [ollama_text_batch("ok")])
    cid = conversations.create()["id"]
    conversations.append_turn(cid, "user", "x" * 500)
    conversations.append_turn(cid, "assistant", "y" * 500)

    run_stream("recent question", cid)
    sent = calls[0]["messages"]
    assert sent[-1] == {"role": "user", "content": "recent question"}
    assert len(sent) < 3  # the oversized turns fell out of the window
    assert sent[0]["role"] == "user"


# --- endpoints ---

def test_chat_endpoint_streams_sse(monkeypatch):
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    fake_spawn(monkeypatch, [INIT, TEXT, RESULT])
    client = TestClient(create_app())
    cid = client.post("/conversations").json()["id"]

    r = client.post("/chat", json={"message": "hi", "conversation_id": cid})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert "event: done" in r.text


def test_chat_endpoint_rejects_bad_requests():
    client = TestClient(create_app())
    assert client.post("/chat", json={"message": "hi",
                                      "conversation_id": "nope"}).status_code == 404
    cid = client.post("/conversations").json()["id"]
    assert client.post("/chat", json={"message": "",
                                      "conversation_id": cid}).status_code == 422


def test_ambient_sse_requires_token():
    client = TestClient(create_app())
    assert client.get("/sse").status_code == 422


# --- model picker (/models, /model) ---

def _only_claude(name):
    return "/usr/local/bin/claude" if name == "claude" else None


def test_models_merges_lanes(monkeypatch):
    monkeypatch.setattr(chat, "harness_bin", _only_claude)
    monkeypatch.setattr(chat, "ollama_tags", lambda: ["qwen3:latest"])
    body = TestClient(create_app()).get("/models").json()
    assert body["models"] == ["claude-code", "qwen3:latest"]
    assert body["current"] == "claude-code"


def test_models_without_cli_or_ollama(monkeypatch):
    monkeypatch.setattr(chat, "harness_bin", lambda name: None)
    monkeypatch.setattr(chat, "ollama_tags", lambda: [])
    body = TestClient(create_app()).get("/models").json()
    assert body == {"models": [], "current": ""}


def test_models_without_cli_default_to_first_ollama_tag(monkeypatch):
    monkeypatch.setattr(chat, "harness_bin", lambda name: None)
    monkeypatch.setattr(chat, "ollama_tags",
                        lambda: ["qwen3:latest", "llama3:8b"])
    body = TestClient(create_app()).get("/models").json()
    assert body == {"models": ["qwen3:latest", "llama3:8b"],
                    "current": "qwen3:latest"}


def test_model_switch_routes_lanes(monkeypatch):
    monkeypatch.setattr(chat, "harness_bin", _only_claude)
    monkeypatch.setattr(chat, "ollama_tags", lambda: ["qwen3:latest"])
    client = TestClient(create_app())

    assert client.post("/model", json={"model": "qwen3:latest"}).status_code == 200
    assert chat.pick_lane() == "ollama"
    assert client.post("/model", json={"model": "claude-code"}).status_code == 200
    assert chat.pick_lane() == "claude_code"
    # a claude model name is no longer a listed lane of its own
    assert client.post("/model", json={"model": "claude-sonnet-5"}).status_code == 422
    assert chat.pick_lane() == "claude_code"


def test_model_switch_rejects_unknown(monkeypatch):
    monkeypatch.setattr(chat, "harness_bin", _only_claude)
    monkeypatch.setattr(chat, "ollama_tags", lambda: [])
    client = TestClient(create_app())
    assert client.post("/model", json={"model": "gpt-99"}).status_code == 422
    assert chat._current_model is None


# --- seat-parameterized claude lane (STORY-000075) ---

def run_seat_lane(seat, cid, message="hi"):
    async def gather():
        return [frame async for frame in
                chat._claude_code_lane(message, cid, seat=seat)]
    return asyncio.run(gather())


def test_seat_lane_uses_cwd_model_and_session_ref(monkeypatch):
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    commands = fake_spawn(monkeypatch, [INIT, TEXT, RESULT])
    cid = conversations.create()["id"]
    conversations.append_turn(cid, "user", "hi", speaker="user")
    seat = conversations.add_participant(cid, "Scribe", "/tmp/arch-repo",
                                         model="claude-opus-5")

    events = parse(run_seat_lane(seat, cid))
    assert fake_spawn.spawn_cwds[0] == "/tmp/arch-repo"
    model_at = commands[0].index("--model")
    assert commands[0][model_at + 1] == "claude-opus-5"
    assert "--resume" not in commands[0]

    # session ref lands on the seat, not claude_session_id
    thread = conversations.read(cid)
    assert thread["participants"][0]["session_id"] == "sess-1"
    assert "claude_session_id" not in thread

    # second seat turn resumes the seat's own session
    seat = thread["participants"][0]
    run_seat_lane(seat, cid)
    resume_at = commands[1].index("--resume")
    assert commands[1][resume_at + 1] == "sess-1"


def test_seat_defaults_are_cheaper_than_the_main_lane(monkeypatch):
    """Seat speed default (user decision 2026-08-29): a seat with no model
    or effort of its own runs sonnet/low - main's model, less thinking -
    while the two-party lane keeps sonnet/medium."""
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    commands = fake_spawn(monkeypatch, [INIT, TEXT, RESULT])
    cid = conversations.create()["id"]
    conversations.append_turn(cid, "user", "hi", speaker="user")
    seat = conversations.add_participant(cid, "Scout", "/tmp/scout-repo")

    run_seat_lane(seat, cid)
    assert commands[0][commands[0].index("--model") + 1] == chat.SEAT_MODEL
    assert commands[0][commands[0].index("--effort") + 1] == chat.SEAT_EFFORT
    assert (chat.SEAT_MODEL, chat.SEAT_EFFORT) == ("sonnet", "low")


def test_seat_effort_override_beats_the_seat_default(monkeypatch):
    """A seat that needs to think harder says so; its own effort wins over
    the seat default and is never overridden by the main lane's setting."""
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    commands = fake_spawn(monkeypatch, [INIT, TEXT, RESULT])
    cid = conversations.create()["id"]
    conversations.append_turn(cid, "user", "hi", speaker="user")
    seat = conversations.add_participant(cid, "Scribe", "/tmp/arch-repo",
                                         model="claude-opus-5", effort="high")

    run_seat_lane(seat, cid)
    assert commands[0][commands[0].index("--model") + 1] == "claude-opus-5"
    assert commands[0][commands[0].index("--effort") + 1] == "high"


def test_seat_frames_carry_speaker_and_turn_is_attributed(monkeypatch):
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    fake_spawn(monkeypatch, [INIT, TEXT, RESULT])
    cid = conversations.create()["id"]
    seat = conversations.add_participant(cid, "Scout", "/tmp/scout")

    events = parse(run_seat_lane(seat, cid))
    first = json.loads(next(d for n, d in events if n == "iteration_start"))
    assert first["speaker"] == "scout" and first["speaker_name"] == "Scout"
    usage = json.loads(next(d for n, d in events if n == "token_usage"))
    assert usage["speaker"] == "scout"

    turns = conversations.read(cid)["turns"]
    assert turns[-1]["speaker"] == "scout"
    assert turns[-1]["content"] == "Hello from the vault"


def test_seatless_lane_emits_no_speaker(monkeypatch):
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    fake_spawn(monkeypatch, [INIT, TEXT, RESULT])
    cid = conversations.create()["id"]
    events = parse(run_stream("hi", cid))
    for name, data in events:
        if name in ("iteration_start", "token_usage", "heartbeat"):
            assert "speaker" not in json.loads(data)


# --- per-conversation model pin (advisor decision 2026-08-27) ---

def test_conversation_pin_outranks_process_pin(monkeypatch):
    monkeypatch.setattr(chat, "harness_bin", _only_claude)
    monkeypatch.setattr(chat, "ollama_tags", lambda: ["qwen3:latest"])
    client = TestClient(create_app())
    cid = client.post("/conversations").json()["id"]

    assert client.post("/model", json={"model": "claude-code"}).status_code == 200
    r = client.post("/model", json={"model": "qwen3:latest",
                                    "conversation_id": cid})
    assert r.status_code == 200
    assert conversations.read(cid)["model"] == "qwen3:latest"
    assert chat._current_model == "claude-code"  # process pin untouched

    # The pinned thread routes to the Ollama lane while the process
    # default stays claude-code for other conversations.
    calls = fake_ollama(monkeypatch, [ollama_text_batch("pinned")])
    run_stream("hi", cid)
    assert calls[0]["model"] == "qwen3:latest"


def test_conversation_pin_validates_model_and_thread(monkeypatch):
    monkeypatch.setattr(chat, "harness_bin", _only_claude)
    monkeypatch.setattr(chat, "ollama_tags", lambda: [])
    client = TestClient(create_app())
    cid = client.post("/conversations").json()["id"]
    assert client.post("/model", json={"model": "gpt-99",
                                       "conversation_id": cid}).status_code == 422
    assert client.post("/model", json={"model": "claude-code",
                                       "conversation_id": "nope"}).status_code == 404
    assert "model" not in conversations.read(cid)


def test_conversation_pin_routes_ollama_thread(monkeypatch):
    ollama_lane(monkeypatch)
    calls = fake_ollama(monkeypatch, [ollama_text_batch("local")])
    cid = conversations.create()["id"]
    conversations.update(cid, {"model": "qwen3:latest"})
    run_stream("hi", cid)
    assert calls[0]["model"] == "qwen3:latest"


# --- harness registry (R33) ---

def test_configured_harness_picks_its_lane(monkeypatch):
    monkeypatch.setenv("AGENTS_APP_HARNESS", "codex")
    monkeypatch.setattr(chat, "harness_bin",
                        lambda name: "/usr/local/bin/codex" if name == "codex" else None)
    assert chat.pick_lane() == "codex"


def test_absent_harness_falls_through_the_ladder(monkeypatch):
    monkeypatch.setenv("AGENTS_APP_HARNESS", "codex")
    monkeypatch.setattr(chat, "harness_bin", lambda name: None)
    assert chat.pick_lane() == "ollama"


def test_unbuilt_harness_driver_fails_loudly(monkeypatch):
    monkeypatch.setenv("AGENTS_APP_HARNESS", "codex")
    monkeypatch.setattr(chat, "harness_bin",
                        lambda name: "/usr/local/bin/codex" if name == "codex" else None)
    cid = conversations.create()["id"]
    events = parse(run_stream("hi", cid))
    assert [name for name, _ in events] == ["error", "done"]
    assert "codex" in events[0][1] and "AGENTS.md" in events[0][1]


def test_present_harnesses_surface_in_models(monkeypatch):
    monkeypatch.setattr(chat, "harness_bin",
                        lambda name: "/bin/x" if name in ("claude", "codex") else None)
    monkeypatch.setattr(chat, "ollama_tags", lambda: [])
    body = TestClient(create_app()).get("/models").json()
    assert "claude-code" in body["models"] and "codex" in body["models"]
    assert body["current"] == "claude-code"
