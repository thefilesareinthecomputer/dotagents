"""Permission matrix (SPEC-HARDENING-V1 H5/H6).

The controls the app claims, checked one row per control, through the
real grant-building and spawn-argument code rather than by reading the
settings file. A harness upgrade or a careless edit to the allowlist
breaks a row here instead of breaking quietly in production.

Two things this tier does NOT do, stated plainly so nobody reads more
into a green run than it earns:

- It does not prove the HARNESS enforces a rule. That was verified
  live against claude-cli on 2026-08-29 (canary read in a trusted
  directory: `Read(**/glob)` and `Read(//absolute)` both refuse with
  "denied by your permission settings"; a `~/`-anchored rule produced
  no evidence and is therefore not used). Re-verification when a
  harness updates is a manual step - see AT-11.
- It does not cover cursor, copilot, or codex permissions. Those
  harnesses express permissions elsewhere (spawn flags, sandbox,
  their own config), and their mapping is AT-9/AT-11 work. The
  enforced-by column below records what carries each control TODAY.
"""

import json
from pathlib import Path

import pytest

from second_brain import chat

_REPO_ROOT = Path(__file__).resolve().parents[1]

# control, enforced_by, assertion-key. enforced_by is the honest answer
# to "what actually stops this", never prose.
CREDENTIAL_STORES = [
    ("ssh private keys", "harness config", "**/.ssh/**"),
    ("ssh key files by name", "harness config", "**/id_rsa*"),
    ("ed25519 keys", "harness config", "**/id_ed25519*"),
    ("aws credentials", "harness config", "**/.aws/credentials"),
    ("gnupg keyring", "harness config", "**/.gnupg/**"),
    ("netrc", "harness config", "**/.netrc"),
    ("git credentials", "harness config", "**/.git-credentials"),
    ("npm token", "harness config", "**/.npmrc"),
    ("pypi token", "harness config", "**/.pypirc"),
    ("docker auth", "harness config", "**/.docker/config.json"),
    ("kube config", "harness config", "**/.kube/config"),
    ("gh hosts", "harness config", "**/.config/gh/hosts.yml"),
    ("gcloud", "harness config", "**/.config/gcloud/**"),
    ("claude credentials", "harness config", "**/.claude/.credentials.json"),
    ("codex auth", "harness config", "**/.codex/auth.json"),
    ("copilot state", "harness config", "**/.copilot/**"),
    ("cursor mcp secrets", "harness config", "**/.cursor/mcp.json"),
    ("pem/pfx/p12/key files", "harness config", "**/*.pem"),
    ("service accounts", "harness config", "**/service-account*.json"),
    ("dotenv anywhere", "harness config", "**/.env"),
    ("dotenv variants anywhere", "harness config", "**/.env.*"),
]


def _settings() -> dict:
    return json.loads((_REPO_ROOT / ".claude" / "settings.json").read_text())


@pytest.mark.parametrize("label,enforced_by,rule",
                         CREDENTIAL_STORES,
                         ids=[row[0] for row in CREDENTIAL_STORES])
def test_credential_store_is_denied(label, enforced_by, rule):
    """Every credential store the review enumerated has a deny rule, in
    the portable glob form verified to enforce (not `~/`-anchored, not
    machine-absolute - this repo is public and runs on other people's
    machines)."""
    deny = _settings()["permissions"]["deny"]
    assert f"Read({rule})" in deny, f"{label}: no deny rule for {rule}"
    assert enforced_by == "harness config"
    assert "/Users/" not in rule and not rule.startswith("~"), \
        f"{label}: rule is machine-specific and would not travel"


FOREIGN_SEAT = {"id": "worker", "cwd": "/nonexistent/other-repo"}
HOME_SEAT = {"id": "worker", "cwd": str(_REPO_ROOT)}


