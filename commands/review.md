---
description: Conduct a five-axis code review - correctness, readability, architecture, security, performance. Defers to agent-skills code-review-and-quality when that plugin is installed.
---

Review the change before it merges. Scope to the diff named in the request, or
to the staged diff when nothing is named.

Five axes, each asked separately:

| Axis | The question |
|---|---|
| Correctness | What input or state makes this produce the wrong result? |
| Readability | What will the next reader misunderstand? |
| Architecture | What does this foreclose, and what now depends on what? |
| Security | What here trusts input it should not, or fails open? |
| Performance | What grows faster than the data it handles? |

Report findings most severe first, each with a `file:line` and a concrete
failure scenario: the inputs, and the wrong output or crash they produce. A
finding you cannot state that way is a preference, so label it as one or drop
it. Distinguish defects from decisions you would have made differently.

If the `agent-skills:code-review-and-quality` skill is installed, invoke it and
follow its fuller procedure. This command stands on its own without it.

$ARGUMENTS
