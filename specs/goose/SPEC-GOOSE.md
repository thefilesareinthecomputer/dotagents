# SPEC-GOOSE.md - goose station

The open-source lane: fully OSS, desktop GUI, mature governance under the Agentic
AI Foundation. Used here for text operations and for running `teach-me` over
existing research artifacts.

**Verified on the laptop 2026-10-14:** `goose 1.54.0`, installed by Homebrew
(`block-goose-cli`), probed with `harness_probe.py` in the `agent-cc-configs-sync`
skill; `goose skills list` names this repo's skills with no sign-in, and that
command is the probe's discovery canary for this harness.

## Strengths

What this harness is for on this station. Each claim is marked **observed**
(seen in a run or a bench here), **doc-derived** (from goose's documentation,
`_RESEARCH/goose-docs-2026-10-11/findings.md`) or **impression** (the user's
working sense, not yet measured).

- **The open-source lane that completes the bench - observed.** On
  `harness-bench` with `glm-5.3-flash:cloud` at thinking `low`, goose passed
  33 of 33 task runs (eleven tasks, three reps) on 2026-10-13; the result table is
  in `tasks/SPEC-HARNESS-BENCH.md`.
- **Keeps large tool output in check - observed.** goose truncates large tool
  output where pi does not: 26K against 98K input tokens on the bench's
  `long-audit` task, which made goose the cheaper harness on the long multi-file
  tasks.
- **Recipes as the repeatable unit - doc-derived.** A YAML recipe holds the
  instructions or prompt, the model and temperature settings, `max_turns`, the
  extensions it may load (and when it declares them, only those load) and
  `sub_recipes`, which is goose's lead-and-worker pattern. `goose run --recipe
  <file>.yaml --params key=value` runs one headless, so a recurring job is a
  file in the repo rather than a prompt someone remembers.
- **Extensions are MCP - doc-derived.** goose takes stdio, builtin, platform
  and streamable-http extensions with an optional `available_tools` allowlist,
  so the tool surface of a run is declared rather than inherited.
- **Relocatable state - observed.** `GOOSE_PATH_ROOT` moves config, data and
  state under one root, which is how the bench gives each run a fake home.
- **Hooks in Claude Code's event shape - doc-derived.** `PreToolUse` and `Stop`
  can block; hook plugins load from `<scope>/.agents/plugins/<name>/hooks/`.
  FEATURE-000053 captures them before anything depends on them.

Limits that bound the lane: the configured model is an Ollama `:cloud` tag, so
hosted and medium-stakes only (`SPEC.md` invariant 6); global hints loaded from
a source the research pass could not find (findings, section 2).

## Config locations

| Scope | Path | Holds |
|---|---|---|
| Global | `~/.config/goose/config.yaml` | provider, model, extensions and settings |
| Global | `~/.config/goose/.goosehints`, `~/.config/goose/AGENTS.md` | the documented global context files (neither exists on the laptop) |
| Global | `~/.config/goose/memory/` | the memory extension's store |
| Remote control (invariant 7) | `GOOSE_TELEMETRY_ENABLED: false` in `config.yaml`; `goose serve` and `goose acp` never run | telemetry off on the laptop 2026-10-15; `goose --help` at 1.54.0 lists `serve` (ACP over HTTP and WebSocket) and `acp` (ACP on stdio) as its only network-serving subcommands, and both start only by hand |
| Relocation | `GOOSE_PATH_ROOT` | moves `config/`, `data/sessions/` and `state/logs/` under one root |
| Project | `.goosehints`, `AGENTS.md`, from the working directory up to the repo root | context files, local wins |
| Project | `.goose/skills/`, `.agents/plugins/<name>/hooks/` | project skills and hook plugins |
| Recipes | any path passed to `goose run --recipe` | the repeatable job definition |

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

## Seeding

What this harness inherits natively from `~/.agents` and what has to be
installed. Shapes are defined once in
[`../SEEDING-SHAPES.md`](../SEEDING-SHAPES.md), and `seed.json` beside this file
is the machine-readable copy that `seed.py` reads.

| Element | Shape | Station path | Notes |
|---|---|---|---|
| Skills | `NATIVE` | reads `~/.agents/skills/` | verified by `goose skills list`, which needs no sign-in |
| Subagents | `N/A` | - | untested; no subagent tree documented |
| Commands | `N/A` | - | commands in `~/.agents/commands/` do not appear in goose (observed 2026-07-31) |
| Remote control | `FRAGMENT` | `~/.config/goose/config.yaml` | one top-level key, `GOOSE_TELEMETRY_ENABLED: false` (invariant 7); the last occurrence of a key wins in this file, so the seed folds duplicates into one line |

## Station config

Not yet adapted. Hooks, settings and the statusline equivalents are Claude Code
shapes today; whether goose has counterparts and what they look like is a backlog
item in `tasks/plan.md`.
