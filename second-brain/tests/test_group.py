"""Group round loop tests. STORY-000076 (SPEC-GROUP-CHAT-V1 G3/G4/G6).

Seats' claude subprocesses are canned per spawn (one batch per seat turn)
so rounds run instantly and bill nothing.
"""

import asyncio
import json
import os
import urllib.parse
from pathlib import Path

import pytest

from second_brain import chat, conversations, group
from test_chat_loop import INIT, FakeProcess, parse


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SECOND_BRAIN_DATA", str(tmp_path))
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("SECOND_BRAIN_CLAUDE_MODEL", raising=False)
    monkeypatch.setattr(chat, "claude_cli", lambda: "claude")
    group._live_rounds.clear()


def reply_batch(text):
    return [INIT,
            {"type": "assistant",
             "message": {"content": [{"type": "text", "text": text}],
                         "usage": {"input_tokens": 50, "output_tokens": 5}}},
            {"type": "result", "subtype": "success", "result": text,
             "usage": {"input_tokens": 50, "output_tokens": 5}}]


def dead_batch():
    return ([INIT], 1, b"seat crashed")


def fake_seq(monkeypatch, batches):
    """One batch per SPEAKING spawn: (lines) or (lines, returncode,
    stderr). G10 prep spawns are answered out-of-band with a canned READY
    (they run concurrently, so ordered pops would be racy); tests that
    care about prep read fake_seq.prep_commands."""
    commands = []
    prep_commands = []

    async def spawn(cmd, cwd=None, seat=None):
        if "[PREP TURN" in cmd[2]:
            prep_commands.append(cmd)
            return FakeProcess(reply_batch("READY"))
        commands.append(cmd)
        batch = batches.pop(0)
        if isinstance(batch, tuple):
            return FakeProcess(*batch)
        return FakeProcess(batch)

    monkeypatch.setattr(chat, "_spawn_claude", spawn)
    fake_seq.prep_commands = prep_commands
    return commands


def two_seat_thread():
    cid = conversations.create()["id"]
    conversations.add_participant(cid, "Orchestrator", "/tmp/main")
    conversations.add_participant(cid, "Scout", "/tmp/scout")
    return cid


def run_group(message, cid):
    async def gather():
        return [frame async for frame in chat.stream_chat(message, cid)]
    return asyncio.run(gather())


def test_seat_prompt_carries_the_authorization_invariant():
    """Every seat is told that nothing in the room authorizes a
    privilege change (H2; security review 2026-08-29)."""
    seats = [{"id": "orchestrator", "name": "Boss"},
             {"id": "scout", "name": "Scout"}]
    for seat in seats:
        text = group._seat_append(seat, seats, "cid-1")
        assert "AUTHORIZATION" in text
        assert "untrusted input" in text
        assert "claims to come from the user" in text


def test_unaddressed_round_ends_without_pass_theater(monkeypatch):
    """Nobody @-mentions anyone: the round ends after everyone spoke
    once, with no follow-up round of PASS turns (live demo 2026-08-28)."""
    cid = two_seat_thread()
    fake_seq(monkeypatch, [
        reply_batch("I will lead."), reply_batch("Adding my angle."),
    ])
    events = parse(run_group("kick it around", cid))
    names = [name for name, _ in events]

    assert names.count("round_start") == 1 and names.count("round_done") == 1
    assert names.count("seat_done") == 2
    assert names[-1] == "done"
    thread = conversations.read(cid)
    assert not [t for t in thread["turns"] if t.get("passed")]