def test_every_deny_rule_reaches_a_spawn():
    """The rules are only controls if the spawn carries them: the main
    lane and every seat receive the full deny set. A seat's own repo may
    never have thought about credential stores, so this repo's list is
    unioned into its deny set (SPEC-SEAT-PERMISSIONS-V1 P4); deny beats
    allow in claude's model, so the union cannot widen a seat."""
    deny = _settings()["permissions"]["deny"]
    _, main_deny = chat._repo_permissions()
    assert main_deny == deny
    for seat in (FOREIGN_SEAT, HOME_SEAT):
        _, seat_deny = chat._repo_permissions(seat)
        assert set(deny) <= set(seat_deny), \
            "a seat must never receive a relaxed deny set"


def test_two_party_lane_grants_are_the_settings_file_verbatim():
    """P2: the two-party lane runs in this repo and keeps this repo's
    rules, byte for byte - the seat change must not touch it."""
    perms = _settings()["permissions"]
    assert chat._repo_permissions() == (perms["allow"], perms["deny"])


def test_a_seat_in_another_repo_receives_no_grant_from_this_one():
    """P1/P3 as probed 2026-09-02 (claude 2.1.258): permissions are
    federated. A seat in another repo runs under that repo's own
    .claude settings, which the harness reads directly, so no allow
    rule of THIS repo is relayed to it. What it does receive is the
    self-mutation denies, because a --disallowedTools rule beats an
    allow the seat's own repo grants itself (probed: `Bash(brain
    seat:*)` allowed locally ran with no flag and was refused with the
    deny flag)."""
    seat_allow, seat_deny = chat._repo_permissions(FOREIGN_SEAT)
    assert seat_allow == []
    for rule in chat._SEAT_DENIED_GRANTS:
        assert rule in seat_deny, f"self-mutation grant not denied: {rule}"


def test_a_seat_in_this_repo_keeps_this_repos_grants_minus_self_mutation():
    """The orchestrator of a group round is seated in this repo (blank
    cwd), so its own repo IS this one: it keeps the allow set that lets
    a fresh, untrusted clone run `brain search` on turn one, minus the
    grants that mutate the roster or the config, which are denied
    outright."""
    main_allow, _ = chat._repo_permissions()
    seat_allow, seat_deny = chat._repo_permissions(HOME_SEAT)
    assert set(seat_allow) < set(main_allow)
    assert any("brain search" in rule for rule in seat_allow)
    for rule in seat_allow:
        assert rule not in chat._SEAT_DENIED_GRANTS
    for rule in chat._SEAT_DENIED_GRANTS:
        assert rule in main_allow, "the main lane keeps its own grants"
        assert rule in seat_deny


def test_every_seat_carries_the_fixed_action_denies():
    """PLAN-SEAT-HARDENING-V1 P0: the AUTHORIZATION rule is prose; these
    flags are the mechanism. Every seat, whatever its repo grants, is
    denied the actions that mutate grants, rules, or remotes. Probed
    2026-09-03 (claude 2.1.259, hooks disabled): `Bash(git push:*)` as a
    deny flag refused a push a local `Bash(git:*)` allowed, against a
    control that pushed; writes under `.claude/` and settings files were
    refused by the harness itself even in the control, so those rows are
    belt and braces. The main lane carries none of them."""
    expected = {"Bash(git reset:*)", "Bash(claude plugin:*)",
                "Bash(claude:*)", "Bash(npx claude:*)",
                "Edit(**/.claude/**)", "Write(**/.claude/**)",
                "Edit(**/settings*.json)", "Write(**/settings*.json)"}
    assert expected <= set(chat._SEAT_DENIED_ACTIONS)
    _, main_deny = chat._repo_permissions()
    assert not expected & set(main_deny)
    for seat in (FOREIGN_SEAT, HOME_SEAT):
        _, seat_deny = chat._repo_permissions(seat)
        assert set(chat._SEAT_DENIED_ACTIONS) <= set(seat_deny)


