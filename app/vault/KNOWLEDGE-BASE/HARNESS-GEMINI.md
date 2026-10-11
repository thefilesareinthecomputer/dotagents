---
date-created: 2026-08-27
last-modified: 2026-08-27
status: canonical
tags:
  - agents-app
  - harness
  - gemini
  - setup
---

# Gemini CLI

Google's open-source terminal agent. Note before investing: Google has been folding consumer access into its Antigravity product, so check the project's current status before adopting it fresh.

## Setup

```bash
npm install -g @google/gemini-cli
gemini             # first run signs in with your Google account
```

Docs: https://github.com/google-gemini/gemini-cli - config lives in `~/.gemini/`, with `GEMINI.md` as its per-repo context file (this repo's `AGENTS.md` carries the same content harness-neutrally).

## Pairing with the agents app

Set `harness = gemini` in `agents config` (or `AGENTS_APP_HARNESS=gemini`). The in-app chat adapter is planned; until it lands, picking `gemini` in the agent picker fails with a pointer to the repo's `AGENTS.md`. What works now:

- **Drive the app from Gemini directly.** Open this repo; `AGENTS.md` covers the `agents` commands, the HTTP surface, and the vault rules.

Back to [[HARNESS-INTEGRATION-OVERVIEW]].
