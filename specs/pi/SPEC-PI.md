# SPEC-PI.md - Pi station

The configurable lane: a minimal, hackable terminal harness built to be adapted
rather than accepted. MIT, TypeScript, extensions in-process. Ships no subagents
and no plan mode by design.

**Verified on the laptop 2026-10-14:** `pi 1.1.0`, installed by Homebrew,
probed with `harness_probe.py` in the `agent-cc-configs-sync` skill. Pi has no
no-login skill listing, and the bench runs it under a fake home, so discovery of
this repo's skills has not been observed here yet; a print-mode probe in a real
home is the pending check. Its config home is `~/.pi/agent/`.

## Strengths

What this harness is for on this station. Each claim is marked **observed**
(seen in a run or a bench here), **doc-derived** (from pi.dev's documentation)
or **impression** (the user's working sense, not yet measured).

- **The leanest harness on the bench - observed.** On `harness-bench` with
  `glm-5.3-flash:cloud` at thinking `low`, pi passed 33 of 33 task runs on
  2026-10-13 and spent 25 to 60 percent fewer input tokens than goose on ten of
  eleven tasks; its system prompt is about 1,000 tokens smaller. The
  `long-audit` task is the one exception.
- **No tool-output cap - observed, double-edged.** pi sent a 258 KB file to the
  model whole on `long-audit` (172K input tokens, six times goose's), so it is
  the more expensive harness on long multi-file work and the cheaper one
  everywhere else.
- **Minimal and extensible by design - doc-derived.** Pi is a four-tool core
  (read, write, edit, bash) extended in-process by TypeScript extensions, with a
  `--tools` allowlist and `--exclude-tools` denylist per run, BYOK across 20+
  providers and tree-based sessions. It is the harness to adapt when a job needs
  a tool surface no other harness has.
- **Skills as the portable surface - doc-derived.** Pi has two global skill
  roots with different root-file rules (see "The discovery rule that matters"),
  takes `/skill:name` invocation, and honors `disable-model-invocation`, which
  is the standard's route for commands.
- **A provider quirk the bench works around - observed.** pi sends its system prompt as a
  `developer`-role message, which Ollama's `/v1` drops; the bench adapter sets
  `compat.supportsDeveloperRole: false` so the prompt reaches the model.

Limits that bound the lane: **no built-in permission system**, so pi runs only
under an outside sandbox (the bench's `sandbox-exec` profile); whichever provider
is configured, `SPEC.md` invariant 6 binds.

## Config locations

| Scope | Path | Holds |
|---|---|---|
| Global | `~/.pi/agent/config.json` | settings, the `skills` array, `enableSkillCommands`, extensions |
| Global | `~/.pi/agent/auth.json`, `~/.pi/agent/models-store.json` | provider credentials and the model store; never copied |
| Global | `~/.pi/agent/skills/` | Pi's own skill root, where a loose root-level `.md` is a skill |
| Global | `~/.pi/agent/installed-plugins/`, `~/.pi/agent/servers/` | extensions and MCP servers |
| Global | `~/.pi/agent/session-store.db`, `~/.pi/agent/logs/` | sessions and logs |
| Project, after trust | `.pi/skills/`, `.agents/skills/` | project skills, in cwd and ancestors |
| Per run | `--skill <path>`, `--tools`, `--exclude-tools`, `--no-skills` | the run's skill and tool surface |

## Skills: nothing to install

Pi reads **`~/.agents/skills/`** as one of two global locations. Cloning this repo
to `~/.agents` is the entire setup.

| Location | Path |
|---|---|
| Global | `~/.pi/agent/skills/` and **`~/.agents/skills/`** |
| Project, after trust | `.pi/skills/` and `.agents/skills/`, in cwd and ancestors |
| Packages | `skills/` dirs, or a `pi.skills` entry in `package.json` |
| Settings | a `skills` array of files or directories |
| CLI | `--skill <path>`, repeatable, and additive even under `--no-skills` |

The table is from pi.dev's documentation as of 2026-07-31 and is doc-derived
throughout: pi is installed on the laptop, but discovery of this repo's skills has
not been observed, because the bench runs pi under a fake home.

## The discovery rule that matters

Pi treats its two global locations differently, and the difference is easy to miss:

- In `~/.pi/agent/skills/` a loose root-level `.md` file becomes a skill.
- In **`~/.agents/skills/` root-level `.md` files are ignored.** Only directories
  containing a `SKILL.md` are discovered, recursively.

That suits this repo exactly, since every skill here is `skills/<name>/SKILL.md`.
It also means a stray markdown file dropped at the top of `skills/` would be
silently invisible to Pi while other harnesses might pick it up.

**A skill with no `description` is not loaded at all.** Name collisions across
locations warn and keep the first found.

## Where Pi diverges from the standard

**Pi does not require `name` to match the parent directory**, deliberately, on the
grounds that the requirement is awkward for shared skill directories. This repo
keeps them matched anyway, per `skill-authoring` and the open standard, so the
divergence costs nothing here. It does mean a skill authored *for* Pi may not be
valid elsewhere.

Frontmatter: `name` (1-64 chars, lowercase alphanumeric and hyphens) and
`description` (1024 max) required; `license`, `compatibility`, `metadata`,
`allowed-tools` and `disable-model-invocation` optional.

## Invocation, and a corroborated finding

Skills are invoked as `/skill:name` or `/skill:name <arguments>`, which requires
`enableSkillCommands: true` in settings.

Pi's own documentation notes that models do not reliably auto-load a matching
skill, and recommends prompting or explicit `/skill:name` to force it. **That
independently corroborates this repo's 2026-07-31 trigger-eval finding**, where
`data-engineering` scored 1/15 recall and a `docker` control showed the same
signature: near-zero auto-invocation with perfect precision. It is a property of
models reaching for skills, not of any one skill's description.

## What does not carry over

Only `skills/`. Pi ships no subagents, so `agents/` has nothing to map onto.
Commands are not read from `~/.agents/commands/`; Pi's equivalent is a skill
carrying `disable-model-invocation`, which it supports.

Pi can also be pointed at other harnesses' skill directories through its settings
`skills` array, for example `{"skills": ["~/.claude/skills", "~/.codex/skills"]}`.

## Models

Whatever provider is configured; 15+ are supported. `SPEC.md` invariant 6 binds:
work that matters runs on Anthropic or a genuinely local model.

## Station config

Not adapted. Pi's extension model is TypeScript in-process rather than shell
hooks, so the hook scripts have no direct analogue and would need rethinking
rather than porting. Tracked in `tasks/plan.md`.