def test_a_seat_inside_a_rules_source_must_be_read_only(monkeypatch, tmp_path):
    """A seat whose cwd is a rules source (the user's agent dotfiles, the
    skills repo, the brain home) can rewrite every session's rules with
    an ordinary `Edit(./**)`. Such a seat spawns only when its roster
    entry says readonly, and then with the file tools and the shell
    denied by tool name (probed 2026-09-03: `--disallowedTools Write Edit
    Bash` wrote nothing where the control wrote)."""
    agents = tmp_path / "agents"
    agents.mkdir()
    monkeypatch.setattr(chat, "_rules_source_roots", lambda: [agents])
    monkeypatch.setattr(chat.config, "seat_roots", lambda: [tmp_path])
    writer = {"id": "dotagent", "cwd": str(agents)}
    with pytest.raises(chat.SeatRootViolation) as caught:
        chat.assert_seat_root(writer)
    assert "rules source" in str(caught.value) and "readonly" in str(caught.value)
    reader = dict(writer, readonly=True)
    chat.assert_seat_root(reader)
    allow, deny = chat._repo_permissions(reader)
    assert allow == []
    assert {"Edit", "Write", "MultiEdit", "NotebookEdit", "Bash",
            "WebFetch", "WebSearch", "Agent", "Task"} <= set(deny)
    # an ordinary seat elsewhere is untouched by the read-only denies
    _, elsewhere = chat._repo_permissions({"id": "w", "cwd": str(tmp_path / "x")})
    assert "Bash" not in elsewhere


@pytest.mark.parametrize("tool,text,deny,expected", [
    ("Bash", "brain-gate: memory-pressure: level 2", [],
     ("environment", "memory pressure gate")),
    ("Edit", "brain-gate: claude-folder: seat w may not modify x", [],
     ("hook", "claude-folder guard")),
    ("Bash", "Claude requested permissions to use Bash, but you haven't granted it yet.",
     ["Bash(git reset:*)"], ("spawn-flag", "Bash(git reset:*)")),
    ("Read", "permission denied by your permission settings",
     ["Read(**/.ssh/**)"], ("global-deny", "Read(**/.ssh/**)")),
    ("Bash", "permission to use Bash has not been granted", [],
     ("no-allow", "")),
    ("Bash", "", [], ("no-allow", "")),
], ids=["environment", "hook", "spawn-flag", "global-deny", "no-allow", "no-text"])
def test_classify_denial_names_the_source(tool, text, deny, expected):
    """Every 'no' a seat hears reads the same to a model; the spawner
    knows which of its own inputs produced it and says so. Only calls the
    harness itself listed as refused reach this function."""
    assert chat.classify_denial(tool, text, deny) == expected


def test_spawn_manifest_records_sources_flags_and_a_guardrails_hash(monkeypatch, tmp_path):
    """PLAN-SEAT-HARDENING-V1 P3: nothing observable stated what a seat
    could do on a turn. The manifest records the resolved values, the
    flags as passed, and a stamp of every settings file that applied, so
    a later turn can tell the guardrails changed."""
    global_settings = tmp_path / "global" / "settings.json"
    global_settings.parent.mkdir()
    global_settings.write_text(json.dumps({
        "permissions": {"deny": ["Read(**/.ssh/**)"]},
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": []}]},
        "theme": "dark"}))
    monkeypatch.setattr(chat, "_global_settings_path", lambda: global_settings)
    seat_dir = tmp_path / "seat"
    (seat_dir / ".claude").mkdir(parents=True)
    local = seat_dir / ".claude" / "settings.local.json"
    local.write_text('{"permissions":{"allow":["Edit(./**)"]}}')
    seat = {"id": "worker", "cwd": str(seat_dir)}

    manifest = chat.spawn_manifest(seat, [], ["Bash(git push:*)"], "opus", "medium")
    assert manifest["model"] == "opus" and manifest["effort"] == "medium"
    assert manifest["cwd"] == str(seat_dir)
    assert manifest["deny_flags"] == ["Bash(git push:*)"]
    assert manifest["allow_flags"] == []
    assert manifest["allow_source"] == str(local)
    assert set(manifest["sources"]) == {str(global_settings), str(local)}
    for stamp in manifest["sources"].values():
        assert len(stamp["sha256"]) == 64 and stamp["mtime"] > 0
    first = manifest["guardrails_hash"]
    assert first == chat.spawn_manifest(seat, [], ["Bash(git push:*)"], "opus", "medium")["guardrails_hash"]

    deny = ["Bash(git push:*)"]
    # a cosmetic global change leaves the hash alone; a hooks change moves
    # it, and so does a change to the flags this lane passes
    global_settings.write_text(global_settings.read_text().replace('"dark"', '"light"'))
    assert chat.spawn_manifest(seat, [], deny, "", "")["guardrails_hash"] == first
    global_settings.write_text(global_settings.read_text().replace('"Bash"', '"Agent"'))
    moved = chat.spawn_manifest(seat, [], deny, "", "")["guardrails_hash"]
    assert moved != first
    assert chat.spawn_manifest(seat, [], [], "", "")["guardrails_hash"] != moved

    # a seat with no settings of its own still gets a manifest
    bare = {"id": "bare", "cwd": str(tmp_path / "bare")}
    assert chat.spawn_manifest(bare, [], [], "", "")["allow_source"] == ""


