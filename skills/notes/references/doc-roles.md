# What each of the six paths is for

Standing detail behind the step 2 table. Read once; the table carries enough to
run the sweep.

## The hot bundle

**`tasks/plan.md`** - the active plan and backlog: tasks with acceptance criteria
and verification. Settled design decisions and closed gotchas do not live here;
they go to `completed/DECISIONS-AND-GOTCHAS.md`, which is an index rather than a
hot file.

**`tasks/todo.md`** - the session-to-session handoff snapshot. It goes stale
fastest and is rewritten from scratch each sweep, not edited downward.

**`tasks/SPEC-FEATURE-NAME.md`** - an ephemeral per-feature spec, one per
in-flight feature, named for it. It is a working doc, not a living one: it folds
into `completed/` on sign-off.

## The cold store

**`tasks/completed/`** holds `plan-completed-YYYY-MM-DD.md`, one per working day,
append-only on that day and immutable after. Retired feature specs move in as
whole files rather than being pasted into a log.

A published `CHANGELOG.md` is a release artifact written for users;
`tasks/completed/` is internal dated history. They are not the same file and one
does not substitute for the other.

## The root docs

**`README.md` is the USE guide**, written for a reader who is not you: what it is,
how to run it, how to use what it ships. Roster level - name the parts, link to
their own files, and do not restate how each works. Rationale, gotchas, internals
and status belong in `tasks/plan.md`.

Carve-out: an architecture section belongs in README when the mechanism **is**
what the reader operates - a sync model, a protocol, a data flow.

**`SPEC.md` is the architectural spec**, written for whoever maintains or extends
it: what it is, what it deliberately is not, invariants, boundaries, constraining
decisions. Always true to now; completed history never accumulates here.

The one-line split: **README says how to USE it, SPEC says what it IS.**

## Flow through the bundle

Plan the work in `plan.md` (plus a feature spec when it is a feature), track it in
`todo.md`. On completion the finished records **move** into `tasks/completed/` and
the durable truth is rewritten into the root docs. Hot files stay lean and
current; nothing is deleted, only relocated.

## The conversion trap

A feature spec that shipped into a repo with no `tasks/completed/` folder stays
where it is and is flagged in a `todo.md` entry. Creating the folder for it is a
layout conversion by another name, and conversions never happen during a sweep.
