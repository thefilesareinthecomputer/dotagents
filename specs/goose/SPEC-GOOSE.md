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
  the tryout bench (`/task tryout`) with `glm-5.3-flash:cloud` at thinking `low`, goose passed
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
| Model egress | `active_provider: ollama` with a `:cloud` model tag in `config.yaml` | every prompt and response goes through the local Ollama app to Ollama's hosted service. Ollama's cloud page states prompt and response data is never logged or trained on and is hosted primarily in the United States (provider's claim, read 2026-11-01). The user accepts this egress (2026-11-01); a local tag keeps prompts on the machine |
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

## Architecture

Read from source at `aaif-goose/goose` commit `8256b9ac` on 2026-11-25 (the repo moved from `block/goose`). Paths are relative to `crates/`, with `oi-kit-*` crates alongside `goose`.

1. **Loop:** **source** - a turn ends on an assistant message with no tool request, error or required action (`oi-kit-agent/src/operation.rs:78-89`).
   - `GOOSE_MAX_TURNS` defaults to 1000 (`goose/src/config/base.rs:1373-1375`). Past half the budget a `<turn-budget>` hint is added (`max_turns.rs:22-76`).
   - A stop hook can block the end up to 8 times. There is no wall-clock limit.
   - `RepetitionInspector` is registered with `None`, so loop detection is effectively off (`tool_monitor.rs:34-87`; `services.rs:746`).
2. **Tools:** **source** - all of a turn's calls run concurrently with no worker cap, and finished results survive a cancel (`mcp/batch.rs:39-74`). The list is dynamic per request and duplicate names are rejected.
3. **Permissions:** **source** - modes are Auto (default), Approve and SmartApprove (`permission/permission_inspector.rs:160-199`).
   - The inspector chain is Security, Egress, Adversary, Permission, Repetition (`services.rs:728-746`).
   - There is no OS sandbox.
   - **docs** - `PreToolUse` and `Stop` hooks can block (see Strengths).
4. **Context:** **source**
   - Tool output over 200,000 characters goes to a temp file with a pointer (`large_response_handler.rs:5-47`). The shell tool caps at 2,000 lines or 50,000 bytes.
   - Tool-pair summarization is off by default (`context_mgmt/mod.rs:59-63,307-353`).
   - Compaction triggers at the lower of `GOOSE_AUTO_COMPACT_THRESHOLD` (0.8) and 225,000 tokens over the window (`context_mgmt/mod.rs:29-57`). It also runs on `/compact` and on a context-length error, at most twice.
   - The summary is structured JSON from `prompts/compaction.md`, requested on the live prefix by default.
   - Old messages are hidden, not deleted. Appended: the summary, a continuation text, the latest user prompt and the latest turn-context message (`compaction/layout.rs:5-100`).
   - A failed summary retries with 0, 10, 20, 50 then 100% of tool responses removed.
5. **Cache:** **source** - cache behavior is declared per provider and model: ExplicitBreakpoints{4}, ImplicitTolerant, ImplicitStrict (default), Uncached (`cache_semantics.rs:8-30`).
   - Anthropic markers go on the system prompt, the last tool and messages.
   - `tests/prefix_invariance.rs` asserts that bytes already sent never change. Volatile context (time, cwd, turn budget) is an agent-only message (`agents/moim.rs:7,85-86`).
6. **Sessions:** **source** - SQLite (schema v18, WAL) with sessions, messages and a usage ledger. Sessions can be copied and truncated. Compaction replaces the conversation inside the same session.
7. **Errors:** **source** - 3 retries from 1 s, doubling, capped at 30 s, with 0.8-1.2 jitter (`oi-kit-provider-types/src/retry.rs:14-117`). The Ollama provider uses 2 s, x1.5, capped at 15 s. Overflow is handled by compaction (item 4).
8. **Rules files:** **source** - `.goosehints` and `AGENTS.md`, overridable with `CONTEXT_FILE_NAMES`.
   - Global files load first, then from the git root down to the cwd. Subdirectory hints load when a tool first touches the directory.
   - Imports are capped at depth 3, 64 references and 1 MiB (`hints/load_hints.rs`; `import_files.rs:14-17`).
9. **Front ends:** **source** - an ACP server over stdio, plus HTTP `/acp` with WebSocket. Internal events: Message, Usage, McpNotification, HistoryReplaced.
   - **docs** - `goose run --recipe` runs headless (see Strengths).
10. **Subagents:** **source** - at most 5 run concurrently, delegated through the summon extension, which takes its own max turns. Isolation: **unknown**.
