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
| Permissions | `FRAGMENT` | `~/.codex/config.toml` | seedable keys only: `[projects."<path>"] trust_level`. Never copy the file - it also carries credentials-adjacent state, plugin enablement and machine-specific paths. Path eligibility is bounded: each path is approved by the user at seed time, only a specific repository root is ever written, and no ancestor directory is eligible - trusting `$HOME` or a multi-repo `dev/` would silently trust every repo cloned under it afterward |
| Sandbox level | `N/A` | - | passed per invocation (`-s`), not configured |
| Hooks | `N/A` | - | no hook mechanism |
| MCP servers | `N/A` | `~/.codex/config.toml`, `[mcp_servers.<name>]` | nothing is seeded. This harness has no persistent per-tool allow or deny list, so a server cannot be bounded once registered. A desktop application's installer can write entries into this file without the user registering anything, and one such entry can expose a language runtime as a tool, so the inventory is taken with `codex mcp list` and the enabled column is read before trusting the file. Placement rules: [`../MCP-PLACEMENT.md`](../MCP-PLACEMENT.md) |

The single `FRAGMENT` row is the whole reason this harness cannot be seeded with
a file copy. Plugin enablement in that same file applies to **every** session
from that home, including headless ones, so a careless overwrite either grants
reach nobody intended or removes tools the user relies on. `$CODEX_HOME` selects
which file is in play, so an isolated profile is a separate seeding target rather
than a variant of this one.

## Station config

Not yet adapted beyond the table above. An `AGENTS.md` template remains a backlog
item in `tasks/plan.md`.
