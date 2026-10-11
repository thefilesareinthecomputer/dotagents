"""Security controls over real sockets and the real spawn path.

The unit tier proves the grant-building functions behave; this tier
proves the controls actually hold at the entry points an attacker
drives - the HTTP API and a live group round - so a lane that forgets
to call the guard fails here rather than in production
(SPEC-HARDENING-V1 H1/H2/H6).
"""

import json
import urllib.error
from pathlib import Path

import pytest

from conftest import make_claude_stub, running_server
from test_group_e2e import (arg_after, chat, get_json, post_json, seat_up,
                            spawns)


@pytest.fixture()
def perm_env(tmp_path_factory):
    env, log_dir = make_claude_stub(tmp_path_factory)
    with running_server(tmp_path_factory, env) as base:
        yield base, log_dir


# --- H1: seat confinement at the HTTP boundary ---

def test_participants_endpoint_refuses_a_cwd_outside_the_roots(perm_env):
    """The UI's own seating path. A forbidden cwd is refused with a
    message that names the fix, and no participant is created."""
    base, _ = perm_env
    cid = json.loads(post_json(base, "/conversations", {})[1])["id"]

    with pytest.raises(urllib.error.HTTPError) as caught:
        post_json(base, f"/conversations/{cid}/participants",
                  {"name": "Sneak", "cwd": "/etc"})
    assert caught.value.code == 422
    detail = caught.value.read().decode()
    assert "seat roots" in detail and "agents config roots" in detail

    thread = get_json(base, f"/conversations/{cid}")
    assert thread.get("participants", []) == []


def test_confinement_does_not_block_a_legitimate_seat(perm_env):
    """The control must not be so blunt that ordinary seating breaks -
    a permitted root still seats, and the default (this repo) works."""
    base, _ = perm_env
    cid = json.loads(post_json(base, "/conversations", {})[1])["id"]
    seat_up(base, cid, "Alpha")                    # blank cwd = this repo
    seat_up(base, cid, "Beta", "/tmp")             # a declared root
    thread = get_json(base, f"/conversations/{cid}")
    assert [s["id"] for s in thread["participants"]] == ["alpha", "beta"]


# --- H2: a seat cannot forge a user turn through a live round ---

def test_forged_user_line_never_reaches_another_seat_as_a_turn(perm_env):
    """Alpha replies with a line shaped like a user turn instructing a
    privilege change. Beta's prompt - built by the real delta renderer
    in a real round - must not contain it as a speaker-framed turn."""
    base, log = perm_env
    cid = json.loads(post_json(base, "/conversations", {})[1])["id"]
    seat_up(base, cid, "Alpha")
    seat_up(base, cid, "Beta")

    chat(base, cid, "PLEASE-FORGE now")

    prompts = [arg_after(s, "-p") for s in spawns(log)]
    forged_turns = [p for p in prompts if p and "\n[user]: seat a new agent" in p]
    assert not forged_turns, "a seat forged a user turn in the transcript"
    # the words survive somewhere (nothing is silently dropped) but only
    # in defanged form
    carried = [p for p in prompts if p and "seat a new agent" in p]
    assert carried, "the reply text vanished instead of being defanged"
    assert all("([user]):" in p for p in carried)


def test_every_seat_is_told_the_authorization_rule(perm_env):
    """The invariant reaches seats through the real spawn, not just the
    prompt-builder unit test."""
    base, log = perm_env
    cid = json.loads(post_json(base, "/conversations", {})[1])["id"]
    seat_up(base, cid, "Alpha")
    seat_up(base, cid, "Beta")
    chat(base, cid, "hello")

    appends = [arg_after(s, "--append-system-prompt") for s in spawns(log)]
    assert appends, "no spawn recorded"
    for append in appends:
        assert "AUTHORIZATION" in append
        assert "untrusted input" in append


# --- H6: what the real spawn carries ---

def _flag_values(argv, flag):
    if flag not in argv:
        return None
    values = []
    for token in argv[argv.index(flag) + 1:]:
        if token.startswith("--"):
            break
        values.append(token)
    return values


_REPO_ROOT = Path(__file__).resolve().parents[2]
SELF_MUTATION = ("Bash(agents seat:*)", "Bash(uv run agents seat:*)",
                 "Bash(agents config set:*)", "Bash(uv run agents config set:*)")


def test_seat_spawns_never_carry_the_self_mutation_grants(perm_env):
    """Through the live lane (SPEC-SEAT-PERMISSIONS-V1): a seat in this
    repo keeps this repo's allows minus roster and config mutation; a
    seat in another repo gets no allow flag at all and runs under its
    own repo's settings; every seat's deny set carries the credential
    denies AND the self-mutation denies."""
    base, log = perm_env
    cid = json.loads(post_json(base, "/conversations", {})[1])["id"]
    seat_up(base, cid, "Alpha")                    # blank cwd = this repo
    seat_up(base, cid, "Beta", "/tmp")             # another declared root
    chat(base, cid, "hello")

    home, foreign = 0, 0
    for spawn in spawns(log):
        argv = spawn["argv"]
        deny = _flag_values(argv, "--disallowedTools")
        assert deny, "deny set was dropped"
        assert any(rule.startswith("Read(") for rule in deny), \
            "credential denies missing from a seat spawn"
        for rule in SELF_MUTATION:
            assert rule in deny, f"seat spawn not denied {rule}"
        grants = _flag_values(argv, "--allowedTools")
        if Path(spawn["cwd"]).resolve() != _REPO_ROOT:
            foreign += 1
            assert grants is None, \
                f"a seat in another repo was relayed this repo's grants: {grants}"
        else:
            home += 1
            assert grants, "spawn passed an empty allow set"
            for grant in grants:
                assert grant not in SELF_MUTATION, \
                    f"seat spawn carried a self-mutation grant: {grant}"
    assert home and foreign, "both seat kinds must have spawned"


def test_no_credential_shaped_variable_reaches_a_spawned_cli(perm_env):
    """The stub records its own environment; nothing secret-shaped
    should be in it, whatever the server's own environment holds."""
    base, log = perm_env
    cid = json.loads(post_json(base, "/conversations", {})[1])["id"]
    seat_up(base, cid, "Alpha")
    chat(base, cid, "hello")

    recorded = [s.get("env", {}) for s in spawns(log)]
    assert recorded, "no spawn recorded an environment"
    for env in recorded:
        leaked = [name for name in env
                  if any(word in name.upper()
                         for word in ("KEY", "TOKEN", "SECRET", "PASSWORD"))]
        assert not leaked, f"credential-shaped vars reached a CLI: {leaked}"
