# SPEC-COPILOT.md - GitHub Copilot station

GitHub Copilot's agent, in VS Code and in the `copilot` CLI. The two share one
user-level configuration root at `~/.copilot/`, so setting up either sets up
both. This is the station that surfaced the skill-portability problem recorded
below, and the only one so far to reject any of this repo's skills.

## Skills: nothing to install

Copilot reads **`~/.agents/skills/`** as a personal skill location. Cloning this
repo to `~/.agents` is the entire setup.

| Scope | Paths |
|---|---|
| Project | `.github/skills/`, `.agents/skills/`, `.claude/skills/` |
| Personal | `~/.copilot/skills/`, **`~/.agents/skills/`** |
| Other | plugin-bundled skills, and directories added with `copilot skill add` |

A project skill wins over a personal skill of the same name.

Frontmatter: `name` (max 64 characters) and `description` (max 1024) required,
plus optional `argument-hint`, `user-invocable` (default true),
`disable-model-invocation` (default false) and the experimental `context`, which
accepts `fork` to run the skill in a subagent and return only its result. In VS
Code, `context: fork` needs `github.copilot.chat.skillTool.enabled`.

Skills are invoked from the `/` menu or chosen by the model from the
`description`. `copilot skill list` prints everything discovered, and `/skills`
does the same inside a VS Code chat.

**Confirmed by observation 2026-08-08** with Copilot CLI 1.0.78 on this machine:
`copilot skill list` names `~/.agents/skills` as a personal source in its own
help text and loads all 24 of this repo's skills from it, with no setup step.

## The eight skills Copilot refused, and what they exposed

The first run of `copilot skill list` loaded only 16 of 24. The 8 failures were
ours rather than Copilot's:

| Cause | Skills |
|---|---|
| `description` over the 1024-character limit | `ai-agent-project-scaffold`, `ai-slop-magic-eraser`, `my-security-review-checklist`, `obsidian-kg` |
| Frontmatter fails to parse, a bare `: ` in the plain description scalar | `cover-me`, `dimensional-data-modeling`, `meta-loop`, `reflect` |

Both are real violations of the Agent Skills specification, which caps
`description` at 1024 characters and expects valid YAML. Claude Code accepts all
24, which is why they stayed broken.

Fixed the same day. Every description was rewritten into a 600-800 character
house band, the colons became spaced hyphens, and both `copilot skill list` and
`opencode debug skill` now return all 24 with no failures. `skill-authoring`
carries both checks and names these two commands as the way to run them, since
neither needs authentication and both report the file and the reason.

Copilot is the strictest parser of the harnesses tried here, which is what makes
it useful beyond its own station: it is the cheapest available conformance test
for the skills tree.

## Rules: the global rules file already reaches it

VS Code reads **`~/.claude/CLAUDE.md`** when `chat.useClaudeMdFile` is enabled,
along with a workspace-root `CLAUDE.md` and `.claude/CLAUDE.md`. On any machine
set up per [`SPEC-CLAUDE-CODE.md`](../claude-code/SPEC-CLAUDE-CODE.md) that file already exists, so the
global rules carry over with one setting rather than a second copy.

| Artifact | Workspace | User |
|---|---|---|
| `AGENTS.md` | repo root, subdirectories when nested support is on | none |
| `CLAUDE.md` | root, `.claude/CLAUDE.md` | `~/.claude/CLAUDE.md` |
| Always-on instructions | `.github/copilot-instructions.md` | none |
| Scoped instructions | `.github/instructions/*.instructions.md` | `~/.copilot/instructions/` |
| Prompt files | `.github/prompts/*.prompt.md` | user profile |
| Custom agents | `.github/agents/*.agent.md` | `~/.copilot/agents/` |
| Hooks | `.github/hooks/` | `~/.copilot/hooks/`, or inline in `settings.json` |
| MCP | project `mcp-config.json` | `~/.copilot/mcp-config.json` |