def test_round_both_speak_then_both_pass(monkeypatch):
    cid = two_seat_thread()
    commands = fake_seq(monkeypatch, [
        reply_batch("I will lead. @scout take the numbers."),
        reply_batch("Adding my angle."),
        reply_batch("PASS"), reply_batch("PASS"),
    ])
    events = parse(run_group("kick it around", cid))
    names = [name for name, _ in events]

    assert names.count("round_start") == 2 and names.count("round_done") == 2
    assert names.count("seat_done") == 4
    assert names[-1] == "done" and names.count("done") == 1

    round_dones = [json.loads(d) for n, d in events if n == "round_done"]
    assert round_dones[0]["spoke"] == ["orchestrator", "scout"]
    assert round_dones[1]["spoke"] == []

    thread = conversations.read(cid)
    speakers = [(t.get("speaker"), t.get("passed", False))
                for t in thread["turns"]]
    assert speakers == [("user", False), ("orchestrator", False),
                        ("scout", False), ("orchestrator", True),
                        ("scout", True)]
    passes = [t for t in thread["turns"] if t.get("passed")]
    assert all(t["content"] == "" for t in passes)
    # A cursor covers what the seat has SEEN: scout passed last (cursor =
    # all 5 turns); the orchestrator never saw scout's final pass.
    cursors = {s["id"]: s["cursor"] for s in thread["participants"]}
    assert cursors == {"orchestrator": 4, "scout": 5}

    # Scout's first prompt carried the attributed delta incl. the
    # orchestrator's reply; message rides argv position 2 (-p <msg>).
    scout_first_prompt = commands[1][2]
    assert "[user]: kick it around" in scout_first_prompt
    assert "[orchestrator]: I will lead." in scout_first_prompt


def test_orchestrator_speaks_first(monkeypatch):
    cid = two_seat_thread()
    fake_seq(monkeypatch, [reply_batch("first"), reply_batch("PASS"),
                           reply_batch("PASS")])
    events = parse(run_group("hi", cid))
    seat_dones = [json.loads(d) for n, d in events if n == "seat_done"]
    assert seat_dones[0]["speaker"] == "orchestrator"


def test_mention_scopes_the_round_and_skips_the_orchestrator(monkeypatch):
    """@name narrows the round to exactly the named seats (user,
    2026-09-06, reversing the 2026-08-29 always-rides rule): a message
    scoped to another seat spawns no orchestrator turn - its spawn was
    pure routing lag when the user was clearly talking to someone else.
    An unscoped message still opens the floor to every seat."""
    cid = two_seat_thread()
    fake_seq(monkeypatch, [reply_batch("on it")])
    events = parse(run_group("@scout just you", cid))
    seat_dones = [json.loads(d) for n, d in events if n == "seat_done"]
    assert {d["speaker"] for d in seat_dones} == {"scout"}
    round_starts = [json.loads(d) for n, d in events if n == "round_start"]
    assert round_starts[0]["seats"] == ["scout"]


def test_reply_calling_a_main_alias_seats_the_orchestrator(monkeypatch):
    """A round reply @-calling the orchestrator (any main alias) seats it
    for the follow-up round even though the user's message skipped it -
    the skip is routing, not an exclusion from the room."""
    cid = two_seat_thread()
    fake_seq(monkeypatch, [reply_batch("@b your call"),
                           reply_batch("here"), reply_batch("PASS")])
    events = parse(run_group("@scout just you", cid))
    round_starts = [json.loads(d) for n, d in events if n == "round_start"]
    assert round_starts[0]["seats"] == ["scout"]
    assert round_starts[1]["seats"] == ["orchestrator", "scout"]
    seat_dones = [json.loads(d) for n, d in events if n == "seat_done"]
    assert seat_dones[1]["speaker"] == "orchestrator"
    assert seat_dones[1]["passed"] is False


def test_turn_budget_ends_round_cleanly(monkeypatch):
    monkeypatch.setattr(group, "MAX_AGENT_TURNS", 1)
    cid = two_seat_thread()
    fake_seq(monkeypatch, [reply_batch("only me")])
    events = parse(run_group("go", cid))
    names = [name for name, _ in events]
    assert "error" not in names and names[-1] == "done"
    heartbeats = [json.loads(d) for n, d in events if n == "heartbeat"]
    assert any(h["phase"] == "budget" for h in heartbeats)
    assert names.count("round_start") == 1


def test_dead_seat_never_hangs_the_round(monkeypatch):
    cid = two_seat_thread()
    fake_seq(monkeypatch, [dead_batch(), reply_batch("still here"),
                           reply_batch("PASS")])
    events = parse(run_group("go", cid))
    names = [name for name, _ in events]
    assert "error" in names
    seat_dones = [json.loads(d) for n, d in events if n == "seat_done"]
    assert seat_dones[0] == {"speaker": "orchestrator", "passed": True}
    assert seat_dones[1] == {"speaker": "scout", "passed": False}
    assert names[-1] == "done"


