# SPEC-CODEX.md - OpenAI Codex CLI station

The medium-stakes lane: everyday work that is not load-bearing. Config lives at
`~/.codex/`.

## Skills: nothing to install

Codex reads **`$HOME/.agents/skills`** directly. Cloning this repo to `~/.agents`
is the entire setup. It follows symlinked skill folders.

**Confirmed by observation 2026-07-31** on this machine.

Its full discovery set, per OpenAI's documentation on that date:

| Path | Scope |
|---|---|
| `$CWD/.agents/skills` | current directory |
| `$CWD/../.agents/skills` | parent, for nested repos |
| `$REPO_ROOT/.agents/skills` | repository root |
| `$HOME/.agents/skills` | user, and what this repo provides |
| `/etc/codex/skills` | system-wide |

Skills are invoked with `/skills` or by typing `$`, and Codex may also select one
implicitly from its description.

## What does not carry over

Only `skills/` is portable. **Confirmed by observation 2026-07-31: commands in
`~/.agents/commands/` do not appear in Codex**, while the skills beside them load.
Subagents are untested.

Codex has its own prompts and subagent mechanisms; this repo's `agents/` and
`commands/` trees target Claude Code. The portable path, if one is wanted, is
re-expressing them as skills carrying `disable-model-invocation: true` or
`context: fork` (backlog).

## Permissions (verified 2026-08-28, codex-cli 0.150.1)

Codex has **no per-command allowlist**: its model is an approval policy times
an OS-level sandbox, and the sandbox is the enforcement. Everything below was
verified headless on this machine.

**Where rules live.** `~/.codex/config.toml` is the base; `-p/--profile <name>`
layers `$CODEX_HOME/<name>.config.toml` over it; `-c key=value` overrides per
invocation (e.g. `-c 'sandbox_permissions=["disk-full-read-access"]'`).
Per-directory trust is recorded in config.toml as
`[projects."<path>"] trust_level = "trusted"` - this machine's config carries
such entries from prior use.

**Headless (`codex exec`) prerequisites.** It refuses to run in a directory
that is neither a git repo nor trusted, without `--skip-git-repo-check`:
`Not inside a trusted directory and --skip-git-repo-check was not specified.`
It also reads stdin, so a driver must close it (`</dev/null`) or the process
waits.

**Sandbox semantics.** `-s read-only | workspace-write | danger-full-access`.
In `read-only`, commands still execute but writes fail at the OS layer -
verified: `date` returned output while a file creation failed inside the turn
with `zsh: operation not permitted`. A denial is therefore an ordinary failed
command in the transcript, not a permission event; there is no prompt to miss
headless. `--approve-for-me` routes approval requests through automatic review
under workspace-write. `--dangerously-bypass-approvals-and-sandbox` exists and
never belongs in a seat spawn.

**Machine-readable output.** `--json` emits JSONL: `thread.started`,
`turn.started`/`turn.completed`, and `item.completed` items (`agent_message`,
command executions, and error items). The narrow-grant seat shape is
`codex exec -s workspace-write` in the seat's cwd: writes confined to the
workspace, no bypass flags.

**The sandbox bounds writes, not reads (verified 2026-08-29).** With the working
directory inside a workspace and `-s read-only` - the most restrictive level -
Codex read a file *outside* that workspace containing an unguessable UUID, and
returned its contents. Read confinement is not part of what this sandbox
provides at any level.

The consequence for anything running as a shared user: a Codex process can read
every other harness's stored credentials, every other project on the machine,
and anything else that user can read. The sandbox stops it changing those files;
it does not stop it seeing them. Where read isolation is actually required, the
boundary has to be a separate operating-system account or a container, not a
sandbox level. The write half of this behavior is recorded above from the
2026-08-28 run and was not re-probed on 2026-08-29.

**Plugins and trust are per `CODEX_HOME`, and they are inherited by every
session.** Plugin enablement (`[plugins."<name>@<marketplace>"] enabled = true`)
and directory trust both live in `config.toml`, so anything configured there
applies to every invocation from that home - including a headless one. A plugin
granting reach into calendar, messaging or documents is therefore not scoped to
interactive use, and there is no per-project or per-invocation plugin scope.

`CODEX_HOME` is the lever, and it is honored: pointing it at a separate
directory yields a distinct configuration domain with its own `config.toml` and
its own plugin set. Verified 2026-08-29 - a separate home ran with its own
config and did **not** inherit credentials from the default one, so an isolated
profile needs its own `codex login`. That makes a plugin-free profile cheap to
stand up for automated use while an interactive home keeps its plugins.