Relevant settings: `chat.useAgentsMdFile`, `chat.useNestedAgentsMdFiles`
(experimental), `chat.useClaudeMdFile`, `chat.instructionsFilesLocations`,
`chat.agentSkillsLocations`. An `*.instructions.md` file takes an `applyTo` glob
so it loads only for matching files, which is the closest analogue to Cursor's
`.mdc` rule globs.

When Agent Host is on, VS Code reads user-level customization from the
harness-agnostic `~/.copilot` and `~/.claude` directories rather than from the VS
Code profile, which is what makes one setup serve both the editor and the CLI.

## What does not carry over

**Subagents.** Copilot's custom agents are `*.agent.md` in `~/.copilot/agents/`.
The concept maps onto this repo's `agents/` tree but the format and extension do
not, so nothing ports without a conversion. Unlike Cursor, Copilot reads no
`~/.claude/agents/` compatibility path.

**Commands.** No `~/.agents/commands/` equivalent. Copilot's prompt files
(`*.prompt.md`) are the nearest artifact, and again the format differs. The
portable route is a skill carrying `disable-model-invocation: true`, which
Copilot supports directly.

## The CLI

`npm install -g @github/copilot`, config root `~/.copilot`, relocatable with
`COPILOT_HOME`. Settings live in `~/.copilot/settings.json` and can be changed
in-session with `/settings KEY VALUE`; `copilot help config` lists every key.
VS Code bundles its own copy of the same binary under the `github.copilot-chat`
extension and offers to fetch it on first use, so the two can be different
versions on one machine.

**PATH gotcha, observed 2026-08-27:** VS Code's integrated terminal prepends the
bundled copy's directory (`.../globalStorage/github.copilot-chat/copilotCli`) to
`PATH`, so inside that terminal `copilot` resolves to the bundled version even
when a newer npm-installed one exists (`which -a copilot` shows both). The
injection comes from the extension, not from any shell rc file; plain shells
resolve the npm copy. Both copies share `~/.copilot`, so the skew is version
only, not configuration.

Authentication is the CLI's own device flow: run `copilot` interactively and use
`/login`. It does not reuse `gh`'s keyring token, and it stores its credentials
in the system keychain rather than under `~/.copilot`, so a bare config root
says nothing about login state - verify with a minimal `copilot -p` turn, which
errors fast when unauthenticated.

`gh skill` installs skills from GitHub repositories, in public preview and
needing GitHub CLI 2.90.0 or later. Treat anything it fetches as untrusted:
GitHub does not verify skills, and `gh skill preview` exists so the content can
be read before it lands. That is the same posture
[`my-security-review-checklist`](../../skills/my-security-review-checklist/) already
requires for third-party agent tooling.

## Permissions (verified 2026-08-28, CLI 1.0.81)

**Grants are per-invocation flags, not persistent config.** There is no
persistent per-tool allow/deny list; `~/.copilot/config.json` carries only
`defaultPermissionMode` (`manual` / `assisted` / `allow-all` - **interactive
sessions only**, explicitly ignored in `-p` runs), `trustedFolders` (folders
granted read/execute), and `allowedUrls`/`deniedUrls` (deny takes precedence).
Everything else rides the spawn: `--allow-tool` / `--deny-tool` /
`--allow-all-tools` / `--allow-all-paths` / `--add-dir` / `--allow-url`.

**Headless semantics, verified:**

- **Read-only commands auto-approve with no grant at all** - `whoami` ran with
  only `shell(date)` allowed. Grants gate the write-shaped and destructive
  commands, so a seat needs far fewer `--allow-tool` entries than its full
  command surface.
- **Narrow grants are word-prefix**: `--allow-tool 'shell(touch)'` let
  `touch probe-file.txt` run; without it the same command hard-denied. The
  documented prefix form `shell(npm run test:*)` extends this to subcommands
  (doc-derived, not separately probed).
- **Denial shape** (`--output-format json`, JSONL): `tool.execution_complete`
  with `error: {"message": "Permission denied and could not request permission
  from user", "code": "denied"}`; the turn continues, the model reports the
  denial, and the process exits non-zero when the task failed. There is no
  hanging prompt headless.
