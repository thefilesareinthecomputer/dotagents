# SPEC-KIMI.md - Kimi Code CLI station

Moonshot AI's terminal coding agent. MIT, TypeScript, Node 22.19+, with built-in
coder, explore and plan subagents and MCP configured conversationally through
`/mcp-config`. Formerly the Python `kimi-cli`, which is wound down.

## Skills: nothing to install

Kimi Code reads **`~/.agents/skills/`** as its shared-across-tools location.
Cloning this repo to `~/.agents` is the entire setup.

It also keeps a Kimi-specific user directory at `$KIMI_CODE_HOME/skills/`, or
`~/.kimi-code/skills/` when that variable is unset. That one moves with
`KIMI_CODE_HOME`, so an isolated data root gets isolated Kimi-only skills, while
`~/.agents/skills/` deliberately stays under the real home so it can be shared.

Discovery scopes, most specific winning: project, user, extra, built-in.
Skills are invoked as `/skill:<name>` and a new session is needed after adding one.

**Not verified here.** Kimi Code is not installed on this machine (`~/.kimi-code`
absent); the above is from Moonshot's documentation as of 2026-07-31.

## What does not carry over

Only `skills/`. This repo's `agents/` and `commands/` target Claude Code, and Kimi
Code has its own subagent set.

One useful exception worth recording: **Kimi Code skills support the same
`$ARGUMENTS` placeholder this repo's commands already use**, including positional
`$ARGUMENTS[0]` / `$0` forms, and it appends `ARGUMENTS: <text>` when a body
declares no placeholder. So if the commands are ever re-expressed as skills
carrying `disable-model-invocation: true`, their argument convention ports here
unchanged. That is the closest thing to a portable command story found so far.

Directory-form skills must declare both `name` and `description`; omitting either
fails to parse.

## Models

Kimi Code runs Moonshot's Kimi models, reached through Kimi Code OAuth or a
Moonshot API key. These are hosted third-party, so `SPEC.md` invariant 6 bounds
this station to **low-stakes work only**. Work that matters runs on Anthropic or a
genuinely local model, which means it does not run here.

Kimi models are also reachable through Ollama on this machine
(`kimi-k2.6:cloud`), but that is a **different access path with a different
harness** and does not change the classification: a `:cloud` model is hosted, not
local.

## Station config

Not adapted. Whether Kimi Code has hook, permission or statusline analogues is
open, and tracked with the goose and Codex station work in `tasks/plan.md`.

## Architecture

The MoonshotAI/kimi-cli GitHub repo was archived on 2026-09-22 (GitHub API, checked 2026-11-25).
Facts below come from its Python source on `main` (commit `9ab1286b`, `src/kimi_cli/soul/kimisoul.py`), fetched from the branch tip, so the pin is approximate.
The product above is the TypeScript Kimi Code, so whether these hold there is **unknown**. Nothing here was run.

1. **Loop:** **source** `KimiSoul.run()` calls `_turn()`, then `_agent_loop()`, then `_step()`. `MaxStepsReached` fires past `loop_control.max_steps_per_turn`.
   A turn ends on no tool calls, a pure tool rejection (root agent only), or `tool_call_repeat` (`KimiToolset.force_stop_turn`), which is the loop detector.
   A Stop hook can re-trigger the turn once.
2. **Tools:** **source** All results of a step are awaited before the next LLM call; MCP loading is deferred and the list is dynamic. Parallel or sequential execution: **unknown**.
3. **Permissions:** **source** A per-turn approval source with `is_yolo`, `is_auto_approve` and `is_afk` flags; plan-file writes are auto-approved in plan mode. Decision logic and sandbox: **unknown**.
4. **Context:** **source** Before each step, `should_auto_compact()` compares tokens to `max_context_size` using `compaction_trigger_ratio` and `reserved_context_size`.
   Compaction clears the context, rewrites the system prompt and appends the compacted messages; the root agent re-adds a snapshot of active background tasks.
   Summary prompt and tool-output limits: **unknown**.
5. **Cache:** **unknown** (not in the file read). History is normalized and dynamic injections are collected on each step.
6. **Sessions:** **source** A checkpoint is made before every LLM call; the `SendDMail` tool reverts the context to a checkpoint and adds a message. Storage format and resume: **unknown**.
7. **Errors:** **source** Exponential backoff with jitter, 0.3 s initial, 5 s max, up to `max_retries_per_step`; retryable are connection errors, timeouts, empty replies and HTTP 429, 500, 502, 503, 504.
   One OAuth refresh on 401; compaction uses the same policy. Overflow handling: **unknown**.
8. **Rules files:** **unknown** (not in the file read).
9. **Front ends:** **source** Events `StepRetry`, `StepInterrupted`, `CompactionBegin` and `CompactionEnd` were seen. Headless mode and ACP: **unknown**.
10. **Subagents:** **source** Same `KimiSoul` class, told apart by `runtime.role`; root-only behavior includes notifications (4 per step) and the stop on pure rejection.
    Isolation, depth and concurrency limits: **unknown**.