Note the boundary this does and does not draw: a separate `CODEX_HOME` is a
configuration boundary, not an isolation boundary. A process running as the same
user can still read the default home directly.

## Delegation from Claude Code: the `codex-task` skill

Claude Code hands Codex one bounded task through
`skills/codex-task/scripts/codex_task.py`, the only sanctioned way a session
spawns Codex. It runs `codex exec` headless in a detached git worktree, harvests
a patch filtered to an explicit file allowlist, and applies it only after the
delegating agent reviews the diff. Built and verified 2026-09-19/20 on desktop
against `codex-cli 0.155.1`; the spec that built it is archived under
`tasks/completed/`.

**The ChatGPT desktop app is not a surface.** It bundles no CLI, local server or
MCP server. The Homebrew cask `codex` is a separate install, and `codex login`
signs in with the ChatGPT plan, whose Codex usage quota bounds delegation (a
quota hit surfaces as an error item in the JSONL, not a hang). "Astra" is
GPT-6 Astra, the model, reached with `-m gpt-6-astra`; it is not a product.

**`codex mcp-server` is gone at 0.155.1.** `codex --help` lists `mcp` (client
management) and the experimental `app-server`; neither is an MCP server a
Claude Code session can register. OpenAI's own `codex-plugin-cc` drives the app
server, has no per-file write scope, and is not installed here.

**Facts the skill rests on, probed 2026-09-19:**

| Fact | How it was seen |
|---|---|
| `workspace-write` denies writes outside the `-C` root, including `$HOME` and other repos, but `/tmp` and `$TMPDIR` are writable unless `sandbox_workspace_write.exclude_slash_tmp` and `exclude_tmpdir_env_var` are set | `codex sandbox -c 'sandbox_mode="workspace-write"'` probe, then `TMP_DENIED` with both keys |
| Network is off under `workspace-write` by default | `NET_DENIED` |
| Inside a detached worktree Codex can edit files and run `git status` and `git diff`, but not `git add`; making the worktree's git dir writable does not help because git then locks the main `.git`, which must stay read-only | worktree probe with and without `writable_roots` |
| `--ignore-user-config` drops the ChatGPT app's `[mcp_servers.*]` and `[plugins.*]` while auth still works | headless run reported no MCP servers or tools |
| **A headless run still writes `[projects."<repo>"] trust_level = "trusted"` into `~/.codex/config.toml`, even with `--ignore-user-config`** | first live canary appended the entry; that trust persists into interactive sessions |
| An isolated `CODEX_HOME` with `auth.json` symlinked to `~/.codex/auth.json` runs without a second login, leaves the real config byte-identical, and takes the trust entry instead; the real `auth.json` mtime did not change | second live canary |
| `codex exec` reads stdin when it is a pipe; an unclosed stdin is the hang | `Reading additional input from stdin...` |
| Both git directories are denied: the worktree's own (`.git/worktrees/<id>/`) and the real repo's common dir, `hooks/` included - the path that would otherwise be code execution on the user's next commit | `codex sandbox` with the skill's exclusion flags, repo and worktree both outside `/tmp`, 2026-09-20. Probing this through a `codex-task` brief does not work: the brief tells the model `.git` is read-only, so it declines rather than being blocked, and a repo under `/tmp` denies for the wrong reason |

The locked flag set, the exit-code contract and the review gate are in
`skills/codex-task/SKILL.md`. Two boundaries it does not draw: reads are not
bounded (see above), and the model is hosted by OpenAI, so delegated work stays
within the medium-stakes lane below.

**Settings audit, 2026-09-19** (config reference at
learn.chatgpt.com/docs/config-file/config-reference). The skill passes these per
run because it ignores the user config; the station values are the fragment
under Station config below:

| Key | Skill passes | Station value |
|---|---|---|
| `analytics.enabled` | `false` | `false` |
| `otel.metrics_exporter` | default `none` under an empty home | `"none"` (default is `statsig`; trace and log exporters default to `none`) |
| `features.memories` | `false` | left on by the ChatGPT app; `memories.disable_on_external_context = true` added |
| `history.persistence` | `--ephemeral` | default `save-all`; 241 MB of sessions on disk that day |
| `shell_environment_policy.inherit` | `"core"` plus `include_only=[HOME,PATH,USER,LANG,SHELL,TMPDIR]`, and the skill builds the child environment itself | default; built-in filters only match `*KEY*`, `*SECRET*`, `*TOKEN*` by name. **`include_only` is accepted under `--strict-config` and then ignored at 0.155.1** - probed 2026-09-20, the whole parent environment reached the sandboxed shell, so the skill scrubs in Python and passes the key only as a second layer |

