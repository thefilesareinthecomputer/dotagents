# Security Policy

Report privately through this repository's Security tab, using **Report a
vulnerability**, rather than opening a public issue. Include the affected file,
what triggers the problem, and what an attacker gains. Fixes land on `develop`
and are fast-forwarded to `main`; only the current state of those branches is
supported.

This repo ships instructions and scripts that an agent executes on a developer's
machine, so the findings worth reporting are not the usual application ones:

- A skill, hook, or script that runs a shell command built from untrusted input.
- A skill that reads web pages, model output, or MCP results and then acts on
  that content as if it were instruction.
- Text hidden from a human reviewer in any file an agent reads as instruction:
  zero-width characters, Unicode tag smuggling, bidi overrides. A bypass of
  `unicode_smuggle_check.py` counts.
- Deletion or overwriting outside the repo, or an escape from the sync script's
  guarantee that real local entries in `~/.claude` survive.
- A path by which credentials on disk reach an agent's context or a log.
- A change that quietly widens a subagent's `tools:` allowlist or a hook's reach.

Report the absence of sandboxing in Claude Code itself upstream, and third-party
plugins to their own maintainers.
