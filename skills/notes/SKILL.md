---
name: notes
description: End-of-session documentation sweep. Use when the user types /notes, says "take notes", "update the docs", "write up the session", or at the end of ANY work session - including in a fresh repo with no docs yet - to capture everything completed, learned, resolved, decided, planned, implemented, or discovered into the repo's living docs (SPEC.md, README.md, tasks/plan.md, tasks/todo.md, created if missing), enforce the hot-file size budgets, and roll finished work into tasks/completed/, the per-date cold-storage folder. Docs only - it never commits or pushes; a whole-session closeout that also commits belongs to wrap-up, and promoting knowledge to permanent memory belongs to reflect. A dictated one-line edit to a README is a plain edit, not a sweep.
---

# Notes - session documentation sweep

Fold what the session produced into the living docs so the next session starts
from current truth.

**The sweep runs once, forward.** Steps 3-5 settle the `tasks/` bundle; step 6
then checks the root docs and is the only step that touches them. Finish a step
and do not reopen it - if step 6 surfaces something for `plan.md`, add the line
and keep going. A late trim to a hot file is bounded and fine; reopening
`README.md` or `SPEC.md` means re-running step 6's heading map.

## Step 1 - Reconstruct

**If `reflect` just ran, take its reconstruction and skip to step 2.** It walked
the same session; walking again costs full price and risks the two passes
disagreeing. Same for a git assessment already run this turn.

Otherwise list concretely: **completed** (with paths), **learned**, **resolved**,
**decided** (and the why), **planned**, **changed**. Pull from the conversation
and the tree, cross-checked against `git status` and `git diff`. **Do not invent
progress.**

## Step 2 - Locate and measure

Six paths, at the repo root, and no others:

| File | Role |
|------|------|
| `tasks/plan.md` | Active plan and backlog (hot) |
| `tasks/todo.md` | Session handoff snapshot (hot) |
| `tasks/SPEC-FEATURE-NAME.md` | Per-feature spec, one per in-flight feature (hot, ephemeral) |
| `tasks/completed/` | Cold store - dated `plan-completed-YYYY-MM-DD.md`, immutable after its day, plus retired feature specs moved in whole |
| `README.md` | How to USE it. Roster level |
| `SPEC.md` | What it IS - invariants, boundaries, constraining decisions |

`references/doc-roles.md` has the full roles and the README/SPEC boundary.
Everything else - `AGENTS.md`, rules files, a published `CHANGELOG.md` - is out of
scope.

**Read each file before editing it.** Create a missing hot file when the work
warrants one; create today's `plan-completed-YYYY-MM-DD.md` only when something
moves into it. **Read the `tasks/` bundle now and leave `README.md` and `SPEC.md`
closed** - step 6 opens them by heading map.

**Legacy layouts** (root `PLAN.md`/`HANDOFF.md`, or a single append log): sweep
into the files that exist and record the conversion as a `todo.md` entry. Never
convert a layout during a sweep.

```bash
wc -l SPEC.md README.md tasks/plan.md tasks/todo.md
```

| File | Budget | Over |
|------|--------|------|
| `tasks/todo.md` | ~100 | **Rewrite from scratch.** |
| `tasks/plan.md` | ~400 | Active work and open backlog only. |
| `SPEC.md` / `README.md` | skimmable | Rewrite stale sections; history never accumulates. |

**The budget is a ceiling and the default posture is deletion.** These load every
session, so a stale line is a tax paid forever. A sweep that only adds is not a
sweep, and a finding fixed by appending a clause is usually fixed wrong: replace,
merge or relocate first, and add only when nothing existing can carry the fact.

**One test per item: does this change what a session does next?** If not it is not
hot, whatever its history. Shipped work, settled decisions, closed gotchas,
merely-interesting background, and anything whose next action is "someone should
decide" with nobody named all fail it.

**`todo.md` is rewritten, not edited.** Build from what the next session needs
rather than pruning what is there - editing downward preserves whatever nobody
argued against, which is how it triples.

**Then reconcile the rewrite against what it replaced**, because a from-scratch
rebuild is the one shrink path that leaves no trace: an item nobody recalled is
silently absent rather than relocated. Diff the new file against the old and
account for every dropped item - finished, moved to cold storage, or named in the
report. Nothing leaves by being forgotten.

**Watch for the category that can never leave.** A file that grows while every
sweep passes has a section whose items have no exit condition. Fix the exit route,
not the procedure, and move the whole section if it qualifies.

## Step 3 - Update the bundle

Merge findings into `plan.md`, `todo.md` and any in-flight feature spec. Edit
surgically, preserve each file's voice. **Do not touch `README.md` or `SPEC.md`** -
note anything they make false for step 6.

**A hot file is a working index, not a narrative.** One entry is a few lines:
state, blocker, next action, pointer. Point rather than restate. Keep exact names,
paths, commands and one-line whys; cut narration, replayed debate, rejected
options and history kept "for context". **Concision is not the goal, density is** -
an entry omitting the blocker is as broken as a paragraph retelling the week.
`references/hot-file-entries.md` has an example per type and a routing table.

## Step 4 - Relocate to cold storage

Finished work leaves the hot files for **today's** `plan-completed-YYYY-MM-DD.md`
(date from the environment or `date +%F`, never guessed), headed `## YYYY-MM-DD`.
**Relocate, never delete.**

A shipped feature spec **moves as a file**:
`git mv tasks/SPEC-NAME.md tasks/completed/SPEC-NAME-YYYY-MM-DD.md`. Never paste a
spec body into the log.

Past-date files are immutable. Corrections happen in the living docs.

## Step 5 - Compress what survives

- **Compress the telling, never the reasoning.** Cut how the work went, keep the
  why. A rationale too long for a hot file **moves verbatim** into today's cold
  file leaving a claim and a pointer - never shortened into a claim with no
  reasoning behind it.
- **Settled dev docs leave `plan.md`** - still true, no longer changing. Move
  verbatim, leave a one-line claim. Live gotchas stay hot.
- **Unresolved items are never dropped** - keep a one-line pointer and flag it.
- Trims of agent-written entries apply directly; compressing what the user wrote
  by hand is proposed, not applied.

## Step 6 - Root docs: false claims only

Nothing moves into `README.md` or `SPEC.md`. The only question is whether the
session made something they assert untrue.

```bash
grep -nE '^#{1,5} ' README.md SPEC.md
```

Heading by heading: did this session invalidate this? A renamed path, a changed
command, a retired mechanism, a shipped thing still called planned, a count that
moved. Read and edit only where the answer is yes. Correct what is false and
nothing else - no session history, no regeneration, no end-to-end read.

## Step 7 - Re-measure and report

Re-run the step 2 measurement and report **before → after** counts. A hot file may
end larger only when the session added that much active state, and the report says
so. **Reporting a number instead of running the relocation is not a close.**

Then: files updated or created, what moved to cold storage, and anything left out.
A restructure too large for this sweep becomes a `todo.md` entry naming the
decision it needs - the report is chat output and does not outlive the session.

## Guardrails

- **Non-destructive, except downward.** Read before edit; merge, never gut.
  Relocation is the only sanctioned way hot files shrink, and it is not deletion.
- **Appending is not maintaining.** A pass that only adds is incomplete.
- **Six paths, one pass.** Anything else belongs to another skill.
- **Don't name the user**, and **no secrets** - these files are tracked, so treat
  them as public. Record that a value exists and where it lives, never the value.
- **Evidence over narrative.** Every claim traces to a real change.
- Writes docs only. Does not commit or push unless asked.
