# SPEC-PI.md - Pi station

The configurable lane: a minimal, hackable terminal harness built to be adapted
rather than accepted. MIT, TypeScript, extensions in-process. Ships no subagents
and no plan mode by design.

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

**Not verified here.** Pi is not installed on this machine; the above is from
pi.dev's documentation as of 2026-07-31.

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