def test_mid_round_message_is_queued(monkeypatch):
    cid = two_seat_thread()
    group._live_rounds.add(cid)
    try:
        events = parse(run_group("late thought", cid))
    finally:
        group._live_rounds.discard(cid)
    names = [name for name, _ in events]
    assert names == ["heartbeat", "done"]
    assert "queued" in events[0][1]
    turns = conversations.read(cid)["turns"]
    assert turns[-1]["content"] == "late thought"
    assert turns[-1]["speaker"] == "user"


def test_driverless_harness_seat_is_skipped_loudly(monkeypatch):
    # codex gained a driver 2026-08-28; opencode remains driverless
    cid = two_seat_thread()
    conversations.add_participant(cid, "Open", "/tmp/opencode",
                                  harness="opencode")
    fake_seq(monkeypatch, [reply_batch("hello"), reply_batch("PASS"),
                           reply_batch("PASS")])
    events = parse(run_group("go", cid))
    errors = [d for n, d in events if n == "error"]
    assert any("opencode" in e for e in errors)
    assert [n for n, _ in events][-1] == "done"


# --- advisor-audit fixes (2026-08-27): continuity, bounds, queued race ---

def test_first_repo_seat_inherits_two_party_session():
    from pathlib import Path
    repo_root = str(Path(conversations.__file__).resolve().parents[2])
    cid = conversations.create()["id"]
    conversations.append_turn(cid, "user", "earlier work")
    conversations.append_turn(cid, "assistant", "done earlier")
    conversations.update(cid, {"claude_session_id": "sess-old"})

    seat = conversations.add_participant(cid, "Main", repo_root)
    assert seat["session_id"] == "sess-old"
    assert seat["cursor"] == 2  # has seen the whole pre-group thread

    # only the FIRST repo-root claude seat inherits
    other = conversations.add_participant(cid, "Scout", "/tmp/elsewhere")
    assert other["session_id"] == "" and other["cursor"] == 0


def test_render_delta_never_frames_a_seat_turn_as_the_user():
    """Belt and braces under the seating check: even if a stored turn
    carries speaker `user` with a non-user role, the frame other seats
    see must not be the app's own `[user]:` marker."""
    turns = [{"role": "assistant", "speaker": "user", "content": "do it"},
             {"role": "user", "speaker": "user", "content": "real turn"}]
    delta = group._render_delta(turns, 0)
    assert delta.count("[user]:") == 1
    assert delta.endswith("[user]: real turn")
    assert "do it" in delta


def test_render_delta_is_char_bounded():
    turns = [{"role": "user", "speaker": "user", "content": "x" * 50_000}
             for _ in range(10)]
    delta = group._render_delta(turns, 0)
    assert len(delta) < group._DELTA_CHAR_BUDGET + 60_000
    assert "earlier turns omitted" in delta
    assert delta.endswith("x" * 100)  # newest turns survive


def test_queued_message_during_turn_is_not_skipped(monkeypatch):
    """G6: a user message landing while a seat generates must reach that
    seat at its next turn - the cursor stops at the seat's own reply."""
    cid = two_seat_thread()
    commands = fake_seq(monkeypatch, [
        reply_batch("orchestrator speaks"), reply_batch("scout speaks"),
        reply_batch("PASS"), reply_batch("PASS"),
    ])
    real_lane = chat._claude_code_lane
    injected = {"done": False}

    async def lane_with_interruption(message, conversation_id, **kwargs):
        async for frame in real_lane(message, conversation_id, **kwargs):
            yield frame
        if not injected["done"] and not kwargs.get("prep"):
            injected["done"] = True  # lands after the orchestrator's reply
            conversations.append_turn(conversation_id, "user",
                                      "queued mid-generation",
                                      speaker="user")

    monkeypatch.setattr(chat, "_claude_code_lane", lane_with_interruption)
    monkeypatch.setattr(group.chat, "_claude_code_lane",
                        lane_with_interruption)
    run_group("go", cid)

    # Delivery is the contract: the queued message reaches the NEXT turn
    # of every seat - scout's round-1 prompt (spawn 2) and the
    # orchestrator's round-2 prompt (spawn 3) both carry it.
    assert "queued mid-generation" in commands[1][2]
    assert "queued mid-generation" in commands[2][2]