Training use of prompts under ChatGPT sign-in is governed by the ChatGPT
account's data controls, not by any Codex key. Zero data retention is an
API-key-plan property and does not apply to ChatGPT sign-in.

## Models

Codex runs OpenAI models, which are hosted third-party. Under `SPEC.md`
invariant 6 that bounds this station to **medium-stakes and hobby work**. Work
that matters runs on Anthropic or a genuinely local model, which means it does not
run here.

## Seeding

What this harness inherits natively from `~/.agents` and what has to be
installed. Shapes are defined once in
[`../SEEDING-SHAPES.md`](../SEEDING-SHAPES.md).

| Element | Shape | Station path | Notes |
|---|---|---|---|
| Skills | `NATIVE` | reads `~/.agents/skills/` | verified by headless probe 2026-08-29: it named this repo's skills from its own available-skills list |
| Subagents | `N/A` | - | no subagent tree of its own |
| Commands | `N/A` | - | no command tree; the portable route is a skill |
| Rules | `NATIVE` | repo-root `AGENTS.md` | Codex's analogue to `CLAUDE.md`, read per repo; no global rules file to seed |
| Privacy and hygiene | `FRAGMENT` | `~/.codex/config.toml` | seedable keys: `analytics.enabled = false`, `otel.metrics_exporter = "none"`, `memories.disable_on_external_context = true`. Values move only in the restrictive direction; merge into the existing tables, never replace the file (see Station config below) |
| Permissions | `FRAGMENT` | `~/.codex/config.toml` | seedable keys only: `[projects."<path>"] trust_level`. Never copy the file - it also carries credentials-adjacent state, plugin enablement and machine-specific paths. Path eligibility is bounded: each path is approved by the user at seed time, only a specific repository root is ever written, and no ancestor directory is eligible - trusting `$HOME` or a multi-repo `dev/` would silently trust every repo cloned under it afterward |
| Sandbox level | `N/A` | - | passed per invocation (`-s`), not configured |
| Hooks | `N/A` | - | no hook mechanism |
| MCP servers | `N/A` | `~/.codex/config.toml`, `[mcp_servers.<name>]` | nothing is seeded. This harness has no persistent per-tool allow or deny list, so a server cannot be bounded once registered. A desktop application's installer writes entries into this file without the user registering anything, and one such entry can expose a language runtime as a tool. The file is not even a complete inventory: an enabled plugin supplies its own server, which appears in no file at all and can carry a plugin-side `enabled = false` that config-level plugin enablement overrides. `codex mcp list` is the inventory, and its enabled column is read before trusting anything. Placement rules: [`../MCP-PLACEMENT.md`](../MCP-PLACEMENT.md) |

The single `FRAGMENT` row is the whole reason this harness cannot be seeded with
a file copy. Plugin enablement in that same file applies to **every** session
from that home, including headless ones, so a careless overwrite either grants
reach nobody intended or removes tools the user relies on. `$CODEX_HOME` selects
which file is in play, so an isolated profile is a separate seeding target rather
than a variant of this one.

## Station config

### Install and sign-in

```
brew install --cask codex      # codex-cli; 0.155.1 on both stations
codex login                    # browser sign-in with the ChatGPT plan
codex login status             # expect "Logged in using ChatGPT"
```

The ChatGPT desktop app does not provide the CLI; the cask is the only install
path this spec supports, and the same ChatGPT plan covers both. Nothing else is
installed: skills load from `~/.agents/skills` natively, and the `codex-task`
skill needs only the binary on `PATH` and a completed login.

### `~/.codex/config.toml` fragment

Applied on both stations, validated with `codex exec --strict-config`. Merge
these keys into the existing tables; the file also holds the ChatGPT app's
plugin and MCP entries and must never be replaced wholesale.

```toml
[analytics]
enabled = false

[otel]
metrics_exporter = "none"      # trace and log exporters already default to none

[memories]
disable_on_external_context = true
```

Left as the user's choice: `history.persistence` (default `save-all`;
`history.max_bytes` caps it), `memories.generate_memories` (on, set by the
ChatGPT app; turn off for repos holding client code), `model` and
`model_reasoning_effort` (station taste, `gpt-6-astra` / `high` on desktop).

### Verify

```
codex exec --strict-config -s read-only --ephemeral --json 'Reply with exactly OK' </dev/null
```

An unrecognized key errors out here; a parse-clean file returns one
`agent_message` item with `OK`. Then confirm the delegation skill end to end:
`python3 -m unittest discover -s ~/.agents/skills/codex-task/tests` (offline,
27 cases), and one live `codex_task.py run` on a scratch repo with a single
allowed file.

An `AGENTS.md` template remains a backlog item in `tasks/plan.md`.
