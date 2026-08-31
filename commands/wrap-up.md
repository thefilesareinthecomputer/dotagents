---
description: Full session closeout in one pass - reflect, then notes, then the git sync ritual, ending with the work pushed and the tree clean on the branch the repo's workflow says work belongs on.
---

Invoke the `wrap-up` skill.

Close out this session end to end. Three existing skills run in order; this
command owns the sequence, the handoffs and the guards between them, not their
procedures.

**Fetch first, before anything else.** Inbound commits from another machine
change what is true, and reconciling a session against stale state produces
memory entries and doc corrections that are wrong on arrival.

0. **Assess and decide whether to run.** `git status --porcelain`,
   `git fetch origin`, `git status -sb`. Stop and ask if the tree holds changes
   this session did not make - another agent may be working here, and sweeping
   their half-finished work into a commit is the worst outcome available. Stop
   if origin has diverged. Say plainly if there is nothing to wrap up. Then tell
   the user the chain has up to three approval gates, so it does not read as
   fire-and-forget.
1. **`reflect`** - session learnings to memory, stale claims corrected wherever
   they live. Runs before notes so the docs sweep writes against a record that is
   already accurate. Afterwards confirm the memory index is clean with
   `python3 ~/.claude/hooks/memory_lint.py`; advisory lines are fine, a `FAIL` is
   not. If the user rejects the whole slate, continue anyway.
2. **`notes`** - the docs sweep: measure the hot files, fold the session into the
   `tasks/` bundle, relocate finished work to `tasks/completed/`, compress what
   survives, then check the root docs for claims the session made false. That
   root-doc check is inside notes; do not run a second pass over it here.
3. **`repo-device-sync` from Phase 2 on** - reconcile inbound, verify the staged
   set before committing (`git commit` writes the whole index, not just what was
   added), one commit by default, re-fetch immediately before pushing.
4. **Land on the right branch.** Read the convention from
   `git symbolic-ref --short refs/remotes/origin/HEAD`, `git branch -vv`, and
   whatever `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md` or memory says. Single
   branch: push it. Paired stable branch: advance the stable one by refspec,
   never by checkout. Feature branch: push it and stop - merging and opening a
   pull request are separate decisions with review attached.

The natural-language remainder of the request refines focus, for example naming
the commit message or asking for the work split across more than one commit.

Never force-push, rebase pushed history, hard reset, or push to a public mirror.
Preserve every sub-skill's own gate rather than skipping it to keep the chain
moving. Finish by confirming the tree is clean, reporting each ref's final
position, and naming anything deliberately left undone.
