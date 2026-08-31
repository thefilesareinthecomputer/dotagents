---
description: Run the pre-launch checklist, then synthesize a go/no-go decision. Defers to agent-skills shipping-and-launch when that plugin is installed.
---

Run the pre-launch pass over what is about to ship, then return one decision.

Ask each question from its own specialist view rather than as a single sweep:

| View | The question |
|---|---|
| Correctness | What is untested, and what did the tests not cover? |
| Security | What is exposed that was not before, and what fails open? |
| Operability | When this breaks at 3am, what tells anyone, and how does it roll back? |
| Data | What migration is irreversible, and what happens to in-flight records? |
| Documentation | What does a user or on-call engineer need that is not written down? |

Exit with **go** or **no-go** and the blocking items named individually. A go
that lists no risks is not a go, it is an absence of review. State plainly
anything you could not check and anything you skipped, rather than letting
silence read as a pass.

If the `agent-skills:shipping-and-launch` skill is installed, invoke it and
follow its fuller procedure, including its parallel specialist personas. This
command stands on its own without it.

$ARGUMENTS
