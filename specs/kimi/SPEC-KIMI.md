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
