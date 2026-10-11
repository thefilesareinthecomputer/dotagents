---
date-created: 2026-08-27
last-modified: 2026-08-27
status: canonical
tags:
  - agents-app
  - harness
  - codex
  - setup
---

# Codex CLI

OpenAI's terminal coding agent (Rust, sandboxed). First in line for a native chat adapter in the app - its headless `codex exec --json` output is the closest match to the app's streaming contract.

## Setup

```bash
npm install -g @openai/codex     # or: brew install codex
codex login                      # signs in with your ChatGPT account
```

Docs: https://github.com/openai/codex - config lives in `~/.codex/` (`config.toml`), and it reads the repo's `AGENTS.md` natively.

## Pairing with the agents app

Codex seats in group chat: `agents seat add <name> <repo> codex` puts a Codex session at that repo on the roster, and an @-mention invites it into a thread, where it runs `codex exec --json` in its workspace-write sandbox and answers in attributed turns. The main two-party lane stays Claude Code. What also works:

- **Drive the app from Codex directly.** Open this repo in Codex; `AGENTS.md` tells it how to run `agents up`, rebuild the graph, search the vault over HTTP, and which rules bind it.
- **Your `~/.codex/` config applies** whenever Codex is the agent doing the driving - same companion principle as every harness here.

## Notes

- Headless mode is `codex exec "<prompt>"`; `--json` emits the JSONL event stream the seat driver maps onto the app's SSE vocabulary.
- Sandboxing is a Codex strength: it constrains its own shell, which pairs fine with this app's local-only HTTP surface.

Back to [[HARNESS-INTEGRATION-OVERVIEW]].
