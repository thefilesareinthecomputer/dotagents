---
description: Start spec-driven development - write a structured specification before writing code. Defers to agent-skills spec-driven-development when that plugin is installed.
---

Write the spec before any implementation. It states what is being built and why,
what it is deliberately not, the invariants and boundaries it holds to, and the
decisions that will constrain later work. Acceptance criteria are part of it, not
an appendix.

Interrogate the request before specifying it. An ambiguity settled now is cheap;
the same ambiguity discovered in code is a rewrite. Where two readings would lead
to materially different work, ask rather than pick.

Per this repo's docs lifecycle, a scoped spec for one feature lands at
`tasks/SPEC-FEATURE-NAME.md` while that feature is in flight. On completion its
durable essence folds into the root `SPEC.md` (rewrite, do not append) and the
husk moves to `tasks/completed/SPEC-FEATURE-NAME-YYYY-MM-DD.md` as a real file
move.

If the `agent-skills:spec-driven-development` skill is installed, invoke it and
follow its fuller procedure. This command stands on its own without it.

$ARGUMENTS