- **No interactive trust prerequisite** for working in the spawn cwd;
  `--add-dir` extends file access beyond it, `trustedFolders` is the persistent
  equivalent.
- `-s/--silent` prints only the agent response; `--log-level none` quiets the
  banner but the JSONL stream stays verbose (model-call telemetry rides it) -
  filter by `type` prefix (`tool.`, `assistant.message`).

**Seat guidance:** reach for `--available-tools` first - per the section below it
is the only flag that makes this harness deny-by-default, and it decides which
tools exist for the run rather than which are approved. Within that surface,
replace `--allow-all-tools` with the handful of write-shaped commands the seat
genuinely needs (`--allow-tool 'shell(git)'`, `--allow-tool 'write'`, ...) and let
read-only auto-approval carry the rest; add `--deny-tool` for anything that must
stay off even if a broad allow lands later.

### The two permission flags take different vocabularies (verified 2026-08-29)

This is the trap on this harness, and it is the same shape as Cursor's dead
literal token: a rule that looks correct, matches nothing, and reports nothing.

| Flag | Vocabulary | Works | Silent no-op |
|---|---|---|---|
| `--deny-tool` / `--allow-tool` | the documented `kind(argument)` permission syntax | `shell(printenv)` | `bash` |
| `--available-tools` | the runtime's **internal tool names** | `bash` | `shell` |

Probed with a UUID injected into the spawn's environment and requested via
`printenv` - only the shell tool can reach process environment, so the value
appearing in the reply proves shell executed, and the value is unguessable.

- `--deny-tool 'shell(printenv)'` blocked it, with and without
  `--allow-all-tools`, confirming that denial outranks a blanket allow.
- `--deny-tool bash` did **not** block it across two runs. `bash` is the
  internal tool name and is not a permission token.
- `--available-tools=view,glob,grep` blocked it 5/5; `--available-tools=bash,view`
  permitted it 3/3. So that flag enforces, and it is differential rather than
  simply breaking the session.
- `--available-tools=shell` blocks everything, because `shell` names no tool and
  the resulting set is empty.

`--available-tools` is therefore the only flag that turns this harness's
permissive default into deny-by-default, and it is the one worth reaching for.

**The internal tool names**, read from a live run's JSON on CLI 1.0.81: `bash`,
`create`, `edit`, `view`, `glob`, `grep`, `task`, `skill`, `sql`,
`session_store_sql`, `web_fetch`, `fetch_copilot_cli_documentation`,
`list_agents`, `read_agent`, `write_agent`, `list_bash`, `read_bash`,
`stop_bash`.

**Granting `bash` forfeits the boundary.** A tool allowlist bounds a seat only
while every allowed tool is narrow; `bash` is every capability, and `task`,
`skill`, `sql` and `web_fetch` are similarly general. So an allowlist containing
`bash` withholds whole tools without bounding the filesystem - a surface
reduction, not containment. The test for any seat: if it needs a shell, tool
permissions cannot bound it and the boundary has to be the OS.

Pin the version beside any rule written from this section. `github/copilot-cli`
issue #2722 is open and reports pattern-scoped denies blocking everything or
nothing and denies not cross-applying between tools, so a release may change
enforcement. A version bump is a reason to re-probe, not a reason to relax.

## Models

Copilot's hosted inference, fronting OpenAI, Anthropic and Google models through
GitHub's infrastructure. `SPEC.md` invariant 6 treats that as **hosted
third-party** and bounds this station to medium-stakes work, whichever model is
selected in the picker.

Content exclusion is configured in GitHub's web UI at org or enterprise level
only, with no in-repo file, which is why the exclusion table in
[`SPEC-CLAUDE-CODE.md`](../claude-code/SPEC-CLAUDE-CODE.md) lists Copilot as having nothing to write here.

## Verification status

Copilot CLI 1.0.78 installed and run on this machine **2026-08-08**; skill
discovery and the eight failures are confirmed by observation. VS Code 
customization paths and settings keys are from Microsoft's documentation on the
same date and are not separately confirmed.