def test_pass_detection_survives_trailing_queued_turn(monkeypatch):
    cid = two_seat_thread()
    fake_seq(monkeypatch, [reply_batch("PASS"), reply_batch("real reply"),
                           reply_batch("PASS")])
    real_lane = chat._claude_code_lane
    injected = {"done": False}

    async def lane_with_interruption(message, conversation_id, **kwargs):
        async for frame in real_lane(message, conversation_id, **kwargs):
            yield frame
        if not injected["done"] and not kwargs.get("prep"):
            injected["done"] = True
            conversations.append_turn(conversation_id, "user", "trailing",
                                      speaker="user")

    monkeypatch.setattr(chat, "_claude_code_lane", lane_with_interruption)
    run_group("go", cid)
    thread = conversations.read(cid)
    orch_turn = next(t for t in thread["turns"]
                     if t.get("speaker") == "orchestrator")
    assert orch_turn.get("passed") is True and orch_turn["content"] == ""


def test_orchestrator_append_carries_seating_recipe(monkeypatch):
    cid = two_seat_thread()
    commands = fake_seq(monkeypatch, [reply_batch("lead"),
                                      reply_batch("PASS"),
                                      reply_batch("PASS")])
    run_group("go", cid)
    orch_append = commands[0][commands[0].index("--append-system-prompt") + 1]
    assert f"brain seat {cid}" in orch_append
    assert "orchestrator" in orch_append
    scout_append = commands[1][commands[1].index("--append-system-prompt") + 1]
    assert "brain seat" not in scout_append  # recipe is orchestrator-only


def test_cancel_ends_round_after_current_seat_turn(monkeypatch):
    """G6 cancel: requested during seat 1's turn - seat 2 never spawns,
    the stream ends with a cancelled heartbeat then done."""
    cid = two_seat_thread()
    commands = fake_seq(monkeypatch, [reply_batch("mid-flight reply")])
    real_lane = chat._claude_code_lane

    async def lane_then_cancel(message, conversation_id, **kwargs):
        async for frame in real_lane(message, conversation_id, **kwargs):
            yield frame
        if not kwargs.get("prep"):
            group.request_cancel(conversation_id)  # lands mid-round

    monkeypatch.setattr(chat, "_claude_code_lane", lane_then_cancel)
    events = parse(run_group("go", cid))
    names = [name for name, _ in events]

    assert len(commands) == 1  # scout never spawned
    heartbeats = [json.loads(d) for n, d in events if n == "heartbeat"]
    assert any(h["phase"] == "cancelled" for h in heartbeats)
    assert names[-1] == "done" and "error" not in names
    assert group._cancel_requested == set()  # flag cleared


def test_cancel_without_live_round_is_refused():
    cid = two_seat_thread()
    assert group.request_cancel(cid) is False
    assert cid not in group._cancel_requested


class HangingProcess:
    """Emits INIT then goes silent without EOF - the shape of a seat CLI
    stuck waiting on background work."""

    def __init__(self):
        self.stdout = asyncio.StreamReader()
        self.stdout.feed_data(json.dumps(INIT).encode() + b"\n")
        self.stderr = asyncio.StreamReader()
        self.stderr.feed_eof()
        self.returncode = None
        self.killed = False

    def kill(self):
        self.killed = True
        self.returncode = -9
        self.stdout.feed_eof()

    async def wait(self):
        return self.returncode


def test_hung_seat_turn_times_out_and_round_moves_on(monkeypatch):
    """A seat that never finishes its turn is killed at the ceiling:
    error frame, seat_done, and the next seat still speaks - the round
    never hangs (live 2026-08-27: an async subagent hung a real round)."""
    monkeypatch.setattr(group, "SEAT_TURN_TIMEOUT", 0.2)
    monkeypatch.setattr(group, "MAX_ROUNDS", 1)
    cid = two_seat_thread()
    hung: list = []

    async def spawn(cmd, cwd=None, seat=None):
        # StreamReader needs the running loop, so fakes build inside spawn
        if "[PREP TURN" in cmd[2]:
            return FakeProcess(reply_batch("READY"))
        if "You are Orchestrator" in cmd[cmd.index(
                "--append-system-prompt") + 1]:
            proc = HangingProcess()
            hung.append(proc)
            return proc
        return FakeProcess(reply_batch("scout still here"))

    monkeypatch.setattr(chat, "_spawn_claude", spawn)
    events = parse(run_group("go", cid))
    names = [name for name, _ in events]

    assert hung and hung[0].killed
    errors = [d for n, d in events if n == "error"]
    assert any("exceeded" in e for e in errors)
    seat_dones = [json.loads(d) for n, d in events if n == "seat_done"]
    assert seat_dones[0] == {"speaker": "orchestrator", "passed": True}
    assert seat_dones[1] == {"speaker": "scout", "passed": False}
    assert names[-1] == "done"