def test_hook_preflight_names_missing_interpreters(tmp_path):
    """PLAN-SEAT-HARDENING-V1 P4: hooks fail open when their interpreter
    is missing from the spawn PATH, so a seat spawned from a leaner
    environment silently loses its guards. The preflight resolves the
    first word of every command hook against the PATH the spawn will
    carry and names what is missing."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("python3", "bash"):
        exe = bin_dir / name
        exe.write_text("#!/bin/sh\n")
        exe.chmod(0o755)
    settings = {"hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "rtk hook claude"},
            {"type": "command", "command": "bash ~/.claude/hooks/x.sh"}]}],
        "SessionStart": [{"hooks": [
            {"type": "command", "command": "python3 ~/.claude/hooks/y.py"},
            {"type": "prompt", "prompt": "not a command"}]}]}}
    assert chat.hook_preflight([settings], str(bin_dir)) == ["rtk"]
    assert chat.hook_preflight([settings], f"{bin_dir}:/nonexistent") == ["rtk"]
    assert chat.hook_preflight([{}], str(bin_dir)) == []
    assert chat.hook_preflight([{"hooks": "garbage"}], str(bin_dir)) == []

    # ordinary hook spellings must not refuse a spawn: a script by path
    # (existing or not), a leading VAR= assignment, a variable it cannot
    # expand here (security review 2026-09-03)
    script = tmp_path / "hook.sh"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)
    unexecutable = tmp_path / "plain.sh"
    unexecutable.write_text("#!/bin/sh\n")
    spelled = {"hooks": {"Stop": [{"hooks": [
        {"type": "command", "command": f"{script} --flag"},
        {"type": "command", "command": "FOO=1 python3 z.py"},
        {"type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/h.sh"},
        {"type": "command", "command": str(tmp_path / "missing.sh")},
        {"type": "command", "command": str(unexecutable)}]}]}}
    # a script that exists but cannot execute fails open at runtime too
    assert chat.hook_preflight([spelled], str(bin_dir)) == [
        str(tmp_path / "missing.sh"), str(unexecutable)]
    home_spelled = {"hooks": {"Stop": [{"hooks": [
        {"type": "command", "command": "~/definitely-not-here/hook.sh"}]}]}}
    assert chat.hook_preflight([home_spelled], str(bin_dir)) == ["~/definitely-not-here/hook.sh"]


def test_a_missing_hook_interpreter_never_reaches_a_spawn(monkeypatch, tmp_path):
    import asyncio

    from second_brain import conversations

    monkeypatch.setenv("SECOND_BRAIN_DATA", str(tmp_path))
    monkeypatch.setattr(chat, "hook_preflight", lambda settings, path: ["rtk"])

    async def refuse_to_spawn(*args, **kwargs):
        raise AssertionError("a spawn happened with a hook that cannot run")

    monkeypatch.setattr(chat, "_spawn_claude", refuse_to_spawn)
    cid = conversations.create()["id"]

    async def drive():
        return [frame async for frame in chat._claude_code_lane("go", cid)]

    frames = b"".join(asyncio.run(drive()))
    assert b"refusing to spawn" in frames and b"rtk" in frames
    assert b"event: done" in frames


def test_a_missing_or_malformed_settings_file_fails_closed(monkeypatch, tmp_path):
    """P4 is the only thing this app contributes to a foreign seat. A
    settings file that cannot be read must refuse the spawn, not yield
    a seat that looks normal and carries no credential denies (security
    review 2026-09-03)."""
    monkeypatch.setattr(chat, "_REPO_ROOT", tmp_path)
    with pytest.raises(chat.PermissionSourceError):
        chat._repo_permissions(FOREIGN_SEAT)
    with pytest.raises(chat.PermissionSourceError):
        chat._repo_permissions()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text("{not json")
    with pytest.raises(chat.PermissionSourceError):
        chat._repo_permissions(FOREIGN_SEAT)


def test_an_unreadable_permission_source_never_reaches_a_spawn(monkeypatch,
                                                               tmp_path):
    """The lane, not only the helper: a broken source ends the stream
    with a refusal and a done frame, and nothing is spawned."""
    import asyncio

    from second_brain import conversations

    monkeypatch.setenv("SECOND_BRAIN_DATA", str(tmp_path))

    def broken(seat=None):
        raise chat.PermissionSourceError("refusing to spawn: unreadable")

    async def refuse_to_spawn(*args, **kwargs):
        raise AssertionError("a spawn happened without a permission set")

    monkeypatch.setattr(chat, "_repo_permissions", broken)
    monkeypatch.setattr(chat, "_spawn_claude", refuse_to_spawn)
    cid = conversations.create()["id"]

    async def drive():
        return [frame async for frame in chat._claude_code_lane("go", cid)]

    frames = b"".join(asyncio.run(drive()))
    assert b"refusing to spawn" in frames
    assert b"event: done" in frames


def test_seat_spawn_env_marks_the_seat():
    """The entry-point guard for the self-mutation commands keys on this:
    a seat's CLI env carries BRAIN_SEAT, the main lane's does not."""
    assert "BRAIN_SEAT" not in chat._cli_env()
    assert chat._cli_env(FOREIGN_SEAT)["BRAIN_SEAT"] == "worker"


def test_spawn_env_carries_no_credentials(monkeypatch):
    """The allowlisted spawn environment is a control too: nothing
    secret-shaped reaches a third-party CLI."""
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GH_TOKEN",
                 "AWS_SECRET_ACCESS_KEY", "CURSOR_API_KEY"):
        monkeypatch.setenv(name, "leak-me")
    env = chat._cli_env()
    assert not [n for n in env
                if any(word in n for word in ("KEY", "TOKEN", "SECRET"))]


def test_seat_root_is_re_asserted_at_spawn_not_only_at_seating(monkeypatch):
    """seat_roots is the one setting an agent may not write, but it was
    checked only when a seat was created. The seat record lives in a
    plain JSON file and a seat with shell can edit it, so a seat could
    rewrite another seat's cwd and have the next round spawn it anywhere
    (security review 2026-08-29). The spawn re-checks, which makes the
    store's contents non-authoritative.
    """
    monkeypatch.setattr(chat.config, "seat_roots",
                        lambda: [Path("/nonexistent/permitted")])

    inside = {"id": "scout", "cwd": "/nonexistent/permitted/repo"}
    outside = {"id": "scout", "cwd": "/etc"}

    chat.assert_seat_root(inside)          # permitted: no raise
    chat.assert_seat_root(None)            # two-party lane: not a seat

    with pytest.raises(chat.SeatRootViolation) as caught:
        chat.assert_seat_root(outside)
    assert "outside the permitted" in str(caught.value)
    # The refusal has to name the seat and the path, or an operator
    # cannot tell which seat was tampered with.
    assert "scout" in str(caught.value) and "/etc" in str(caught.value)

    # A stored model is argv next to --model, so the same store-tampering
    # threat applies to it and it is refused at the same gate.
    with pytest.raises(chat.SeatRootViolation):
        chat.assert_seat_root({"id": "scout",
                               "cwd": "/nonexistent/permitted/repo",
                               "model": "--dangerously-skip-permissions"})
    # effort reaches argv next to --effort by the identical route, and
    # the store is no more authoritative for it than for model or cwd.
    with pytest.raises(chat.SeatRootViolation):
        chat.assert_seat_root({"id": "scout",
                               "cwd": "/nonexistent/permitted/repo",
                               "effort": "--dangerously-skip-permissions"})


@pytest.mark.parametrize("harness", ["claude", "copilot"])
def test_a_tampered_seat_never_reaches_a_spawn(monkeypatch, tmp_path,
                                               harness):
    """The check above proves the helper refuses. This proves the LANES
    call it: deleting either call site left the whole suite green, which
    made the helper test worthless on its own (security review
    2026-08-29). A spawn that raises on entry is the tripwire.
    """
    import asyncio

    from second_brain import conversations

    monkeypatch.setenv("SECOND_BRAIN_DATA", str(tmp_path))
    monkeypatch.setattr(chat.config, "seat_roots",
                        lambda: [Path("/nonexistent/permitted")])

    async def refuse_to_spawn(*args, **kwargs):
        raise AssertionError("a tampered seat reached the spawn")

    monkeypatch.setattr(chat, "_spawn_claude", refuse_to_spawn)

    cid = conversations.create()["id"]
    conversations.append_turn(cid, "user", "hi", speaker="user")
    # Seated legitimately, then tampered with in the store - exactly what
    # a seat with shell access can do to the conversation JSON.
    seat = conversations.add_participant(cid, "Scout", "/tmp/scout",
                                         harness=harness)
    seat = dict(seat, cwd="/etc")

    async def drive():
        frames = []
        lane = (chat._claude_code_lane("go", cid, seat=seat)
                if harness == "claude"
                else chat._peer_harness_lane("go", cid, seat))
        async for frame in lane:
            frames.append(frame)
        return frames

    frames = b"".join(asyncio.run(drive()))
    assert b"refusing to spawn" in frames
    assert b"event: done" in frames, "the stream must still terminate"


def test_no_harness_is_spawned_with_a_blanket_grant():
    """Row per built harness: the mechanism that bounds it, whether that
    mechanism is an ALLOWLIST or a DENYLIST, and whether a PROBE
    established it rather than a reading of the docs.

    The allow-versus-deny column exists because "headless only enforces
    deny lists" circulated here as though it were general. It is not.
    It traces to one reported bug in one harness we do not drive, and
    copilot's own --available-tools allowlist was probed enforcing on
    2026-08-29 (5/5 blocked with the shell tool omitted, 3/3 permitted
    with it granted, against a no-flag control that ran 2/3). Each row
    below states what was actually established for that harness; an
    unprobed row is a claim, not a control, and is marked as such.
    """
    #                mechanism, shape, probed?
    posture = {
        # Federated (SPEC-SEAT-PERMISSIONS-V1): a seat in another repo
        # runs under that repo's own .claude settings and gets only this
        # repo's deny set plus the self-mutation denies as flags. Probed
        # 2026-09-02 on 2.1.258 with a UUID canary and a no-rule control:
        # settings.local.json allow AND deny enforce in a never-trusted
        # directory; settings.json allows are ignored there (stderr
        # warning) until the workspace is trusted; a --disallowedTools
        # Bash prefix beats a local allow.
        "claude": ("main lane: explicit --allowedTools/--disallowedTools "
                   "from settings.json. Seats: own repo's settings, plus "
                   "this repo's deny set and the self-mutation denies",
                   "allowlist + deny", "allow, local settings and deny "
                   "flags probed with control"),
        # The row every other lane was being measured against, and it is
        # weaker than it reads. Canary probed 2026-08-29 by the agents
        # session, NOT reproduced here: with cwd inside the workspace and
        # an unguessable UUID in a file outside it, `-s read-only` READ
        # THE FILE. So this sandbox is a write boundary, not a read one -
        # a codex seat can reach other seats' repos and any harness
        # credential file the user account can read. The write half was
        # not run, so refusal-on-write rests on earlier observation.
        "codex": ("OS sandbox: -s workspace-write fresh, "
                  '-c sandbox_mode="workspace-write" on resume. '
                  "READ BOUNDARY: NONE. Write boundary: unprobed",
                  "OS boundary, writes only", "read probed, write NOT"),
        "cursor": ("--sandbox enabled bounds SHELL only; the native Write "
                   "tool is governed separately by Write(glob) permission "
                   "rules that this driver does not yet pass. --trust is "
                   "required or print mode refuses in an untrusted cwd",
                   "OS boundary, partial", "sandbox scope probed"),
        # Unchanged this session, deliberately. --available-tools was
        # probed enforcing (5/5 blocked with the shell tool omitted, 3/3
        # permitted with it granted), but swapping it IN PLACE OF
        # --allow-all-tools was also probed and regresses the lane to
        # read-only, because print mode requires a grant for
        # write-shaped commands even though it auto-approves read-only
        # ones. The shape worth shipping is both flags together; the
        # probe that would confirm it needs a shell-only side effect
        # with a control that fires, and does not exist yet.
        "copilot": ("--allow-all-tools; bounded by cwd and the OS user "
                    "only. --available-tools would bound the tool "
                    "surface and is probed, but is NOT applied - alone "
                    "it costs the seat its write ability",
                    "NOT SCOPED", "probed 1.0.81, fix not shipped"),
    }
    # No lane confines reads today. Recorded here rather than in prose so
    # that a lane gaining read containment has to come edit this line.
    no_read_boundary = {"codex", "copilot", "cursor"}
    assert no_read_boundary <= set(posture), \
        "a lane vanished from the table - reads are the unbounded axis"
    unprobed = [name for name, (_, _, probe) in posture.items()
                if "NOT" in probe]
    assert unprobed == ["codex"], \
        "probe coverage changed - update the table deliberately, and " \
        "never downgrade a row from probed to claimed without saying why"
    codex_cmd = chat._codex_cmd("hi", "")
    assert "-s" in codex_cmd and "workspace-write" in codex_cmd
    assert not [flag for flag in codex_cmd if "dangerously" in flag]
    # resume drops -s, so the sandbox has to ride the -c override or every
    # turn after the first would be unsandboxed
    resumed = chat._codex_cmd("hi", "sess-1")
    assert 'sandbox_mode="workspace-write"' in resumed
    assert not [flag for flag in resumed if "dangerously" in flag]

    cursor_cmd = chat._cursor_cmd("hi", "")
    assert "--sandbox" in cursor_cmd
    assert cursor_cmd[cursor_cmd.index("--sandbox") + 1] == "enabled"
    assert "--force" not in cursor_cmd and "--yolo" not in cursor_cmd

    copilot_cmd = chat._copilot_cmd("hi", "")
    # Doctrine rule 1: every lane's primary control is an allowlist or an
    # OS boundary. No lane may rest on a deny list alone.
    assert not [name for name, (_, shape, _) in posture.items()
                if shape.startswith("deny")], \
        "a lane is resting on a deny list as its only boundary"
    # Copilot keeps --allow-all-tools for now: print mode requires a grant
    # for write-shaped commands, so the allowlist ALONE regresses the seat
    # to read-only. The widest grant in the fleet stays until the pair can
    # be probed together with a control that fires.
    assert "--allow-all-tools" in copilot_cmd, \
        "if this is scoped at last, the probe must show writes still work"
    # The two flags that were never in play stay out either way.
    assert "--allow-all" not in copilot_cmd
    assert "--allow-all-paths" not in copilot_cmd, \
        "file-path verification is the one thing still active on this lane"
    # The allowlist a follow-up should ship has to withhold something, or
    # it is theater when it does land.
    for withheld in ("web_fetch", "sql", "write_agent", "list_agents"):
        assert withheld not in chat.COPILOT_TOOLS, \
            f"{withheld} is granted to seats - was that deliberate?"
    # Doctrine rule 4: --available-tools takes INTERNAL tool names and
    # --deny-tool takes the `shell(cmd)` permission syntax. Mixing them
    # fails silently, so a rule naming the wrong vocabulary must not ship.
    assert "shell" not in chat.COPILOT_TOOLS, \
        "`shell` is not an --available-tools token; the tool is `bash`"
    for flag in copilot_cmd:
        if flag.startswith("--deny-tool"):
            assert "(" in flag, \
                "a bare tool name in --deny-tool is a silent no-op"
