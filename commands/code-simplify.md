---
description: Simplify code for clarity and maintainability - reduce complexity without changing behavior. Defers to agent-skills code-simplification when that plugin is installed.
---

Reduce complexity without changing behavior. Get the tests green first, so that
"behavior preserved" is a measurement rather than a claim, and re-run them after
each simplification.

What earns removal: speculative abstraction, indirection with one caller, options
nobody passes, defensive branches for states that cannot occur, and duplication
that a name would explain better than a helper would.

What does not: code that is merely unfamiliar, formatting you would have chosen
differently, and anything outside the scope you were handed. Do not refactor what
is not broken, and do not improve adjacent code on the way past. If you notice
unrelated dead code, say so rather than deleting it.

Report what shrank and what you deliberately left alone.

If the `agent-skills:code-simplification` skill is installed, invoke it and
follow its fuller procedure. This command stands on its own without it.

$ARGUMENTS
