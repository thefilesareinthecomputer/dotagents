---
name: hi
description: Session-start orientation ritual. Reads this workspace's state - living docs (README/SPEC/tasks-plan/tasks-todo), memory (file-based MEMORY.md + recent claude-mem activity), changelog, and git status - then reports a concise current-state briefing ending in the single next action. Read-only, writes nothing. Portable across any repo (discovers the workspace root). Triggers on "/hi", "get up to speed", "orient", "where are we", "catch up", "repo status" - but NOT for the status of an in-flight command, background task, or test run in the current session (answer those directly from session context).
---

# /hi - session-start orientation

Get up to speed fast: read this workspace's state, then report a concise current-state
briefing. **Read-only - this skill never writes, edits, archives, or logs.**

## When to use

- Start of a session, before any work.
- Explicit `/hi`, or "get up to speed" / "where are we" / "catch up" / "orient".
- Any time the agent is lost and needs to re-anchor on workspace state.

## When NOT to use

- Mid-task - this is orientation, not a checkpoint. To *save* state use `/notes`
  (docs sweep) or `/reflect` (memory + truth reconciliation).
- It modifies nothing. If you catch yourself wanting to edit, you're past orientation.

## Procedure

First, **find the workspace root**: `git rev-parse --show-toplevel` (fall back to the
current working directory if this isn't a git repo). Resolve everything below relative to
that root. If a file or directory is absent, note it and move on - **never fabricate
state**.

Read these in one parallel batch (absolute paths, no `cd`). **Sources 1 and 2 are primary:
the task files say what the work IS, git says what actually HAPPENED to it.** Everything
after them corroborates and dates; when a later source disagrees with git, git wins.

1. **The hot task files - ALL of them, IN FULL.** `ls` the `tasks/` directory (or the repo's
   equivalent) and read **every file it lists** except the cold archives
   (`tasks/completed/`, `*-completed.md`, `*-COMPLETED.md`, `__archive/`) - `plan.md`, `todo.md`, every
   `SPEC-*.md` feature spec, and anything else in there. Do not pick a subset, do not skim
   for the top-of-file initiative, and do not assume a file named for an old initiative is
   dead: in-flight work is exactly what lives here, and the item that decides your next
   action is as often at the bottom as the top.

   **A truncated read is not a read.** These files run long, and the Read tool caps output
   and says so. If a result is partial, page through with `offset`/`limit` until you reach
   the end. If a file is genuinely too large to hold, say which parts you skipped in the
   briefing rather than presenting a partial read as complete.

2. **Git - state AND history.** Read-only git; the git-mutation gate does not apply.
   - `git -C <root> status` plus `git -C <root> branch --show-current`. **Uncommitted work is
     in-flight work** and the single sharpest signal of what did not finish. Name the files.
   - `git -C <root> log --oneline -20` for the arc of recent work, then
     `git -C <root> log --stat -5` (or `--name-only`) to see what those commits actually
     touched. A subject line states intent; the file list states what shipped.
   - Reconcile the two against source 1: work the task files call done but git never
     committed, and work git shows landed that the task files still call open, are both
     findings - report them.

3. **Living docs at the repo root** - whichever exist: `README.md`, `SPEC.md` (or legacy
   root `PLAN.md` / `HANDOFF.md`), plus `AGENTS.md` / `CLAUDE.md` for repo-specific rules.
   These describe the *active* state; crack open the cold files only if you need history.
4. **Memory - file-based.** If `MEMORY.md` was **not** already auto-injected into context
   this session, read this workspace's index at
   `~/.claude/projects/<slug>/memory/MEMORY.md` - where `<slug>` is the workspace's
   absolute path with every `/` and `.` replaced by `-` (e.g. `/Users/me/code/app`
   → `-Users-me-code-app`) - then any linked files that look relevant. If it was
   already injected (check the session context), don't re-read it.
5. **Memory - recent activity (claude-mem).** The SessionStart hook usually injects a
   recent timeline; if it's missing or you need more depth, pull it via the `mem-search`
   skill, `/mem-search <query>`, `npx claude-mem search "<query>"`, or the claude-mem MCP
   (`timeline`, `smart_search`, `get_observations`). This answers "what was I just doing,
   what did we decide/change last session" - the part docs don't capture yet.
6. **Changelog** - the newest entry: `ls` the `_CHANGELOG/` dir for the latest file, or
   read the head of `CHANGELOG.md`, whichever this repo uses.

## Output

A concise current-state briefing (terse, evidence over narration):

- **Branch + working-tree state** - clean / dirty, and what's uncommitted.
- **Active initiatives** - one line each: phase/status + the single next action.
- **Recent activity** - what the last session(s) actually did (from claude-mem + git log),
  especially anything that **didn't finish**.
- **Blocked / gated** - anything waiting on a user review gate or decision.
- **Flagged maintenance** - stale status lines, pending sweeps, pinned do-not-touch items.
- **End with a question** - which thread to pull next.

No filler. Surface what didn't finish last session before proposing new work.
