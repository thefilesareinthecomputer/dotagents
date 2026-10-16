# SPEC-OPENCODE.md - opencode station

The open-source lane: MIT, TypeScript, provider-agnostic across 75+ providers,
TUI plus a client/server split. Config lives at `~/.config/opencode/`. It is the
only harness here with a first-class way to ask what it discovered without
authenticating, which makes it the cheapest place to check that a skill parses.

## Skills: nothing to install

opencode reads **`~/.agents/skills/`** as a global location. Cloning this repo to
`~/.agents` is the entire setup.

| Scope | Paths |
|---|---|
| Project | `.opencode/skills/<name>/SKILL.md`, `.claude/skills/`, `.agents/skills/` |
| Global | `~/.config/opencode/skills/`, `~/.claude/skills/`, **`~/.agents/skills/`** |

Project discovery walks up from the working directory to the git worktree root,
so a skill in an ancestor directory still loads.

Frontmatter: `name` and `description` required, with `license`, `compatibility`
and `metadata` recognized and unknown fields ignored. `name` must match the
containing directory and match `^[a-z0-9]+(-[a-z0-9]+)*$`; `description` is
capped at 1024 characters.

Skills load on demand through a native `skill` tool rather than being injected up
front. The agent sees names and descriptions, then calls
`skill({ name: "..." })` to pull the body in.

**Confirmed by observation 2026-08-08** on this machine with opencode 1.18.15:
`opencode debug skill` run from a directory outside any repository returned all
24 of this repo's skills plus opencode's one built-in, with no setup step. It
resolved some through `~/.agents/skills/` and some through `~/.claude/skills/`,
which are the same files by symlink, and deduplicated them by name.

## The debug commands are worth knowing

`opencode debug skill` prints every discovered skill as JSON with its resolved
`location`, which makes it the fastest way to answer "does this skill parse and
where is it being found". `opencode debug config` shows resolved configuration,
`opencode debug paths` shows the data, config, cache and state roots, and
`opencode debug agent <name>` shows one agent's configuration.

None of these need a signed-in provider, so this station doubles as a lint step
for the skills tree even when the work is happening elsewhere. It is more lenient
than Copilot, though, so a clean run here does not mean a skill is portable; see
[`SPEC-COPILOT.md`](../copilot/SPEC-COPILOT.md).

## Permissions

Skill access is filtered by pattern in `opencode.json`, which no other harness
here offers:

```json
"permission": {
  "skill": { "*": "allow", "internal-*": "deny", "experimental-*": "ask" }
}
```

`allow` loads without prompting, `ask` requires approval, `deny` hides the skill
entirely. Patterns can differ per agent, so a narrow agent can be given a narrow
slice of the tree. Setting `"skill": false` under `tools` removes the skill tool
altogether. Config is read once at startup and is not hot-reloaded, so a change
needs a restart.

## What does not carry over

Only `skills/`. opencode agents are markdown in `~/.config/opencode/agent/` and
`.opencode/agent/`, and it reads no `~/.claude/agents/` compatibility path, so
this repo's `agents/` tree does not appear; `opencode agent list` showed only
built-ins on 2026-08-08. Commands are a separate feature again and are not read
from `~/.agents/commands/`. The portable route for a command is a skill, as
elsewhere.

`AGENTS.md` is the project knowledge file, matching the convention this repo
already follows at its root.

## Models

Any of 75+ providers, chosen per session. `SPEC.md` invariant 6 binds on the
model rather than the harness: work that matters runs on Anthropic or a genuinely
local model, and pointing opencode at a hosted third-party provider bounds that
session to medium-stakes work.

## A naming caution

Two projects have carried this name. The one specced here is the TypeScript
opencode, `sst/opencode`, now developed at `anomalyco/opencode`. The original Go
opencode was archived and continues as Charm's Crush. Installed here from npm as
`opencode-ai`.

## Station config

**Remote control (invariant 7).** opencode's network surface is its own server:
`opencode serve`, `opencode web` and `opencode acp` listen on `127.0.0.1:4096`
with no authentication unless `OPENCODE_SERVER_PASSWORD` is set, and its
security policy makes securing that server the user's job. Two January 2026
advisories (CVE-2026-22812, an unauthenticated local server any website could
drive through permissive CORS, fixed in 1.0.216; CVE-2026-22813, a web UI XSS,
fixed in 1.1.10) and a September 2026 one (GHSA-632h-h47v-g4x4, a malicious
page reaching the `/global/upgrade` endpoint of a running server, fixed in
1.18.22) all needed the server running, so on this station none of the three
subcommands ever runs and the version floor is 1.18.22. Session sharing is the
`share` config key (`manual`, `auto`, `disabled`); a seed sets `disabled`. The
binary names `api.opencode.ai`, `models.opencode.ai` (the model list, off with
`OPENCODE_DISABLE_MODELS_FETCH=1`), `console.opencode.ai` and `app.opencode.ai`;
whether any usage telemetry leaves the process is unverified (OpenTelemetry SDK
strings are present, no opt-out key was found, and users have reported telemetry
with no switch). The permission system is not a sandbox by the project's own
policy, so a run here is bounded by the bench's `sandbox-exec` profile, never by
opencode. The laptop's npm install of `opencode-ai` 1.18.15 (2026-08-08, below
the floor, empty config, no server process, no credentials on disk) and its
state folders were removed on 2026-10-15; any reinstall is pinned from Homebrew
after an egress audit of that version.

Not adapted beyond that. No `~/.config/opencode/opencode.json` is written by this repo, and
opencode's plugin model is TypeScript rather than shell hooks, so the Claude Code
hook scripts have no direct analogue and would need rethinking rather than
porting, the same conclusion [`SPEC-PI.md`](../pi/SPEC-PI.md) reaches. Tracked in
`tasks/plan.md`.
