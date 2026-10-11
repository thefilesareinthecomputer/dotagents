"""Group-chat integration tier: every piece of the end-to-end flow over a
REAL server and real sockets, with the claude CLI replaced by a recording
stub (conftest.make_claude_stub) - each seat turn is a real subprocess
spawn whose argv/cwd land in a log the tests read back.

Covers the user scenario piecewise: two-party work -> conversion to group
with session inheritance -> per-seat sessions/cwds -> orchestrator-only
seating recipe -> phone-a-friend mid-thread -> PASS rounds and budgets ->
@-mention scoping -> a message queued while a round is streaming.
"""

import json
import re
import threading
import time
import urllib.request

import pytest

from conftest import make_claude_stub, running_server


@pytest.fixture()
def group_env(tmp_path_factory):
    env, log_dir = make_claude_stub(tmp_path_factory)
    with running_server(tmp_path_factory, env) as base:
        yield base, log_dir


def post_json(base, path, body):
    request = urllib.request.Request(
        base + path, method="POST", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.status, response.read().decode()


def get_json(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as response:
        return json.loads(response.read())


def chat(base, cid, message):
    """One full chat turn/round; returns the SSE event names + raw text."""
    status, text = post_json(base, "/chat",
                             {"message": message, "conversation_id": cid})
    assert status == 200
    names = [line[7:] for line in text.splitlines()
             if line.startswith("event: ")]
    return names, text

def spawns(log_dir):
    """Recorded stub spawns, in order: [{argv, cwd}]."""
    out = []
    for path in sorted(log_dir.glob("spawn-*.json")):
        out.append(json.loads(path.read_text()))
    return out


def arg_after(spawn, flag):
    argv = spawn["argv"]
    return argv[argv.index(flag) + 1] if flag in argv else None


def seat_up(base, cid, name, cwd="", harness="claude"):
    status, body = post_json(base, f"/conversations/{cid}/participants",
                             {"name": name, "cwd": cwd, "harness": harness})
    assert status == 200
    return json.loads(body)


def test_two_party_work_then_group_conversion_keeps_the_session(group_env):
    base, log = group_env
    cid = json.loads(post_json(base, "/conversations", {})[1])["id"]

    # Two-party phase: a real turn establishes the main session.
    names, _ = chat(base, cid, "do some two-party work")
    assert names[-1] == "done"
    thread = get_json(base, f"/conversations/{cid}")
    main_session = thread["claude_session_id"]
    assert main_session.startswith("stub-")

    # Conversion: the first repo-root seat inherits session and history.
    seat = seat_up(base, cid, "B")
    assert seat["session_id"] == main_session
    assert seat["cursor"] == len(thread["turns"])
    seat_up(base, cid, "Scout", "/tmp")

    # First group round: the main seat's spawn RESUMES the two-party session.
    chat(base, cid, "now as a group")
    all_spawns = spawns(log)
    main_turns = [s for s in all_spawns
                  if "You are B," in (arg_after(s, "--append-system-prompt") or "")]
    assert main_turns, "the main seat took a group turn"
    assert arg_after(main_turns[0], "--resume") == main_session
    # and its delta does NOT replay the pre-group history it already saw
    assert "two-party work" not in arg_after(main_turns[0], "-p")


def test_each_seat_owns_its_cwd_and_session_across_rounds(group_env, tmp_path):
    base, log = group_env
    cid = json.loads(post_json(base, "/conversations", {})[1])["id"]
    other_repo = tmp_path / "other-repo"
    other_repo.mkdir()
    seat_up(base, cid, "Alpha")
    seat_up(base, cid, "Beta", str(other_repo))

    chat(base, cid, "first message")
    chat(base, cid, "second message")

    beta_spawns = [s for s in spawns(log)
                   if "You are Beta," in (arg_after(s, "--append-system-prompt") or "")]
    assert len(beta_spawns) >= 2
    # its own repo, both turns
    assert all(s["cwd"] == str(other_repo) for s in beta_spawns)
    # first turn opens the session, later turns resume it
    assert arg_after(beta_spawns[0], "--resume") is None
    assert arg_after(beta_spawns[1], "--resume") == "stub-beta"
    thread = get_json(base, f"/conversations/{cid}")
    beta = next(s for s in thread["participants"] if s["id"] == "beta")
    assert beta["session_id"] == "stub-beta"


def test_orchestrator_alone_carries_the_seating_recipe(group_env):
    base, log = group_env
    cid = json.loads(post_json(base, "/conversations", {})[1])["id"]
    seat_up(base, cid, "Alpha")
    seat_up(base, cid, "Beta")
    chat(base, cid, "hello room")

    appends = {("Alpha" if "You are Alpha," in a else "Beta"): a
               for s in spawns(log)
               if (a := arg_after(s, "--append-system-prompt"))}
    assert f"brain seat {cid}" in appends["Alpha"]
    assert "brain seat" not in appends["Beta"]


def test_phone_a_friend_joins_mid_thread_with_bounded_catchup(group_env):
    base, log = group_env
    cid = json.loads(post_json(base, "/conversations", {})[1])["id"]
    seat_up(base, cid, "Alpha")
    chat(base, cid, "round one context")

    # The orchestrator's recipe is exactly this call; a live agent would
    # curl it - the integration seam is identical.
    friend = seat_up(base, cid, "Friend")
    assert friend["cursor"] == 0

    chat(base, cid, "friend, weigh in")
    friend_spawns = [s for s in spawns(log)
                     if "You are Friend," in (arg_after(s, "--append-system-prompt") or "")]
    assert friend_spawns, "friend took a turn in the next round"
    catchup = arg_after(friend_spawns[0], "-p")
    # full attributed catch-up: the earlier round is in its first prompt
    assert "[user]: round one context" in catchup
    assert "[alpha]:" in catchup

    thread = get_json(base, f"/conversations/{cid}")
    assert {s["id"] for s in thread["participants"]} == {"alpha", "friend"}


def test_pass_round_ends_early_with_passed_turns(group_env):
    base, log = group_env
    cid = json.loads(post_json(base, "/conversations", {})[1])["id"]
    seat_up(base, cid, "Alpha")
    seat_up(base, cid, "Beta")
    names, text = chat(base, cid, "PLEASE-PASS everyone")

    assert names.count("round_start") == 1  # nobody spoke - no round 2
    seat_dones = [json.loads(line[6:]) for line in text.splitlines()
                  if line.startswith("data: ") and '"passed"' in line]
    passed = [d for d in seat_dones if d.get("passed") is True]
    assert len(passed) == 2
    thread = get_json(base, f"/conversations/{cid}")
    chips = [t for t in thread["turns"] if t.get("passed")]
    assert len(chips) == 2 and all(t["content"] == "" for t in chips)


def test_mention_scopes_round_and_skips_the_orchestrator(group_env):
    """@name narrows the round to exactly the named seats (main-skipped,
    user 2026-09-06). Alpha, seated first, IS the orchestrator here; it
    and the third unmentioned seat both stay out."""
    base, log = group_env
    cid = json.loads(post_json(base, "/conversations", {})[1])["id"]
    seat_up(base, cid, "Alpha")
    seat_up(base, cid, "Beta")
    seat_up(base, cid, "Gamma")
    chat(base, cid, "@beta PLEASE-PASS just you")

    appends = [arg_after(s, "--append-system-prompt") or "" for s in spawns(log)]
    spoke = {name for name in ("Alpha", "Beta", "Gamma")
             if any(f"You are {name}," in a for a in appends)}
    assert spoke == {"Beta"}, spoke


def test_brain_seat_cli_seats_via_the_running_server(group_env):
    """The orchestrator's seating recipe is `brain seat <cid> <name>
    [cwd]` - run it exactly as a seat's bash would."""
    import subprocess as sp
    import sys
    base, log = group_env
    port = base.rsplit(":", 1)[1]
    cid = json.loads(post_json(base, "/conversations", {})[1])["id"]
    seat_up(base, cid, "Alpha")

    result = sp.run(
        [sys.executable, "-c",
         f"import sys; sys.argv = ['brain', 'seat', '{cid}', 'Zero', ''];"
         "from second_brain.app import main; main()"],
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "SECOND_BRAIN_PORT": port,
             "SECOND_BRAIN_HOME": "/tmp"})
    assert result.returncode == 0, result.stderr
    assert "seated zero" in result.stdout

    thread = get_json(base, f"/conversations/{cid}")
    assert {s["id"] for s in thread["participants"]} == {"alpha", "zero"}


def test_message_queued_during_live_round_reaches_next_turn(tmp_path_factory):
    env, log = make_claude_stub(tmp_path_factory, sleep=1.2)
    with running_server(tmp_path_factory, env) as base:
        cid = json.loads(post_json(base, "/conversations", {})[1])["id"]
        seat_up(base, cid, "Alpha")
        seat_up(base, cid, "Beta")

        first = {}
        def run_first():
            first["names"], _ = chat(base, cid, "PLEASE-PASS after this")
        round_thread = threading.Thread(target=run_first)
        round_thread.start()
        time.sleep(0.6)  # Alpha's turn is mid-generation now
        names, text = chat(base, cid, "queued interjection")
        round_thread.join(timeout=30)

        # the second POST was acknowledged as queued, not a second round
        assert names == ["heartbeat", "done"] and "queued" in text
        # and a later seat turn in the SAME round received it
        prompts = [arg_after(s, "-p") for s in spawns(log)]
        assert any("queued interjection" in p for p in prompts[1:])


# --- peer-harness seats over native-shape stubs (R33/G9, 2026-08-27) ---

def peer_prompt(spawn):
    """The prompt argv slot per harness: cursor rides the last argument,
    claude and copilot ride -p."""
    argv = spawn["argv"]
    if argv[0] == "cursor-agent":
        return argv[-1]
    return arg_after(spawn, "-p") or ""


def test_peer_seats_full_round_with_prep_resume_and_persistence(group_env):
    """A cursor + copilot round end to end over real sockets: attributed
    SSE, no errors despite copilot's 150KB snapshot line, prep for the
    second seat, sessions stored and resumed in round 2, replies
    persisted with speakers."""
    base, log = group_env
    cid = json.loads(post_json(base, "/conversations", {})[1])["id"]
    seat_up(base, cid, "Cursor", "/tmp", harness="cursor")
    seat_up(base, cid, "Copilot", "/tmp", harness="copilot")

    names, text = chat(base, cid, "introduce yourselves")

    assert "error" not in names, text[:2000]
    assert names.count("round_start") == 2 and names[-1] == "done"

    thread = get_json(base, f"/conversations/{cid}")
    speakers = [t.get("speaker") for t in thread["turns"]]
    assert speakers == ["user", "cursor", "copilot", "cursor", "copilot"]
    contents = {t["speaker"]: t["content"] for t in thread["turns"][1:3]}
    assert contents["cursor"] == "Cursor reporting - @copilot confirm"
    assert contents["copilot"] == "Copilot reporting"
    sessions = {s["id"]: s["session_id"] for s in thread["participants"]}
    assert sessions["cursor"].startswith("cur-stub-")
    assert sessions["copilot"].startswith("cop-stub-")

    all_spawns = spawns(log)
    cursor_spawns = [s for s in all_spawns if s["argv"][0] == "cursor-agent"]
    copilot_spawns = [s for s in all_spawns if s["argv"][0] == "copilot"]
    # cursor: two speaking turns; copilot: one prep + two speaking turns
    assert len(cursor_spawns) == 2
    assert len(copilot_spawns) == 3
    preps = [s for s in copilot_spawns if "[PREP TURN" in peer_prompt(s)]
    assert len(preps) == 1
    # no prep output persisted anywhere
    assert all("READY" not in (t.get("content") or "")
               for t in thread["turns"])
    # round 2 resumed the sessions round 1 created
    assert arg_after(cursor_spawns[1], "--resume") == sessions["cursor"]
    resume_args = [a for a in copilot_spawns[-1]["argv"]
                   if a.startswith("--resume=")]
    assert resume_args == ["--resume=" + sessions["copilot"]]
    # both seats ran in their seat cwd (macOS reports the resolved path)
    import os
    assert ({s["cwd"] for s in cursor_spawns + copilot_spawns}
            == {os.path.realpath("/tmp")})


def test_mission_control_shows_live_turn_then_clears(tmp_path_factory):
    """G8 over real sockets: GET /agents carries a row while a seat turn
    is generating and is empty after the round ends."""
    env, _log = make_claude_stub(tmp_path_factory, sleep=1.2)
    with running_server(tmp_path_factory, env) as base:
        cid = json.loads(post_json(base, "/conversations", {})[1])["id"]
        seat_up(base, cid, "Alpha")

        result = {}

        def run_round():
            result["names"], _ = chat(base, cid, "PLEASE-PASS")

        round_thread = threading.Thread(target=run_round)
        round_thread.start()
        try:
            rows = []
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not rows:
                rows = get_json(base, "/agents")["agents"]
                time.sleep(0.1)
            assert rows, "no live row appeared during the seat turn"
            assert rows[0]["actor"] == "alpha"
            assert rows[0]["conversation_id"] == cid
            assert rows[0]["state"] in ("starting", "thinking", "tools",
                                        "generating", "idle")
        finally:
            round_thread.join(timeout=30)
        assert get_json(base, "/agents")["agents"] == []


def test_thread_and_seat_sessions_survive_a_server_restart(tmp_path_factory):
    """Reopening a thread later resumes the SAME sessions - the main
    lane's and every seat's - because the session refs live in the
    conversation file on disk rather than in server memory.

    Nothing here is a long-lived process: each turn spawns a CLI and it
    exits. So "the agents come back" is a claim about stored refs
    surviving, and the only honest way to test it is to kill the server
    between rounds. Two servers, one data dir, and round two's recorded
    argv has to carry --resume with round one's ids.
    """
    env, log = make_claude_stub(tmp_path_factory)
    data_dir = tmp_path_factory.mktemp("restart-data")
    env = dict(env, SECOND_BRAIN_DATA=str(data_dir))

    with running_server(tmp_path_factory, env) as base:
        cid = json.loads(post_json(base, "/conversations", {})[1])["id"]
        chat(base, cid, "do some two-party work")
        seat_up(base, cid, "Alpha")
        seat_up(base, cid, "Beta")
        names, _ = chat(base, cid, "@alpha @beta open the round")
        assert names[-1] == "done"

        thread = get_json(base, f"/conversations/{cid}")
        seats = {s["name"]: s["session_id"]
                 for s in thread["participants"]}
        assert all(seats.values()), f"a seat has no session ref: {seats}"
        assert seats["Beta"] != seats["Alpha"], \
            "seats must not share one session"
    before = len(spawns(log))

    # The server is gone. A new one, same data dir. Reopening a thread in
    # the UI spawns nothing by itself, so the proof is the NEXT round.
    with running_server(tmp_path_factory, env) as base:
        reopened = get_json(base, f"/conversations/{cid}")
        assert {s["name"]: s["session_id"]
                for s in reopened["participants"]} == seats, \
            "seat session refs did not survive the restart"

        names, _ = chat(base, cid, "@alpha @beta still with me?")
        assert names[-1] == "done"

    # Every round-two spawn resumed the id round one established, and
    # each seat resumed its OWN rather than a shared one.
    resumed = {}
    for spawn in spawns(log)[before:]:
        append = arg_after(spawn, "--append-system-prompt") or ""
        match = re.search(r"You are ([^,]+),", append)
        if match:
            resumed.setdefault(match.group(1), set()).add(
                arg_after(spawn, "--resume"))
    assert resumed, "round two spawned nothing"
    for name, session_id in seats.items():
        assert resumed.get(name) == {session_id}, \
            f"{name} did not resume its own session: {resumed.get(name)}"
