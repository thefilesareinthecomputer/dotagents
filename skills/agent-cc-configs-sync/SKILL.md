---
name: agent-cc-configs-sync
description: Seeds a new device or idempotently reconciles an existing one against the station specs in specs/<harness>/ - pulls the latest ~/.agents first and alerts on anything breaking in the delta, plans every installed harness with seed.py (sync-skills.sh, the CLAUDE.md pointer, Antigravity's skills.json, the privacy and remote-control fragments) and applies one harness at a time on approval, then diffs Claude Code's settings, hooks, statuslines, keybindings, plugins and CLI deps item by item, asking which drifted items to apply. Invoked explicitly (/agent-cc-configs-sync) when setting up a new machine, bringing a device up to date with the specs, or checking a station for drift. External installs are an opt-in second step. The git commit/push ritual is repo-device-sync, not this.
disable-model-invocation: true
---

# agent-cc-configs-sync

Brings one machine's harness stations into line with the specs under
`~/.agents/specs/` - the same procedure whether the device is brand new or just
drifted. Each spec's Seeding table, mirrored in its `seed.json`, says what that
harness inherits and what gets planted (Phase 1, every installed harness).
Claude Code has the most seed files, and `SPEC-CLAUDE-CODE.md` section 0 maps
each to its station path; a configured station matches its seeds byte for
byte, so every check below is a `diff`, not a reading exercise (Phases 2 to 5).
Idempotent by design: on an in-spec station every phase reports clean and
changes nothing.

**Non-destructive throughout.** Nothing on the station is overwritten without
showing the diff and getting the user's pick first. Drift is two-way: the
station may hold a deliberate improvement the spec has not absorbed yet, so
"apply the seed" and "this is a pending spec update" are both valid outcomes.

## Phase 0 - Pull the latest spec, then vet what arrived

Reconciling against a stale spec defeats the point, so update `~/.agents`
first, using the `repo-device-sync` ritual (fetch, deletion pre-flight,
`--ff-only`; divergence or uncommitted work there is stop-and-ask).

Then vet the inbound changes before applying anything: review what the pull
brought in against the station's current state -

```bash
git -C ~/.agents log --oneline <old-head>..HEAD
git -C ~/.agents diff <old-head> HEAD -- specs/claude-code/ | head -200
```

Alert the user up front, before any seeding, to anything breaking, important,
or critical in that delta: changed or removed hooks and permission rules
(these alter what the harness allows or blocks), settings keys that change
enforcement behavior, deleted seeds or skills the station currently relies on,
and anything that would overwrite a station-side customization. Routine prose
or template wording changes just flow into the normal Phase 2/3 diffs; the
alert is for changes with behavioral or safety consequences.

## Phase 1 - Plan every harness the station has

```bash
python3 ~/.agents/skills/agent-cc-configs-sync/scripts/harness_probe.py          # what is installed; columns explained in Phase 2
python3 ~/.agents/skills/agent-cc-configs-sync/scripts/seed.py plan --harness all
python3 ~/.agents/skills/agent-cc-configs-sync/scripts/seed.py apply --harness <h> [--element <e>] [--key <k>]   # after the user approves that harness's plan
```

`seed.py` reads `specs/<harness>/seed.json`, the machine-readable copy of that
spec's Seeding table, and does what each row's shape says. The six shapes are
defined in `specs/SEEDING-SHAPES.md`.

| Shape | What `seed.py` does |
|---|---|
| `LINK` | runs `sync-skills.sh` |
| `POINTER` | writes a file only when it is absent (Claude Code's `CLAUDE.md`, Antigravity's `skills.json`) |
| `COPY` | shows the diff, and replaces the station file on apply |
| `FRAGMENT` | merges only the named keys into a station-owned file (`settings.json`, Codex's `config.toml`, Cursor's `cli-config.json`, goose's `config.yaml`, the shell profile for pi) and re-reads the result before writing it |
| `NATIVE`, `N/A` | reports only |

A harness with no binary on PATH and no config home is skipped as not
installed, so one `plan --harness all` covers whatever the station has. The plan
writes nothing. `apply` recomputes the plan, prints the diff it writes, and
writes one harness at a time; `--element` limits it to one row and `--key` to
named keys inside a `FRAGMENT` row. An object or list value is written whole,
and the plan names the station-only entries that drops, except that a
permissions deny list is always the union. An existing file is kept once as
`<name>.seed-bak`. Every persistent invariant 7 switch (Claude Code's
`disableRemoteControl` and telemetry env, Codex's daemon and analytics keys,
Cursor's privacy mode, goose's and pi's telemetry) is one of these fragments;
what no file holds stays by hand: a running `codex app-server` daemon is
killed, Copilot's `--no-remote-export` rides each session, and Antigravity's
remote-control daemon is never started. After an apply the remote-control
column of `harness_probe.py` reads `off`.

The `LINK` row runs `sync-skills.sh`, which creates the Claude Code symlinks and
also runs by hand (`bash ~/.agents/sync-skills.sh`). It is idempotent and never
clobbers a real local entry. If it errors on a parent-level symlink, follow the
message it prints. Hooks go through `seed_hooks.py`, which the `Hooks` row runs.

## Phase 2 - Seed-file parity

First, see what is installed:

```bash
python3 ~/.agents/skills/agent-cc-configs-sync/scripts/harness_probe.py          # --json for scripts, --skill <name> for another canary
```

It prints one row per core harness (Claude Code, Codex, Cursor, Copilot, goose,
pi, Antigravity) with the installed version, the config home, and whether the
harness lists one of this repo's skills where a no-login listing exists. Its
remote-control column must read `off` for every harness, because SPEC.md
invariant 7 keeps remote control, background daemons and telemetry off on every
station. Any other value names the switch to flip, and that harness's spec says
where the switch lives.
Stamp a station spec's version line from this output, never from memory.

Hooks come next, and `seed_hooks.py` handles them. Their scripts come from two folders
(the repository's `hooks/` and `specs/claude-code/hooks/`), and the `hooks` key
of `settings.json` is generated from their manifests, so neither is a plain
file diff.

```bash
python3 ~/.agents/skills/agent-cc-configs-sync/scripts/seed_hooks.py plan --harness claude-code
python3 ~/.agents/skills/agent-cc-configs-sync/scripts/seed_hooks.py apply --harness claude-code   # after the user approves the plan
```

`plan` lists each file to copy or update, each wiring entry to add or retire,
every entry it leaves alone because the user added it by hand, and every
manifest entry it skipped with the reason. `apply` writes exactly that and
records what it installed in `~/.claude/hooks/.seed-hooks.json`, so a later
rename or retirement is reported rather than left running. A wiring diff that
changes only grouping is not applied.

The remaining rows of the spec's section 0 table (CLAUDE.md.example,
statusline.sh, subagent-statusline.sh, keybindings.json) are `seed.py` rows,
and the Phase 1 plan already showed each as in parity, absent or drifted. Ask
the user which side wins for every drifted row in one pass rather than one
prompt per file:

- **Seed wins** - `apply --element <row>` writes the seed over the station file.
- **Station wins** - leave the station alone and record the delta as a pending
  spec edit for the user to make deliberately - never edit the spec seeds from
  inside this ritual.

`seed.py` never overwrites a `CLAUDE.md` that differs; reconcile it by hand.

## Phase 3 - settings.json (per-key, never whole-file)

`~/.claude/settings.json` mixes spec-owned keys with machine-local ones, so a
whole-file overwrite is always wrong. The `Permissions and settings` row of
`seed.py` merges only the keys the spec names and leaves every station-owned key
(`model`, `effortLevel`, `theme`, `tui` and the rest) alone. `seed_hooks.py`
wrote the `hooks` key in Phase 2. The `seed.py` plan lists each differing key
with both values. Ask the user which to apply, then run
`apply --element "Permissions and settings"` for the seed-wins keys; a
station-wins key is a pending spec edit, as in Phase 2.

The spec's section 7 explains what each block enforces; consult it before
recommending a side.

## Phase 4 - Plugins and CLI deps (report only)

Check and report; install nothing in this phase:

```bash
claude plugin list
rtk --version && rtk gain >/dev/null && echo rtk-ok
jq --version; node --version; python3 --version
curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://localhost:37701 || true
```

Compare against the spec's sections 2 and 3 (four plugins, jq, rtk, node,
python3, claude-mem daemon on 37701). Report what is missing or disabled.

## Phase 5 - External installs (opt-in only)

Only on the user's explicit go-ahead, item by item:

- `brew install jq` / `brew install rtk-ai/tap/rtk`, then rtk config per
  spec section 2 (grep excluded from the hook).
- `/plugin` marketplaces and installs per section 3 - these run inside Claude
  Code, so name the steps for the user rather than pretending to run them.
- Seed `~/.claude-mem/settings.json` per section 3.1 - required after every
  claude-mem install or reinstall; the default config intercepts Read.

## Verify and report

Run the spec's section 11 step 9 verification list as far as it can be checked
from this session. End with a compact table: item, state found, action taken,
final state - one row per seed file, one for settings keys, one for plugins,
one for deps.

## When NOT to use

Committing or pushing this repo (or any repo) is `repo-device-sync`. A one-off
settings.json tweak the user dictates is `update-config`, not a parity sweep.
Phases 2 to 5 are Claude Code's; the other harnesses have no seed files beyond
their `seed.json` rows yet, so Phase 1 is their whole reconciliation.