def test_error_turns_read_as_passes_and_do_not_repeat_rounds(monkeypatch):
    """Live 2026-08-27: seats erroring ('Credit balance is too low') were
    recorded as spoken turns, so the dead round repeated and burned more
    failed turns. Error turns now count as passes: one round, no repeat,
    nothing persisted."""
    cid = two_seat_thread()
    error_batch = [INIT, {"type": "result",
                          "subtype": "error_during_execution",
                          "result": "Credit balance is too low"}]
    fake_seq(monkeypatch, [error_batch, error_batch])
    events = parse(run_group("go", cid))
    names = [name for name, _ in events]

    assert names.count("round_start") == 1
    errors = [d for n, d in events if n == "error"]
    assert any("Credit balance" in e for e in errors)
    seat_dones = [json.loads(d) for n, d in events if n == "seat_done"]
    assert all(d["passed"] for d in seat_dones)
    turns = conversations.read(cid)["turns"]
    assert len(turns) == 1 and turns[0]["speaker"] == "user"


# --- G10 parallel prep, sequential speech (STORY-000082) ---

def test_prep_spawns_for_later_seats_and_stays_out_of_thread(monkeypatch):
    """The scout preps while the orchestrator speaks: exactly one prep
    per seat per user message, never the first speaker, READY discarded,
    cursor untouched by prep, and the prep session rides into the speak
    turn via --resume."""
    cid = two_seat_thread()
    commands = fake_seq(monkeypatch, [
        reply_batch("orch leads"), reply_batch("scout follows"),
        reply_batch("PASS"), reply_batch("PASS"),
    ])
    events = parse(run_group("go", cid))

    preps = fake_seq.prep_commands
    assert len(preps) == 1  # scout only, once across both rounds
    prep_append = preps[0][preps[0].index("--append-system-prompt") + 1]
    assert "You are Scout" in prep_append
    assert "[PREP TURN" in preps[0][2]

    thread = conversations.read(cid)
    contents = [t.get("content", "") for t in thread["turns"]]
    assert not any("READY" in c for c in contents)
    # scout's speak turn resumed the session its prep created (sess-1
    # from the fake INIT; scout's seat started with no session)
    scout_speak = commands[1]
    assert scout_speak[scout_speak.index("--resume") + 1] == "sess-1"
    # prep frames are flagged and never carry token frames
    prep_frames = [d for n, d in events
                   if n not in ("token", "thinking") and '"prep": true' in d]
    assert prep_frames, "expected prep-flagged frames in the stream"
    tokens = [urllib.parse.unquote(d) for n, d in events if n == "token"]
    assert not any("READY" in t for t in tokens)


def test_failed_prep_notes_heartbeat_and_speak_proceeds(monkeypatch):
    monkeypatch.setattr(group, "MAX_ROUNDS", 1)
    cid = two_seat_thread()

    async def spawn(cmd, cwd=None, seat=None):
        if "[PREP TURN" in cmd[2]:
            return FakeProcess([INIT], 1, b"prep exploded")
        return FakeProcess(reply_batch("spoken"))

    monkeypatch.setattr(chat, "_spawn_claude", spawn)
    events = parse(run_group("go", cid))
    heartbeats = [json.loads(d) for n, d in events if n == "heartbeat"]
    assert any(h.get("phase") == "prep-error" for h in heartbeats)
    assert "error" not in [n for n, _ in events]
    seat_dones = [json.loads(d) for n, d in events if n == "seat_done"]
    assert {d["speaker"] for d in seat_dones} == {"orchestrator", "scout"}
    assert all(not d["passed"] for d in seat_dones)


