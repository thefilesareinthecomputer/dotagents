---
name: agent-cc-configs-sync
description: Seeds a new device or idempotently reconciles an existing one against the Claude Code station spec in specs/claude-code/ - pulls the latest ~/.agents first, vets the inbound delta and alerts on anything breaking or critical, runs sync-skills.sh, applies the global CLAUDE.md pointer template, then diffs settings, hooks, statuslines, keybindings, plugins and CLI deps item by item, asking the user which drifted items to apply. Invoked explicitly (/agent-cc-configs-sync) when setting up Claude Code on a new machine, bringing a device up to date with the specs, or checking a station for drift. External installs (brew, plugins, claude-mem) are an opt-in second step. The git commit/push ritual is repo-device-sync, not this.
disable-model-invocation: true
---

# agent-cc-configs-sync

Brings one machine's Claude Code station into line with the spec at
`~/.agents/specs/claude-code/` - the same procedure whether the device is
brand new or just drifted. The spec's `SPEC-CLAUDE-CODE.md` is the source of
truth; its section 0 table maps each seed file to its station path, and a
configured station matches its seeds byte for byte, so every check below is a
`diff`, not a reading exercise. Idempotent by design: on an in-spec station
every phase reports clean and changes nothing.

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

## Phase 1 - Sync the view

```bash
bash ~/.agents/sync-skills.sh
```

Symlinks `skills/`, `agents/`, and `commands/` into `~/.claude/` per-entry.
Already idempotent and never clobbers a real local entry; run it every time.
If it errors on a parent-level symlink, follow the message it prints.

## Phase 2 - Seed-file parity

For each row of the spec's section 0 table (CLAUDE.md.example, which is the
one-line pointer to `~/.agents/AGENTS.md`,
`hooks/`, statusline.sh, subagent-statusline.sh, keybindings.json - everything
except settings.json, which gets Phase 3's treatment), diff the seed against
its station path:

- **Identical** - skip, report in sync.
- **Missing on station** - copy the seed verbatim (Write tool, not shell).
- **Drifted** - show the diff and ask which side wins. Seed wins: write the
  seed over the station file. Station wins: leave the station alone and record
  the delta as a pending spec edit for the user to make deliberately - never
  edit the spec seeds from inside this ritual.

Collect all drifted items first, then ask about them in one pass rather than
one prompt per file.

## Phase 3 - settings.json (per-key, never whole-file)

`~/.claude/settings.json` mixes spec-owned keys with machine-local ones, so a
whole-file overwrite is always wrong. Compare the seed and the station
key by key (top-level keys, and per-entry inside `permissions`, `hooks`, and
`enabledPlugins`):

- Keys only on the station: leave them; they are device-local by design.
- Keys only in the seed, or differing: list each with both values and ask
  which to apply. Apply the chosen ones with Edit on the station file.

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
Other harnesses' stations follow their own folder under `specs/`.
