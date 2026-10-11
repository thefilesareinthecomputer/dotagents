---
date-created: 2026-08-27
last-modified: 2026-08-27
status: canonical
tags:
  - second-brain
  - harness
  - copilot
  - setup
---

# GitHub Copilot CLI

GitHub's terminal agent - Copilot's agent loop in a shell, authenticated with your GitHub account.

## Setup

```bash
npm install -g @github/copilot
copilot            # first run signs in with GitHub (or reuses gh auth)
```

Docs: https://docs.github.com/copilot - config lives in `~/.copilot/`, and it reads the repo's `AGENTS.md`.

## Pairing with second-brain

Copilot seats in group chat: `brain seat add <name> <repo> copilot` puts a Copilot session at that repo on the roster, and an @-mention invites it into a thread, where it runs `copilot -p` and answers in attributed turns. The main two-party lane stays Claude Code. What also works:

- **Drive the app from Copilot directly.** Open this repo; `AGENTS.md` covers the `b` commands, HTTP endpoints, and vault rules. `copilot -p "<prompt>"` runs a one-shot prompt.
- Copilot's structured output is thinner than Claude Code's or Codex's, so its seat streams final text with fewer per-tool events.

Back to [[HARNESS-INTEGRATION-OVERVIEW]].
