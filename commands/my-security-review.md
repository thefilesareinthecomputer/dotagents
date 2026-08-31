---
description: Run a personal agent-tooling security review - secrets, shell/hook command execution, untrusted input, plugin/MCP trust, destructive file ops, settings.json
---

Invoke the `my-security-review-checklist` skill.

Review the current changes (staged, or recent commits if nothing is staged), plus
any files named in the request, for the security concerns specific to agent
tooling:

1. **Secrets & dotfiles** - scan the staged diff for secrets; check `.gitignore` coverage
2. **Shell & script safety** - `set -euo pipefail`, quoted expansions, no `eval`/`curl|bash`, guarded `rm`/`mv`
3. **Hooks & command execution** - every hook command understood; no untrusted interpolation into shells
4. **Untrusted input** - agent/LLM/web/MCP/file content never executed or obeyed blindly; paths confined
5. **Plugin & MCP trust** - official source, pinned versions, look-alike names rejected
6. **File, path & symlink safety** - non-destructive rule honored; destructive ops reversible and empty-var guarded
7. **Permissions & settings.json** - least privilege; no wildcard auto-approve
8. **Portability & personal-constant hygiene** - no username-bearing absolute paths,
   device/vault overfitting, or hardcoded personal facts (names, emails, handles,
   personal repo URLs, vault/project names) in shared files; prefer `~/` (docs) or
   `"$HOME"` (shell), root discovery, and runtime derivation (env, git config/remote,
   session context) or asking the user live.
   Scan: `grep -rnE '/Users/[^/]+/|/home/[^/]+/'` over changed skills/scripts/docs
   (exclude `.claude/`, `__archive/`); rewrite hits and re-scan to confirm clean.

Categorize findings as **Critical**, **Important**, or **Suggestion**, each with a
`file:line` reference and a concrete fix. End with a **Safe to merge / Blocked** verdict.

For a thorough fresh-context pass (recommended before merging anything that runs
commands or touches files), dispatch the **my-security-reviewer** subagent instead
of reviewing inline.