def test_cancel_kills_running_prep(monkeypatch):
    """Round-cancel after the orchestrator's turn: the scout never
    speaks and its still-running prep subprocess is killed."""
    cid = two_seat_thread()
    hung: list = []

    async def spawn(cmd, cwd=None, seat=None):
        if "[PREP TURN" in cmd[2]:
            proc = HangingProcess()
            hung.append(proc)
            return proc
        return FakeProcess(reply_batch("orch speaks"))

    monkeypatch.setattr(chat, "_spawn_claude", spawn)
    real_lane = chat._claude_code_lane

    async def lane_then_cancel(message, conversation_id, **kwargs):
        if not kwargs.get("prep"):
            # real turns always yield to the loop; instant fakes don't -
            # give the concurrent prep task a chance to start
            await asyncio.sleep(0.05)
        async for frame in real_lane(message, conversation_id, **kwargs):
            yield frame
        if not kwargs.get("prep"):
            group.request_cancel(conversation_id)

    monkeypatch.setattr(chat, "_claude_code_lane", lane_then_cancel)
    events = parse(run_group("go", cid))
    names = [name for name, _ in events]
    assert names[-1] == "done"
    heartbeats = [json.loads(d) for n, d in events if n == "heartbeat"]
    assert any(h["phase"] == "cancelled" for h in heartbeats)
    assert hung and hung[0].killed


# --- global roster + @-invite (G1 amendment, 2026-08-27 evening) ---

def seed_roster(entries):
    home = Path(os.environ["SECOND_BRAIN_HOME"])
    home.mkdir(parents=True, exist_ok=True)
    (home / "seats.json").write_text(json.dumps(entries))


def test_roster_mention_invites_seat_and_main_first(monkeypatch):
    """@name of a roster seat in a two-party thread invites it, seating
    the main agent first (inheriting the thread's session) so it stays
    the orchestrator; the round is scoped to the mentioned seat."""
    seed_roster([{"name": "Scribe", "cwd": "/tmp/arch"}])
    cid = conversations.create()["id"]
    conversations.append_turn(cid, "user", "earlier")
    conversations.append_turn(cid, "assistant", "done earlier")
    conversations.update(cid, {"claude_session_id": "sess-two-party"})
    commands = fake_seq(monkeypatch, [reply_batch("checking in"),
                                      reply_batch("PASS")])

    events = parse(run_group("@scribe check your repo, @b confirm", cid))

    seats = conversations.read(cid)["participants"]
    assert [s["id"] for s in seats] == ["b", "scribe"]
    # Continuity is asserted where it actually happens - the main seat's
    # FIRST turn resumes the two-party session. Its stored id then
    # advances as it speaks, so reading it back after the round proves
    # nothing.
    main_cmd = next(c for c in commands
                    if "You are B," in " ".join(c))
    assert main_cmd[main_cmd.index("--resume") + 1] == "sess-two-party"
    assert seats[1]["cwd"] == "/tmp/arch"
    heartbeats = [json.loads(d) for n, d in events if n == "heartbeat"]
    seated = [h["label"] for h in heartbeats if h["phase"] == "seated"]
    assert seated == ["B joined the conversation",
                      "Scribe joined the conversation"]
    round_starts = [json.loads(d) for n, d in events if n == "round_start"]
    assert round_starts[0]["seats"] == ["b", "scribe"]


def test_roster_mention_joins_existing_group(monkeypatch):
    seed_roster([{"name": "Zeta", "cwd": "/tmp/zeta"}])
    cid = two_seat_thread()
    fake_seq(monkeypatch, [reply_batch("zeta here"), reply_batch("PASS")])
    events = parse(run_group("@zeta thoughts?", cid))
    ids = [s["id"] for s in conversations.read(cid)["participants"]]
    assert ids == ["orchestrator", "scout", "zeta"]  # no second main seat
    round_starts = [json.loads(d) for n, d in events if n == "round_start"]
    # zeta is the mentioned seat; the unmentioned orchestrator and scout
    # both stay out (main-skipped, user 2026-09-06).
    assert round_starts[0]["seats"] == ["zeta"]


