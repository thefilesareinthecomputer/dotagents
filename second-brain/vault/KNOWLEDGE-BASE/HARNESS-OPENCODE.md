---
date-created: 2026-08-27
last-modified: 2026-08-27
status: canonical
tags:
  - second-brain
  - harness
  - opencode
  - setup
---

# OpenCode

The provider-agnostic open-source terminal agent (MIT) - bring any model provider, keep one harness. A natural fit for this app's no-lock-in stance.

## Setup

```bash
curl -fsSL https://opencode.ai/install | bash    # or: npm i -g opencode-ai
opencode auth login                              # pick and authenticate a provider
```

Docs: https://opencode.ai - config lives in `~/.config/opencode/`, and it reads the repo's `AGENTS.md` natively.

## Pairing with second-brain

Set `harness = opencode` in `brain config` (or `SECOND_BRAIN_HARNESS=opencode`). The in-app chat adapter is planned; until it lands, picking `opencode` in the agent picker fails with a pointer to the repo's `AGENTS.md`. What works now:

- **Drive the app from OpenCode directly.** Open this repo; `AGENTS.md` covers the `b` CLI, the HTTP endpoints, and the vault rules. `opencode run "<prompt>"` is its headless mode.
- **Whatever provider you wired into OpenCode comes along** - the app never needs to know which model answers.

Back to [[HARNESS-INTEGRATION-OVERVIEW]].
