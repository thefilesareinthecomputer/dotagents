---
description: Implement incrementally - build, test, verify, commit one thin slice at a time. Defers to agent-skills incremental-implementation when that plugin is installed.
---

Deliver the change in thin vertical slices. Never stack multiple features or
refactors before testing any of them.

Per slice:

1. Implement the smallest piece that is complete on its own.
2. Run its tests, plus the regression suite.
3. Verify against the task's acceptance criteria.
4. Commit, then start the next slice.

Touch only what the task requires. Remove imports, variables and functions that
your own change orphaned, and leave pre-existing dead code alone beyond
mentioning it. Match the surrounding style even where you would do it
differently.

Add "auto" to run an approved plan straight through instead of pausing between
slices.

If the `agent-skills:incremental-implementation` skill is installed, invoke it
and follow its fuller procedure. This command stands on its own without it.

$ARGUMENTS