Re-verified **2026-08-27**: standalone CLI 1.0.81 installed via
`npm install -g @github/copilot` (the only copy previously on this machine was
VS Code's bundled 1.0.78); `copilot skill list` loads all 32 of this repo's
skills from `~/.agents/skills` with zero failures, no authentication needed.
Signed in the same day via the `/login` device flow; credentials land in the
system keychain, not `~/.copilot` (the directory staying bare is not evidence
of a missing login - probe with a `copilot -p` turn instead). An authenticated
in-session probe enumerates the full repo skills tree.

## Seeding

What this harness inherits natively from `~/.agents` and what has to be
installed. Shapes are defined once in
[`../SEEDING-SHAPES.md`](../SEEDING-SHAPES.md).

| Element | Shape | Station path | Notes |
|---|---|---|---|
| Skills | `NATIVE` | reads `~/.agents/skills/` | verified by `copilot skill list`, which needs no sign-in and names the file and reason for every rejection - the strictest parser in the tree and the cheapest conformance test |
| Subagents | `N/A` | - | `*.agent.md` differs enough that nothing ports without conversion |
| Commands | `N/A` | - | no command tree; the portable route is a skill |
| Rules, IDE | `FRAGMENT` | VS Code `settings.json` (`~/Library/Application Support/Code/User/settings.json` on macOS, `$VSCODE_PORTABLE` aware) | one key: `chat.useClaudeMdFile`. Turning it on is what makes the global rules file apply, and it is the highest-value single change for this harness |
| Rules, project | `POINTER` | `.github/copilot-instructions.md` | a short file pointing at the repo's `AGENTS.md`, so the two never drift into two rule sets |
| Permissions | `N/A` | - | there is no persistent per-tool allow/deny list. Grants ride every spawn, so there is nothing to seed and a caller that omits them has no boundary |
| Trust and URLs | `FRAGMENT`, pending probe | UNVERIFIED - `~/.copilot/config.json` self-describes as application-managed and holds none of these keys on a default install; this spec's own table puts user settings in a `settings.json` that does not exist here | keys, once the location is confirmed: `defaultPermissionMode`, `trustedFolders`, `allowedUrls`, `deniedUrls`. These widen reach, so a seed moves them only in the restrictive direction - `deniedUrls` and `defaultPermissionMode: manual`. `allow-all` is never seeded, and `trustedFolders` entries are approved individually. Seeds nothing until probed |
| Hooks | `N/A`, pending probe | `~/.copilot/hooks/` per this spec's own table, or inline in a settings file | UNVERIFIED which file the CLI actually reads. The station's `config.json` self-describes as application-managed, so writing hooks there risks either being overwritten or reporting hooks installed while nothing enforces them. Do not seed until probed |
| MCP servers | `N/A` | `~/.copilot/mcp-config.json`, not created by default | nothing is seeded: as with permissions, every control rides the spawn, so a caller that omits the flags has no boundary. `github-mcp-server` is built into the CLI and enabled by default with a subset of its tools, so a server is present whether or not that file exists; `--disable-builtin-mcps` and `--disable-mcp-server <name>` turn servers off per invocation, and `--add-github-mcp-tool`/`--add-github-mcp-toolset` widen the tool set, so neither is ever seeded widened. Alone among the harnesses here it allowlists whose initialization instructions reach the system prompt, which `--allow-all-mcp-server-instructions` disables and a seed therefore never sets. Placement rules: [`../MCP-PLACEMENT.md`](../MCP-PLACEMENT.md) |

The `N/A` on permissions is the important row. Every other harness here has some
persistent surface to seed; this one has none, so its boundary exists only in the
arguments of whatever spawns it. A sync can make this station tidy but it cannot
make it bounded.

## Station config

Not adapted beyond the table above. No `~/.copilot/settings.json` exists on a
default install, and the Claude Code hooks have not been ported. Tracked in
`tasks/plan.md`.
