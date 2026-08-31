---
description: Look over my shoulder. Spawn the fresh-context supervisor peer to scrutinize in-flight work for scope drift, context rot, rookie mistakes, lazy shortcuts, over-engineering, and safety landmines. Non-blocking and advisory.
---

Invoke the `cover-me` skill.

Spawn the **`supervisor`** subagent in a forked/parallel context and hand it the
brief it needs:

1. **Task intent**: what this work is actually supposed to do, in a sentence or
   two (the yardstick for drift).
2. **Work so far**: the diff (`git diff` / `git diff --cached`), files touched, or
   a description of actions taken/planned.
3. **Stakes**: mission-critical/irreversible vs. routine.

The natural-language remainder of the request refines the focus (e.g. "watch for
scope creep," "I'm worried about the migration"). If intent or stakes aren't
clear from the conversation, infer them from the current work and state your
inference in the brief rather than stalling.

Relay the supervisor's verdict (on track / watch out / stop and rethink)
and its findings back to the user. It is **advisory**: surface the flags, don't
silently act on them or block on them. For depth it defers (full code review,
security), route to `agent-skills:code-review-and-quality`,
`my-security-review-checklist`, or `agent-skills:security-and-hardening`.
