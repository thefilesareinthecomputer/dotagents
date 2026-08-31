---
description: Break work into small verifiable tasks with acceptance criteria and dependency ordering. Defers to agent-skills planning-and-task-breakdown when that plugin is installed.
---

Plan the scope named in the request. State your assumptions before planning, and
surface any decision that needs the user rather than guessing at it.

Produce ordered tasks, each independently verifiable, in the form:

```
1. [Step] -> verify: [the check that proves it]
2. [Step] -> verify: [the check that proves it]
```

Every task carries acceptance criteria and a verification step. Weak criteria
("make it work") force constant clarification; strong ones let the work loop
without supervision. Mark which tasks depend on which, and which can run in
parallel. Plan the work asked for and nothing speculative.

If the `agent-skills:planning-and-task-breakdown` skill is installed, invoke it
and follow its fuller procedure. This command stands on its own without it.

$ARGUMENTS
