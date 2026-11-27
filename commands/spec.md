---
description: Start spec-driven development - write a structured specification before writing code. Defers to agent-skills spec-driven-development when that plugin is installed.
disable-model-invocation: true
---

Write the spec before any implementation. It states what is being built and why,
what it is deliberately not, the invariants and boundaries it holds to, and the
decisions that will constrain later work. Acceptance criteria are part of it, not
an appendix.

Interrogate the request before specifying it. An ambiguity settled now is cheap;
the same ambiguity discovered in code is a rewrite. Where two readings would lead
to materially different work, ask rather than pick. A requirement the user
stated that the spec cannot meet, or scopes out, is never cut silently: it goes
under the spec's decisions for the user, with the reason.

Per this repo's docs lifecycle, a scoped spec for one feature lands at
`tasks/SPEC-FEATURE-NAME.md` while that feature is in flight. On completion its
durable essence graduates into `docs/` (rewrite, do not append): what the system now
is becomes a section of `docs/SPEC.md` (the root `SPEC.md` in a repo that has not
moved it), and a choice between options becomes an ADR in `docs/adr/`. The husk moves
to `tasks/completed/SPEC-FEATURE-NAME-YYYY-MM-DD.md` as a real file move. Where
`docs/`, `tasks/` and `kb/` each fit is in the `project-knowledge-vault` skill's
`references/lanes.md`.

If the `agent-skills:spec-driven-development` skill is installed, invoke it and
follow its fuller procedure. This command stands on its own without it.

$ARGUMENTS
