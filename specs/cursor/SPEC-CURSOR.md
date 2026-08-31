# SPEC-CURSOR.md - Cursor station

Cursor's agent, in the IDE and in the `cursor-agent` CLI. Both read the same
customization tree under `~/.cursor/`. Notable here as the **only harness other
than Claude Code and Gemini CLI that has all three trees**, and the only one that
picks up this repo's subagents without any extra work.

## Skills: nothing to install

Cursor reads **`~/.agents/skills/`** as a user-level location. Cloning this repo
to `~/.agents` is the entire setup.

| Scope | Paths |
|---|---|
| Project | `.agents/skills/`, `.cursor/skills/` |
| Project compatibility | `.claude/skills/`, `.codex/skills/` |
| User | **`~/.agents/skills/`**, `~/.cursor/skills/` |
| User compatibility | `~/.claude/skills/`, `~/.codex/skills/` |

Discovery is recursive, and a skills folder anywhere inside a repository is
picked up, with nested skills automatically scoped to the directory they sit in
as if they carried a `paths` glob.

Frontmatter: `name` and `description` required, plus optional `paths`,
`disable-model-invocation` and `metadata`. Skills are invoked from the `/` menu
or selected by the model from the description.

Cursor ships its own bundled skills separately at **`~/.cursor/skills-cursor/`**,
managed by a `.sync-manifest.json` it maintains itself. Observed on this machine
2026-08-08 with 19 built-ins, among them `create-skill`, `create-subagent`,
`create-hook` and `review-security`. Leave that directory alone; it is Cursor's,
not a place to put anything.

## Subagents: project-level only in the CLI, seeded per repo

Cursor's docs list project and user locations, but in the `cursor-agent` CLI
**only the project-level `.cursor/agents/` actually loads** - the user-level
paths and the documented `~/.claude/agents/` compatibility location do not
(verified by invocation probes 2026-08-27 on build 2026.08.25; the IDE may
differ). Symlinked definitions and Claude-format frontmatter (including a
`tools` field) both work at the project level, so this repo's subagents run
unmodified once planted.

The seed is one command per repo the CLI will work in:

```bash
bash ~/.agents/sync-skills.sh --cursor <repo>
```

It plants `<repo>/.cursor/agents/` with leaf symlinks into
`~/.agents/agents/`, idempotent and non-clobbering like the main sync, and it
treats the repo as not its own: entries git tracks are never touched or
pruned. The links are absolute paths, so before planting it ensures the
directory is ignored, appending `.cursor/agents/` to the repo-local
`.git/info/exclude` when no ignore rule covers it.

| Scope | Paths per docs | CLI observation 2026-08-27 |
|---|---|---|
| Project | `.cursor/agents/`, `.claude/agents/`, `.codex/agents/` | `.cursor/agents/` loads (invocation-verified) |
| User | `~/.cursor/agents/`, `~/.claude/agents/`, `~/.codex/agents/` | none load (real file and symlink both probed) |

Same shape as Claude Code: a markdown file whose body is the system prompt.
Frontmatter is `name`, `description`, `model` (`inherit` or an id), `readonly`
and `is_background`; none are required (`name` defaults from the filename), and
unknown Claude Code fields are tolerated. There is no list command and print
mode cannot enumerate the roster, so verify a definition by invoking it
("use the X subagent to ...") rather than by asking for a listing.

