# specs/

One folder per agent harness: the station spec, plus every file that spec seeds.
A spec states what a machine's install of that harness needs around these skills, and what it already provides on its own.

`SPEC.md` at the repo root says what this repo IS. These say what a *harness*
needs around it.

| Folder | Harness | Skills setup |
|---|---|---|
| [`claude-code/`](claude-code/SPEC-CLAUDE-CODE.md) | Claude Code | `sync-skills.sh` |
| [`antigravity/`](antigravity/SPEC-ANTIGRAVITY.md) | Antigravity CLI (`agy`) | `~/.gemini/config/skills.json` |
| [`codex/`](codex/SPEC-CODEX.md) | OpenAI Codex CLI | none, reads `~/.agents/skills` |
| [`copilot/`](copilot/SPEC-COPILOT.md) | GitHub Copilot (VS Code + CLI) | none, reads `~/.agents/skills` |
| [`cursor/`](cursor/SPEC-CURSOR.md) | Cursor (IDE + CLI) | none, reads `~/.agents/skills` |
| [`goose/`](goose/SPEC-GOOSE.md) | goose | none, reads `~/.agents/skills` |
| [`gemini/`](gemini/SPEC-GEMINI.md) | Gemini CLI | none, reads `~/.agents/skills` |
| [`kimi/`](kimi/SPEC-KIMI.md) | Kimi Code CLI | none, reads `~/.agents/skills` |
| [`opencode/`](opencode/SPEC-OPENCODE.md) | opencode | none, reads `~/.agents/skills` |
| [`pi/`](pi/SPEC-PI.md) | Pi | none, reads `~/.agents/skills` |
| [`deepagents/`](deepagents/SPEC-DEEPAGENTS.md) | deepagents | passed in code |

## The folder convention

Every harness folder follows the shape `claude-code/` established:

- **`SPEC-<HARNESS>.md`** is the station spec, and the only required file.
  The filename carries the harness name so a search hit or an open tab is unambiguous on its own.
- **Seed files** - every file the spec tells a station to install (`CLAUDE.md.example`, `settings.json`, `hooks/`, status lines, keybindings) - live beside the spec as real files rather than code blocks, so they can be diffed, linted and copied directly.
  A seed file and the configured station it seeds stay in byte parity: a drift check is a `diff`, not a reading exercise.
- **Reference docs** that inform a harness beyond this station's own choices sit beside the spec they belong to (e.g. [`claude-code/CLAUDE-CONTEXT-TOPOLOGY-ONTOLOGY-AND-TEAM-HEURISTICS.md`](claude-code/CLAUDE-CONTEXT-TOPOLOGY-ONTOLOGY-AND-TEAM-HEURISTICS.md)).
- **Same-folder links are bare filenames; cross-folder links are relative** (`../copilot/SPEC-COPILOT.md`).
  Assets shared by several harnesses stay at `specs/` level: [`secrets-exclusions.gitignore`](secrets-exclusions.gitignore), [`SEEDING-SHAPES.md`](SEEDING-SHAPES.md) defining the shape vocabulary every spec's Seeding table uses, [`MCP-PLACEMENT.md`](MCP-PLACEMENT.md) carrying the position each spec's MCP row defers to, and [`HARNESS-MODELS-AND-EFFORT.md`](HARNESS-MODELS-AND-EFFORT.md) recording how each CLI enumerates models and names effort levels, stamped with the version and date it was probed.

A folder holding nothing but its spec is normal; most harnesses need no seeds.
Rules for agents editing this tree: [`AGENTS.md`](AGENTS.md).

[`claude-code/CLAUDE-CONTEXT-TOPOLOGY-ONTOLOGY-AND-TEAM-HEURISTICS.md`](claude-code/CLAUDE-CONTEXT-TOPOLOGY-ONTOLOGY-AND-TEAM-HEURISTICS.md) is the general standard behind the Claude Code station: what lives where in a Claude Code deployment - the sorting grid, the mechanisms and their context costs, the memory/retrieval layers, and how a team runs one repository as the shared source of truth for its context, skills and settings - independent of this station's choices.

Claude Code is the opinionated first choice and carries the fullest spec by a
wide margin: its spec covers a whole station - plugins, hooks, settings and
permission rules - not just skills. `SPEC-CLAUDE-CODE.md` records one
opinionated setup rather than a neutral baseline: it names specific plugins,
hooks and permission rules, several of them third-party. The plugins and
their settings are optional - omit them and the rest still stands.

Two harnesses need a setup step before they find these skills. Claude Code
takes `sync-skills.sh`, which also gives it the subagents and commands.
Antigravity reads `.agents/` per project but not `~/.agents/` globally, and
takes a one-entry `skills.json` pointer file instead.

deepagents is the odd one out: a library rather than something you install on
a machine, so its spec covers wiring rather than a station. LangGraph sits
under it as the runtime and has no skills support of its own.

Claude Code, Codex CLI, goose, GitHub Copilot and opencode have been
confirmed by direct observation on a real machine. Cursor and Antigravity are
installed but only partly confirmed, and each says which parts. The rest are
documentation-derived and each says so.

## What Copilot found that nothing else did

Copilot CLI has the strictest `SKILL.md` parser of the harnesses tried, and on
2026-08-08 it rejected 8 of this repo's 24 skills. Four had a `description` over
the standard's 1024-character cap; four had frontmatter that would not parse
because a plain description scalar contained a bare `: `. Claude Code accepts all
24, which is how they stayed broken.

All 24 load everywhere now, and `skill-authoring` carries both checks. The
durable lesson is that the usual harness is the wrong one to validate against:
`copilot skill list` and `opencode debug skill` both run without
authentication and name the file and reason for every rejection, so portability
is cheap to test and worth testing before it is claimed.
[`SPEC-COPILOT.md`](copilot/SPEC-COPILOT.md) names the eight.

Every harness here except deepagents reads `~/.agents/skills/`. That is the whole
reason this repo lives at that path.

## Why most of these are short

Only one of the three trees in this repo is portable.

**`skills/` is a standard.** `~/.agents/skills/` is the cross-harness convention,
so a harness that reads it needs no install step and its spec has little to say
about skills.

**`agents/` is not, with one exception.** Every harness names its own subagent
directory. Cursor is the exception: it reads `~/.claude/agents/` as a
compatibility location, so `sync-skills.sh` delivers this repo's subagents there
too, at no extra cost. Gemini CLI's `~/.gemini/agents/*.md` uses the same
YAML-frontmatter-plus-prompt shape, so those are mechanically compatible even
though neither reads the other's path. Copilot's `*.agent.md`, opencode's
`agent/*.md` and Antigravity's `agents/<name>/agent.md` each differ enough that
nothing ports without conversion. Pi ships no subagents at all by design.

**`commands/` is not, and the formats differ.** Claude Code uses markdown at
`~/.claude/commands/*.md`; Gemini CLI uses **TOML** at `~/.gemini/commands/*.toml`.
These are different artifacts, not one artifact at two paths. Confirmed by
observation on 2026-07-31: commands in `~/.agents/commands/` appear in neither
Codex nor goose, while the skills beside them load.

The standard's own answer to both is to fold them into skills:
`disable-model-invocation: true` makes a skill behave as an explicit slash
command, and `context: fork` runs one in an isolated subagent. Each spec should
say which of those its harness honors, because that is the portable path.

A spec here is long-lived and describes current state. Session records and retired
per-feature specs live in `tasks/completed/`.
