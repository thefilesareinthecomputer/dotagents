"""What a seat turn loses silently, made observable.

Probed 2026-09-02 (claude 2.1.258): a committed .claude/settings.json's
allow rules apply only where the user's claude install has trusted the
workspace. Elsewhere the CLI drops them and says so on stderr, which the
spawner used to read only when a turn failed. These rows cover the three
paths that surface it: the stderr warning frame, the spawn-time notice,
and the denial source that names the lost allowlist.
"""

import asyncio
import json
from pathlib import Path

import pytest

from second_brain import chat, conversations

TRUST_WARNING = ("Ignoring 7 permissions.allow entries because this "
                 "workspace has not been trusted")

INIT = {"type": "system", "subtype": "init", "session_id": "sess-1"}
TEXT = {"type": "assistant",
        "message": {"content": [{"type": "text", "text": "done"}]}}
RESULT = {"type": "result", "subtype": "success", "result": "done"}
TURN = [INIT, TEXT, RESULT]


class FakeProcess:
    """Canned stream-json on stdout, canned bytes on stderr."""

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

    def kill(self):
        self.returncode = -9


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SECOND_BRAIN_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(chat.config, "seat_roots", lambda: [tmp_path])


def fake_spawn(monkeypatch, lines=TURN, stderr=b""):
    async def spawn(cmd, cwd=None, seat=None):
        return FakeProcess(lines, 0, stderr)

    monkeypatch.setattr(chat, "_spawn_claude", spawn)


def parse(frames):
    events = []
    for frame in frames:
        text = frame.decode()
        event_line, data_line = text[:-2].split("\n", 1)
        events.append((event_line[7:], data_line[6:]))
    return events


def seated(tmp_path, name="Scout", allows=None):
    """A conversation with one seat in its own directory, optionally
    carrying a committed allowlist."""
    cwd = tmp_path / name.lower()
    cwd.mkdir(exist_ok=True)
    if allows is not None:
        (cwd / ".claude").mkdir(exist_ok=True)
        (cwd / ".claude" / "settings.json").write_text(
            json.dumps({"permissions": {"allow": allows}}))
    cid = conversations.create()["id"]
    seat = conversations.add_participant(cid, name, str(cwd))
    return cid, seat


def run_lane(message, cid, seat):
    async def drive():
        return [frame async for frame in
                chat._claude_code_lane(message, cid, seat=seat)]
    return parse(asyncio.run(drive()))


def test_stderr_warnings_reach_a_frame_and_the_turn(monkeypatch, tmp_path):
    """A finished turn used to drop stderr entirely, so a seat that lost
    its whole allowlist looked like a seat that had one."""
    monkeypatch.setattr(chat, "_trusted", lambda cwd: True)
    cid, seat = seated(tmp_path)
    fake_spawn(monkeypatch, stderr=(TRUST_WARNING + "\n"
                                    "some other note\n").encode())

    events = run_lane("go", cid, seat)
    warnings = [json.loads(data) for name, data in events if name == "warnings"]
    assert len(warnings) == 1, "one warnings frame per turn, no more"
    assert warnings[0]["seat"] == seat["id"]
    assert warnings[0]["truncated"] is False
    assert warnings[0]["lines"][0] == TRUST_WARNING
    assert "some other note" in warnings[0]["lines"]

    turn = conversations.read(cid)["turns"][-1]
    assert turn["warnings"] == warnings[0]["lines"]


def test_a_quiet_turn_carries_no_warnings(monkeypatch, tmp_path):
    monkeypatch.setattr(chat, "_trusted", lambda cwd: True)
    cid, seat = seated(tmp_path)
    fake_spawn(monkeypatch, stderr=b"   \n\n")

    events = run_lane("go", cid, seat)
    assert not [name for name, _ in events if name == "warnings"]
    assert "warnings" not in conversations.read(cid)["turns"][-1]


def test_warning_lines_are_capped(monkeypatch, tmp_path):
    monkeypatch.setattr(chat, "_trusted", lambda cwd: True)
    cid, seat = seated(tmp_path)
    noise = "\n".join(f"line {n}" for n in range(40)) + "\n" + "x" * 500
    fake_spawn(monkeypatch, stderr=noise.encode())

    events = run_lane("go", cid, seat)
    payload = [json.loads(data) for name, data in events if name == "warnings"][0]
    assert len(payload["lines"]) == 20
    assert max(len(line) for line in payload["lines"]) <= 300
    assert payload["truncated"] is True


