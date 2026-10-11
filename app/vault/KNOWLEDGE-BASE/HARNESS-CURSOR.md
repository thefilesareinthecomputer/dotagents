---
date-created: 2026-08-27
last-modified: 2026-08-27
status: canonical
tags:
  - agents-app
  - harness
  - cursor
  - setup
---

# Cursor CLI

Cursor's terminal agent (`cursor-agent`) - the same agent as the Cursor editor, drivable from a shell.

## Setup

```bash
curl https://cursor.com/install -fsS | bash
cursor-agent login
```

Docs: https://cursor.com/docs - rules and config live in `~/.cursor/`, and it reads the repo's `AGENTS.md`.

## Pairing with the agents app

Cursor seats in group chat: `agents seat add <name> <repo> cursor` puts a Cursor agent session at that repo on the roster, and an @-mention invites it into a thread, where it runs `cursor-agent -p` and answers in attributed turns. The main two-party lane stays Claude Code. What also works:

- **Drive the app from Cursor directly** - editor or CLI. `AGENTS.md` covers the `agents` commands, the HTTP surface, and the vault rules; `cursor-agent -p "<prompt>"` is its print mode.
- **Your `~/.cursor/` rules apply** whenever Cursor is the agent doing the driving.

Back to [[HARNESS-INTEGRATION-OVERVIEW]].