Invocation is `/name <prompt>`, natural language ("use the advisor subagent
to..."), or automatic delegation from the description. Three built-ins run
without configuration: Explore, Bash and Browser.

## What does not carry over

**Commands.** Cursor commands are markdown in `.cursor/commands/` and
`~/.cursor/commands/`, combined into one `/` menu. No Claude or Codex
compatibility path is documented for commands, unlike skills and subagents, so
this repo's `commands/` tree does not appear. The portable route is the same one
the other specs name: re-express a command as a skill carrying
`disable-model-invocation: true`, which Cursor supports.

**Rules.** Cursor project rules are `.mdc` files in `.cursor/rules/`, and a plain
`.md` file dropped there is ignored rather than treated as a rule. User Rules are
free text held in Cursor's settings rather than a file on disk, so
[`AGENTS.md`](../../AGENTS.md) cannot be pointed at from there. Team Rules come from
the Cursor dashboard on paid team plans.

**AGENTS.md** is read at a repository root and in any subdirectory, with the more
specific file winning. There is no user-level `AGENTS.md` path, so the repo-root
copy is the only place this repo's rules reach Cursor as rules.

## Hooks

`hooks.json`, project-level in `.cursor/hooks.json` and user-level in
`~/.cursor/hooks.json`. Configs layer rather than override: every hook registered
at every location runs. Command paths resolve relative to the `hooks.json` that
declares them, so scripts conventionally live beside it in `hooks/`.

Six events: `beforeSubmitPrompt`, `beforeShellExecution`, `beforeMCPExecution`,
`beforeReadFile`, `afterFileEdit`, `stop`. A hook reads the event JSON on stdin
and writes JSON on stdout; `beforeShellExecution` and `beforeMCPExecution` can
return `allow`, `deny` or `ask` with a message. The system is documented as beta.

The CLI does not deliver the full set. Community reports have `cursor-agent`
sending only the shell events, so a hook that enforces something important should
not be assumed to fire there. Verify per event before relying on one.

## Permissions, and a caution

Cursor has **two separate permission systems**, which is the thing most likely to
catch you out:

| Surface | File |
|---|---|
| IDE | `~/.cursor/permissions.json`, `<workspace>/.cursor/permissions.json` |
| CLI | `~/.cursor/cli-config.json`, and `<project>/.cursor/cli.json` for permissions only |

Both IDE files are optional, accept JSONC, are re-read on change, and concatenate
rather than replace when both exist. CLI tokens are `Type(pattern)`, for example
`Shell(git)` and `Read(.env*)`. `CURSOR_CONFIG_DIR` relocates the whole
directory.

**Verified semantics (2026-08-28, build 2026.08.25, all headless):**

- **Token matching is glob-based and a bare literal never matches.**
  `Read(secrets.json)` failed to block a workspace-root `secrets.json`;
  `Read(**/secrets.json)` blocked it, and `Read(*.pem)` blocked a root-level
  `.pem`. Write every deny token with a wildcard - `**/` prefix as the house
  form. A literal token is silently dead, which is worse than absent because it
  reads as protection.
- **Shell allow tokens match the literal first word.** With `Shell(date)`
  allowed, `date` ran and `whoami` was rejected; a model that wraps the command
  (`rtk ls`) no longer matches `Shell(ls)`.
- **A project `.cursor/cli.json` REPLACES the global permissions object
  entirely, deny list included.** Verified live: a fixture whose project file
  carried `deny: []` read a `secrets.json` that the working global deny blocks
  everywhere else, and the global `Shell(ls)` allow stopped applying there too.
  So every project file must replicate the full deny set, and the schema
  enforces shape: `permissions` requires BOTH `allow` and `deny` keys or the
  CLI errors out.
- **Headless denial shape** (`--output-format stream-json`): a
  `tool_call`/`completed` event carrying
  `shellToolCall.result.rejected {command, workingDirectory, reason,
  isReadonly}`; the turn continues and the model reports the rejection. The
  init event carries `permissionMode`.
- **Trust persists.** The first run in a new cwd stops to ask; `--trust`
  answers it once and later runs proceed without the flag. `-f/--force` and
  `--yolo` bypass the allowlist and never belong in a seat spawn.

**File modes on this config do not stick (verified 2026-08-29).**
`~/.cursor/cli-config.json` holds an `authCacheKey` alongside the permissions
block and ships world-readable. Setting it to 600 held for under an hour: the
CLI rewrote its own config during normal use and restored the permissive mode.
Treat that as general - a harness that owns a file will reset its mode, so
per-file hardening on harness-managed config is not a durable control anywhere
in this tree. The durable equivalent is the mode on the *home directory*, which
no harness rewrites.

**What `--trust` switches on.** Trusting a checkout activates that repo's own
`.cursor/cli.json`, and per the replacement rule above, that file substitutes for
the global permissions object rather than adding to it. So `--trust` on an
unfamiliar repository can silently retire every global deny in favor of whatever
that repository ships. Read the project file before trusting a checkout you did
not write.

**Peer-reported, not probed here.** Two findings from another agent's probing,
recorded because they change how a spawn must be written, and carried at lower
confidence until reproduced:

- `cursor-agent -p` refuses a workspace that has not been trusted, so an
  automated run in a fresh checkout never starts without `--trust`.
- `--sandbox` governs shell commands only. The agent's native write tool is
  governed separately by `Write(pathOrGlob)` rules, so a sandbox that correctly
  blocks a shell write can still be routed around by the write tool when no
  `Write` rule exists. Whether a `Write` deny actually refuses is unestablished,
  so that axis is unproven rather than covered.

Two known problems, both worth knowing before granting anything:

- Granting a permission interactively inside a project writes it to the global
  `~/.cursor/cli-config.json`, while the project file takes precedence, so the
  grant does not take and the prompt returns.
- **GHSA-v64q-396f-7m79**: the CLI loads `<project>/.cursor/cli.json`
  automatically, so running it inside a repository you do not trust combines a
  permissive config with prompt injection delivered through that repo's
  `.cursor/rules/*.mdc` into remote code execution. The
  deny-replacement finding above is the same mechanism: an untrusted repo's
  `cli.json` silently nullifies your global deny list. Treat an untrusted
  repo's `.cursor/` directory as hostile input, and use `--workspace`
  deliberately.

**The CLI's defaults are worth knowing before the first run.** Installing
`cursor-agent` and invoking it once writes `~/.cursor/cli-config.json` even
without signing in. Observed on 2026-08-08, that default ships
`approvalMode: "allowlist"` with `permissions.allow` at just `Shell(ls)`, which
is appropriately tight, but also `sandbox.mode: "disabled"` and an **empty deny
list**, so nothing stops a read of `.env`. Under this repo's rule that the deny
list is the hard control and ignore files are only defense in depth, that is the
entry to fill in first. It sits beside the IDE's `permissions.json` rather than
colliding with it, since the two surfaces read different files.

Seed the deny list from the secret-bearing subset of
[`secrets-exclusions.gitignore`](../secrets-exclusions.gitignore) - the patterns
naming credentials, keys and state files rather than every ignore entry - written
as `Read(**/...)` tokens in glob form. The literal form was
probed and proved dead, with the canary read succeeding until the glob form
landed. Leave `sandbox.mode` at `disabled` unless it is being changed
deliberately: enabling it changes how commands run, so it is a decision rather
than cleanup.

`.cursorignore` guards Cursor's file-reading tools only. It does not stop the
agent reading the same file with `cat`, so it is not a secrets control; the deny
list and a `beforeShellExecution` hook are. That matches the position
[`AGENTS.md`](../../AGENTS.md) already takes on ignore files as defense in depth.

## Models

Cursor's own inference layer, fronting several vendors including Anthropic
models. Requests route through Cursor's infrastructure whichever model is
selected, so `SPEC.md` invariant 6 treats this as **hosted third-party** and
bounds the station to medium-stakes work. Picking a Claude model inside Cursor
does not make it an Anthropic-direct path.

`agent --list-models` prints what the signed-in account can reach.

## Verification status

Cursor IDE 3.14.7 and `cursor-agent` 2026.08.25-3e8eec8 are installed on this
machine (the CLI self-updated from 2026.08.04 during the 2026-08-27 pass), and
`~/.cursor/skills-cursor/` was inspected directly on **2026-08-08**.
Everything above other than the observations dated below is from Cursor's
documentation as of 2026-08-08.

Verified **2026-08-27**, signed in (`cursor-agent login`, a browser flow):

- **Skill discovery CONFIRMED.** A print-mode probe (`cursor-agent --trust -p`)
  enumerates the full `~/.agents/skills/` tree alongside Cursor's built-ins and
  installed plugin skills. A first run in a new directory stops to ask for
  workspace trust; `--trust` answers it non-interactively.
- **Subagent loading CONFIRMED, project-level only** (same day, after the CLI
  self-updated to 2026.08.25). Invocation probes - the reliable test, since
  enumeration questions return only built-ins regardless - showed user-level
  definitions never load (real file and symlink both tried), while a
  project-level `.cursor/agents/` definition runs, including a symlinked
  Claude-format file from `~/.agents/agents/`. The subagents section above
  carries the resulting seed procedure; the first seeded repo ran the `reader`
  subagent end to end.

## Seeding

What this harness inherits natively from `~/.agents` and what has to be
installed. Shapes are defined once in
[`../SEEDING-SHAPES.md`](../SEEDING-SHAPES.md).

| Element | Shape | Station path | Notes |
|---|---|---|---|
| Skills | `NATIVE` | reads `~/.agents/skills/` | verified by headless probe 2026-08-29: it named this repo's skills from its own available-skills list |
| Subagents | `LINK` | `<repo>/.cursor/agents/` | project-level ONLY - the CLI does not read a global subagent tree, so each repo is seeded with `sync-skills.sh --cursor <repo>`. It does read `~/.claude/agents/` as a compatibility path |
| Commands | `N/A` | - | no portable command form |
| Rules | `NATIVE` | repo-root `AGENTS.md` | read per repo; no global rules file to seed |
| Permissions, global | `FRAGMENT` | `~/.cursor/cli-config.json` | the `permissions` object only. The file also holds an auth cache and UI state, and the CLI rewrites it during normal use, so a whole-file copy is both destructive and short-lived |
| Permissions, project | `COPY` | `<repo>/.cursor/cli.json` | must be COMPLETE, not a delta: a project file replaces the global permissions object outright, deny list included, and the schema requires both `allow` and `deny` keys. Never overwrite an existing project file without showing the deny-list delta first - a parity check would otherwise silently re-widen a repo whose deny list someone narrowed on purpose |
| Hooks | `COPY` | `~/.cursor/hooks.json` | six-event model; the Claude Code hook scripts have not been ported, so no seed source exists yet. When one does, show the delta before overwriting an existing file rather than replacing it wholesale |
| IDE permissions | `N/A`, pending probe | `~/.cursor/permissions.json` | a separate system from the CLI; the two do not share state. Schema not probed, so no keys can be named - and an unkeyed merge into a permissions file is an unbounded permission edit. Not seeded until probed |
| MCP servers | `N/A`, pending probe | `~/.cursor/mcp.json` or `<repo>/.cursor/mcp.json` | neither file exists on this station. Nothing is seeded until a probe settles whether the CLI permissions object can deny an MCP tool by name, since a server that cannot be bounded per tool cannot be seeded at all. The CLI keeps its own approved list (`cursor-agent mcp enable`/`disable`), and `--approve-mcps` auto-approves every server, so it is never seeded under the restrictive-direction rule. Placement rules: [`../MCP-PLACEMENT.md`](../MCP-PLACEMENT.md) |

Two rows here encode traps that have already cost this station. The project
permissions row is `COPY`-and-complete rather than `FRAGMENT` precisely because
merging into it is what produces a file that looks configured and enforces
nothing. And the global row is `FRAGMENT` because per-file hardening does not
survive: the CLI rewrote its own config and reset a tightened mode within an
hour.

## Station config

Not adapted beyond the table above. Tracked in `tasks/plan.md`.