def test_the_untrusted_notice_fires_only_when_allows_are_lost(monkeypatch,
                                                              tmp_path):
    """Three states, one frame: allows in a workspace this machine has
    not trusted. A trusted workspace and a seat with no committed
    allowlist say nothing."""
    fake_spawn(monkeypatch)

    monkeypatch.setattr(chat, "_trusted", lambda cwd: False)
    cid, seat = seated(tmp_path, "Scout", allows=["Bash(brain search:*)",
                                                  "Read(./**)"])
    notices = [json.loads(data) for name, data in run_lane("go", cid, seat)
               if name == "notice"]
    assert len(notices) == 1
    assert notices[0]["kind"] == "untrusted-committed-allow"
    assert notices[0]["seat"] == seat["id"]
    assert notices[0]["count"] == 2
    assert notices[0]["text"] == (
        f"2 committed allow rules in {seat['cwd']}/.claude/settings.json "
        "are ignored because the workspace is not trusted on this device")

    monkeypatch.setattr(chat, "_trusted", lambda cwd: True)
    assert not [name for name, _ in run_lane("go", cid, seat)
                if name == "notice"]

    monkeypatch.setattr(chat, "_trusted", lambda cwd: False)
    bare_cid, bare = seated(tmp_path, "Bare")
    assert not [name for name, _ in run_lane("go", bare_cid, bare)
                if name == "notice"]
    empty_cid, empty = seated(tmp_path, "Empty", allows=[])
    assert not [name for name, _ in run_lane("go", empty_cid, empty)
                if name == "notice"]


def test_the_spawner_never_writes_the_trust_file(monkeypatch, tmp_path):
    """The notice reports; it must never auto-trust anything."""
    home = tmp_path / "fakehome"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    fake_spawn(monkeypatch)
    cid, seat = seated(tmp_path, "Scout", allows=["Bash(ls:*)"])

    run_lane("go", cid, seat)
    assert not (home / ".claude.json").exists()


def _seat_dir(tmp_path, allows):
    cwd = tmp_path / "repo"
    (cwd / ".claude").mkdir(parents=True, exist_ok=True)
    (cwd / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": allows}}))
    return str(cwd)


def test_classify_denial_names_a_lost_committed_allow(monkeypatch, tmp_path):
    """A seat denied for a call its own repo allows has hit the trust
    gate, not a missing rule - and the two read identically to the model."""
    cwd = _seat_dir(tmp_path, ["Bash(brain search:*)", "Read(./**)"])
    call = {"command": "brain search vault notes"}

    monkeypatch.setattr(chat, "_trusted", lambda path: False)
    assert chat.classify_denial("Bash", "", [], cwd=cwd, tool_input=call) == \
        ("untrusted-committed-allow", "Bash(brain search:*)")
    assert chat.classify_denial("Read", "", [], cwd=cwd,
                                tool_input={"file_path": "x.md"}) == \
        ("untrusted-committed-allow", "Read(./**)")

    # a trusted workspace keeps the old answer, and so does an unrelated
    # command, an unlisted tool, and a call with no cwd to check
    monkeypatch.setattr(chat, "_trusted", lambda path: True)
    assert chat.classify_denial("Bash", "", [], cwd=cwd, tool_input=call) == \
        ("no-allow", "")
    monkeypatch.setattr(chat, "_trusted", lambda path: False)
    assert chat.classify_denial("Bash", "", [], cwd=cwd,
                                tool_input={"command": "rm -rf /"}) == \
        ("no-allow", "")
    assert chat.classify_denial("WebFetch", "", [], cwd=cwd,
                                tool_input={}) == ("no-allow", "")
    assert chat.classify_denial("Bash", "", [], tool_input=call) == \
        ("no-allow", "")


def test_a_deny_rule_and_a_gate_still_win_over_the_trust_gate(monkeypatch,
                                                              tmp_path):
    """Lost allows explain a denial only when nothing denied the call:
    a deny flag beats an allow in the harness's model, so it beats this
    attribution too."""
    cwd = _seat_dir(tmp_path, ["Bash(git reset:*)"])
    monkeypatch.setattr(chat, "_trusted", lambda path: False)
    call = {"command": "git reset --hard"}
    assert chat.classify_denial("Bash", "", ["Bash(git reset:*)"],
                                cwd=cwd, tool_input=call) == \
        ("spawn-flag", "Bash(git reset:*)")
    assert chat.classify_denial(
        "Bash", "brain-gate: memory-pressure: level 2", [],
        cwd=cwd, tool_input=call) == ("environment", "memory pressure gate")


def test_stderr_warnings_orders_permission_notes_first():
    text = ("compiling\n"
            "  \n"
            "Ignoring 3 permissions.allow entries\n"
            "note: wildcard before the last segment\n")
    lines, truncated = chat.stderr_warnings(text)
    assert truncated is False
    assert lines[:2] == ["Ignoring 3 permissions.allow entries",
                         "note: wildcard before the last segment"]
    assert lines[2] == "compiling"
    assert chat.stderr_warnings("") == ([], False)
