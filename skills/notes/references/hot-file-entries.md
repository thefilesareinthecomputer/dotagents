# Hot-file entries: examples

Hot files (`SPEC.md`, `README.md`, `tasks/plan.md`, `tasks/todo.md`) load into
context every session. Aim for information density: every field load-bearing,
nothing a future session could reconstruct from the cold store or git.

---

## What belongs where

| Content | Home |
|---|---|
| Active task, blocker, owner, next action | `tasks/todo.md` |
| Phase breakdown, acceptance criteria, architecture notes, failure modes | `tasks/plan.md` |
| Finished work, the full narrative record | `tasks/completed/plan-completed-YYYY-MM-DD.md` |
| Per-file add / edit / rename / archive | the repo's changelog, if it keeps one |
| Durable cross-session working knowledge | memory |
| Why this code looks like this | a comment, or an ADR |
| Current state and scope | `SPEC.md` / `README.md` |

---

## Examples

**Shipped initiative** - state, rule, pointer, open item.

> 12. **Auth refresh rewrite - SHIPPED 2026-03-04.** Record: `completed/plan-completed-2026-03-04.md`.
>     - **Rule:** never trust client clocks for expiry.
>     - **Code:** `auth/refresh.ts`, `middleware/session.ts`.
>     - **OPEN:** mobile client still on the old refresh path.

**Active workstream** - the choice, its one-line why, the next action.

> 7. **Search indexing - IN PROGRESS.** Using C (A: licensing, B: unmaintained). Nightly full rebuild.
>     - **Next:** wire the rebuild into CI.

**Blocker** - dated, referenced, with a consequence and a trigger.

> 9. **BLOCKED - read access to the reporting DB.** Requested 2026-03-01, ticket OPS-4412, no owner assigned. Blocks items 10 and 14. **Escalate if not granted by 03-08.**

**Decision** - the choice and the single constraint that settled it.

> **Chose X over Y:** Y needs a per-tenant migration that cannot be scheduled this quarter. Revisit after the tenancy work lands.

**Session handoff** - the exact next action and what a fresh session needs to run it.

> **NEXT:** finish `parse_header()` in `src/parse.py` - it handles quoted delimiters but not escaped quotes. Failing case is pinned in `tests/test_parse.py::test_escaped_quote`. Run `pytest tests/test_parse.py -k escaped`.

**Correction to a prior entry** - state the new truth, not the history of the error.

> **CORRECTED 2026-03-11:** the nightly job runs at 02:00 UTC, not 02:00 local. Item 8's schedule assumption was wrong.
