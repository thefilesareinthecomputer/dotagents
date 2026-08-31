# SPEC-GOOSE.md - goose station

The open-source lane: fully OSS, desktop GUI, mature governance under the Agentic
AI Foundation. Used here for text operations and for running `teach-me` over
existing research artifacts.

## Skills: nothing to install

goose reads **`~/.agents/skills/`** directly, which is its own recommended global
location. Cloning this repo to `~/.agents` is the entire setup.

**Confirmed by observation 2026-07-31** on this machine. A doc-versus-behavior
report exists upstream claiming `~/.agents` does not resolve; it did not reproduce
here. If it ever does, the documented fallback is `.goose/skills/` in the project.

Also discovered by goose, for compatibility rather than by preference:
`.goose/skills/`, `.claude/skills/`, `~/.claude/skills/`, and its own
platform config directory.

## What does not carry over

Only `skills/` is portable. **Confirmed by observation 2026-07-31: commands in
`~/.agents/commands/` do not appear in goose**, while the skills beside them load.
Subagents are untested.

goose has its own recipes and subagent model; this repo's `agents/` and
`commands/` trees target Claude Code and are not read here. The portable path, if
one is wanted, is re-expressing them as skills carrying
`disable-model-invocation: true` or `context: fork` (backlog).

## Models

`glm-5.2` via Ollama cloud is the configured model.

**Routing is through the Ollama app only.** Never its public HTTP API, never a
non-loopback bind, `OLLAMA_HOST` never `0.0.0.0` or routable
(`SPEC.md` invariant 5).

Because Ollama `:cloud` models are hosted rather than local, anything run here
falls under the hosted-model limit in `SPEC.md` invariant 6: **medium-stakes and
hobby work only.** Work that matters runs on Anthropic or a genuinely local model.
Check each model's local-versus-cloud status before assuming it satisfies "local";
the `:cloud` suffix is the tell, and the parameter count is a hint.

## Station config

Not yet adapted. Hooks, settings and the statusline equivalents are Claude Code
shapes today; whether goose has counterparts and what they look like is a backlog
item in `tasks/plan.md`.