def test_unknown_mention_notices_and_still_delivers(monkeypatch):
    """G1: an @name matching nothing produces a visible notice and the
    message still runs the normal two-party lane - never a silent
    fallback, never a lost message."""
    cid = conversations.create()["id"]
    monkeypatch.setattr(chat, "pick_lane", lambda: "claude_code")
    fake_seq(monkeypatch, [reply_batch("I can seat them if you ask")])
    events = parse(run_group("@ghost @phantom hello", cid))
    heartbeats = [json.loads(d) for n, d in events if n == "heartbeat"]
    notice = next(h for h in heartbeats if h["phase"] == "unknown-seat")
    assert "@ghost" in notice["label"] and "@phantom" in notice["label"]
    thread = conversations.read(cid)
    assert not thread.get("participants")
    assert thread["turns"][-1]["role"] == "assistant"


def test_main_aliases_are_never_unknown(monkeypatch):
    """@main/@brain/@b/@2b/@b2/@second-brain in a two-party thread mean
    the agent already answering: no notice, no invite, the message flows
    down the two-party lane; combined with a roster mention the main
    seat joins once and the round covers both."""
    monkeypatch.setattr(chat, "pick_lane", lambda: "claude_code")
    for alias in ("main", "brain", "b", "2b", "b2", "second-brain"):
        cid = conversations.create()["id"]
        fake_seq(monkeypatch, [reply_batch("checked")])
        events = parse(run_group(f"@{alias} check", cid))
        heartbeats = [json.loads(d) for n, d in events if n == "heartbeat"]
        assert not any(h["phase"] == "unknown-seat" for h in heartbeats), alias
        assert not conversations.read(cid).get("participants"), alias

    seed_roster([{"name": "Scribe", "cwd": "/tmp/arch"}])
    cid2 = conversations.create()["id"]
    fake_seq(monkeypatch, [reply_batch("main here"), reply_batch("arch here"),
                           reply_batch("PASS"), reply_batch("PASS")])
    events = parse(run_group("@scribe status? @main check", cid2))
    round_starts = [json.loads(d) for n, d in events if n == "round_start"]
    assert round_starts[0]["seats"] == ["b", "scribe"]


def test_main_alias_scopes_round_to_orchestrator(monkeypatch):
    """@b (or any main alias) in a group thread addresses the orchestrator
    seat even when it is not named main."""
    cid = two_seat_thread()
    fake_seq(monkeypatch, [reply_batch("just me"), reply_batch("PASS")])
    events = parse(run_group("@b just you", cid))
    round_starts = [json.loads(d) for n, d in events if n == "round_start"]
    assert round_starts[0]["seats"] == ["orchestrator"]


def test_round_addressed_aliases_bind_to_the_orchestrator_only():
    """A seat whose id happens to equal a main-alias string ("brain",
    "b", ...) must not inherit the alias handle set - aliases bind to
    the thread's orchestrator by identity (security review 2026-09-06)."""
    impostor = [{"id": "brain", "name": "Brain"},
                {"id": "scout", "name": "Scout"}]
    replies = [("scout", "@b your call")]
    assert not group._round_addressed(replies, impostor, orch_id="other")
    # the same seat WITH orchestrator identity legitimately answers to @b
    assert group._round_addressed(replies, impostor, orch_id="brain")


def test_mention_requires_leading_whitespace():
    seed_roster([{"name": "Scribe", "cwd": "/tmp/arch"}])
    cid = conversations.create()["id"]
    joined, unknown = group.resolve_mentions(
        "mail someone@example.com about x", cid)
    assert joined == [] and unknown == []
    assert not conversations.read(cid).get("participants")


def test_main_agent_append_carries_seating_recipe(monkeypatch):
    cid = conversations.create()["id"]
    monkeypatch.setattr(chat, "pick_lane", lambda: "claude_code")
    commands = fake_seq(monkeypatch, [reply_batch("hello")])
    run_group("no mentions here", cid)
    append = commands[0][commands[0].index("--append-system-prompt") + 1]
    assert "brain seat add" in append and f"brain seat {cid}" in append


def test_seat_frames_attributed_in_round(monkeypatch):
    cid = two_seat_thread()
    fake_seq(monkeypatch, [reply_batch("mine"), reply_batch("PASS"),
                           reply_batch("PASS")])
    events = parse(run_group("go", cid))
    starts = [json.loads(d) for n, d in events if n == "iteration_start"]
    assert starts[0]["speaker"] == "orchestrator"
    tokens = [urllib.parse.unquote(d) for n, d in events if n == "token"]
    assert "mine" in tokens
