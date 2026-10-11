---
date-created: 2026-08-27
last-modified: 2026-08-27
status: canonical
tags:
  - second-brain
  - harness
  - setup
---

# Agent Harness Integration Overview

This app is a companion to whatever agent setup you already run. The chat lane shells out to your own harness CLI, so your personal skills, agents, and config ride along natively - nothing gets re-implemented here. Pick your harness during `brain config` (the `harness` key), or set `SECOND_BRAIN_HARNESS` per invocation.

## The harnesses

| Harness | Config home | Note | In-app chat driver |
|---|---|---|---|
| Claude Code | `~/.claude/` | [[HARNESS-CLAUDE-CODE]] | built - the main two-party lane and a group-chat seat |
| Codex CLI | `~/.codex/` | [[HARNESS-CODEX]] | built - group-chat seat driver |
| OpenCode | `~/.config/opencode/` | [[HARNESS-OPENCODE]] | planned |
| Cursor CLI | `~/.cursor/` | [[HARNESS-CURSOR]] | built - group-chat seat driver |
| Copilot CLI | `~/.copilot/` | [[HARNESS-COPILOT]] | built - group-chat seat driver |
| Gemini CLI | `~/.gemini/` | [[HARNESS-GEMINI]] | planned |

Any harness in the table - and anything not in it that can run bash - can drive the app's full CLI and HTTP surface today. `AGENTS.md` at the repo root is the harness-neutral operating guide: run commands, endpoint table, and the rules that bind every agent.

## What "supported" means

Two levels, and both count:

1. **Drive the app from outside.** Point your harness at this repo; it reads `AGENTS.md`, runs `b up` / `b build`, calls the HTTP API, and edits vault notes like any other files. This works everywhere, now.
2. **Be the app's chat engine.** The web UI's agent picker routes a conversation to a harness driver. Claude Code is the built driver; the rest fail loudly with a pointer here until their adapters land.

Editing the vault by hand happens in [[EDITOR-OBSIDIAN|Obsidian]] or any editor - the graph re-indexes on drift, so nothing you do outside the app gets missed. The knowledge rules themselves live in [[SECOND-BRAIN-KNOWLEDGE-LIFECYCLE]].
