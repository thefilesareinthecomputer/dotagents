---
date-created: 2026-08-27
last-modified: 2026-08-27
status: canonical
tags:
  - second-brain
  - harness
  - claude-code
  - setup
---

# Claude Code

Anthropic's terminal agent, and this app's primary chat driver: the web UI drives a real Claude Code session over the repo, billed to your Claude subscription rather than metered API.

## Setup

```bash
npm install -g @anthropic-ai/claude-code   # or: curl -fsSL https://claude.ai/install.sh | bash
claude                                     # first run walks you through login
```

Docs: https://code.claude.com/docs - config lives in `~/.claude/` (`CLAUDE.md`, `skills/`, `agents/`, `settings.json`).

## Pairing with second-brain

Nothing to wire up. With `claude` on your PATH and logged in, the app detects it, `brain config` defaults `harness = claude`, and the agent picker shows `claude-code`. Each conversation in the web UI is one persistent Claude Code session, resumed every turn - context and in-flight work survive across messages, and "New Chat" starts fresh.

Because it is a genuine harness session over this repo:

- **Your whole config rides along.** Every skill, subagent, and rule in `~/.claude/` is available from the chat window, alongside this repo's packaged lifecycle skills.
- **Subagent customization works from chat.** Ask for specific models, effort levels, or tool restrictions on delegated work and the session honors it through its own Agent tooling.
- **The knowledge lifecycle is reachable from chat**, not just the terminal - see [[SECOND-BRAIN-KNOWLEDGE-LIFECYCLE]].

## Notes

- No SDK or pip package involved; the server shells out to `claude -p` with streaming JSON. The CLI is an optional runtime peer - the app runs without it on other lanes.
- Sessions run at the default permission mode: actions that need write approval will ask (or be declined) rather than run silently.

Back to [[HARNESS-INTEGRATION-OVERVIEW]].
