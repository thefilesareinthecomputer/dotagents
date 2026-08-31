# Decomposition and sequencing

How work divides into epics, features and stories, how to tell when an item is
the wrong size, and what order to put them in.

## Contents

- [The three levels](#the-three-levels)
- [Boundary tests](#boundary-tests)
- [Sizing tests](#sizing-tests)
- [Splitting](#splitting)
- [Vertical slicing](#vertical-slicing)
- [INVEST, as a checklist that fires](#invest-as-a-checklist-that-fires)
- [Sequencing](#sequencing)
- [Investigation work](#investigation-work)

## Establish the epic cadence first

Level definitions are relative to how long an epic runs on this engagement, and
teams differ by an order of magnitude. An epic can be a year, a quarter, or one
to two weeks. Ask, or read it off the existing board's history.

At a one-to-two-week epic cadence everything shifts down: an epic is what a
longer-cadence team would call a sprint goal, a feature is a few days, and a
story is one sitting. Someone carrying a year-long-epic model into that setting
will produce features where stories belong and will keep demoting items that
look too small, which is what generates container items later.

The story ceiling below does not move with cadence. Only the levels above it do.

## Capacity is a constraint on the board, not a footnote

Before writing bodies, multiply available engineers by working days and compare
against story count at one to two days each. A 30-item board against 15
engineer-days is not a plan, and finding that out after the bodies are written
wastes the expensive half of the work.

Where the two do not reconcile, the levers are scope, the story ceiling, and
writing only what the team can start while leaving the rest as titled
placeholders. Which lever to pull belongs to the user. Presenting the arithmetic
belongs here.

Watch for completion evidence that is wall-clock rather than effort. An epic
requiring a successful production run history, an observation period, a close
cycle or a soak test cannot be compressed by adding people, and that item sets
the floor date no matter how the rest is sequenced. Sequence it terminal, make
its dependency on everything upstream explicit, and say plainly that the close
date is upstream-complete plus the period.

## The three levels

**Epic.** One outcome, spanning several sprints, answering a single primary
question. It closes when its End State holds and its Completion Evidence exists.
An epic is bounded by what it excludes at least as much as by what it contains,
which is why the Out of Scope list is not optional.

**Feature.** A coherent slice of an epic with one accountable owner, completable
within a release or quarter. It delivers something a stakeholder can be shown.
Between two and roughly six stories.

**Story.** One independently testable unit of work, for one person or pair,
**sized 1 to 3 points and finishable in 1 to 2 days**. It has a beneficiary, a
reason, an approach and a way to be proven done.

The 1-to-2-day ceiling is the hard constraint and the one most often broken. A
story that cannot plausibly close inside two days is not a small story, it is a
feature that has not been split yet, and it will sit open across sprints
absorbing unrelated work. Size every story against that ceiling before writing
its body, not after.

The levels are about completeness of outcome as well as size. A half-day task
with its own testable outcome and its own beneficiary is a story; a half-day
task that only makes sense as part of another story's outcome is a step inside
that story's Development Approach.

## Boundary tests

Apply these when unsure which level something belongs at.

| Question | If yes |
|---|---|
| Can its end state be demonstrated within one sprint? | Not an epic |
| Does it deliver something a stakeholder can be shown? | At least a feature |
| Is it independently testable, by one person or pair, in 1 to 2 days? | A story |
| Would it take more than 2 days? | Not a story yet - split it |
| Does it only have meaning as part of another item's outcome? | A step, not an item |
| Does it need more than one owner to close? | Too big for its level |
| Would splitting it produce halves with no standalone value? | Leave it whole |

## Sizing tests

Signals that an item sits at the wrong level:

- **A story that could not close in two days.** The primary test; everything
  below is a proxy for it.
- A story estimated above 3 points.
- A story whose Definition of Done runs past seven criteria.
- A story whose Development Approach exceeds six steps.
- A story whose testing approach spans two systems or two teams.
- A story whose title contains "and", or a list, or the word "all".
- A story needing more than one person, or a handoff between people, to close.
- A feature with a single story - it was a story with extra headings.
- A feature with more than about eight stories - there are two features.
- An epic whose End State is demonstrable in one sprint.
- Any item with no owner able to close it alone.

Estimate before writing bodies. Sizing an item after its prose exists biases
toward keeping it, because the prose already represents effort spent.

Open-ended containers deserve particular suspicion. An item phrased as
"remediate all defects", "address issues as they arise" or "monitor ongoing
quality" has no closing condition and will stay open forever. Either time-box it
to a named window with a fixed intake list, or split it into the specific items
known today, or both.

## Splitting

When an item is too big, split along one of these seams, in rough order of
preference:

1. **By workflow step.** The stages the work naturally passes through.
2. **By data or interface variation.** One source, format, endpoint or tenant at
   a time, where each is genuinely different work.
3. **By operation.** Read before write, happy path before error path, manual
   before automated.
4. **By rule complexity.** The simple rule first, the exceptions after.
5. **By investigate-then-act.** A spike that answers the unknown, then the work
   its findings define.
6. **By defer the hardening.** The functional outcome first, then performance,
   resilience or scale as a separate item with its own thresholds.

Avoid splitting by technical layer. Two halves called "back end" and "front end"
each deliver nothing, and neither can be tested against a user-visible outcome.

Splitting an item that has a board ID: the original ID stays with the child
carrying the original intent, and the new sibling gets a placeholder. Say which
child kept it.

## Vertical slicing

A story cuts through whatever stack it touches far enough to produce an
observable result. "Define the data model" is not a story; "a user can save a
draft and reopen it unchanged" is, and it happens to require the data model.

The test: can the story's completion be observed by someone who did not build
it, using something they can look at? If the only evidence is that a component
now exists, the slice is horizontal and the story is a step.

## INVEST, as a checklist that fires

Run over each story. A failed letter is a rewrite, not a note.

- **Independent** - can be worked without waiting on a sibling, or its blocker
  is recorded on the dependency line.
- **Negotiable** - states the outcome, leaving implementation open. A story that
  prescribes exact code is a task.
- **Valuable** - names who benefits and what they can then do. If the
  beneficiary is only the team and the value is only tidiness, justify it.
- **Estimable** - someone who has not done the work could size it. If not, the
  unknown is the real story; write that instead.
- **Small** - closes in 1 to 2 days, 1 to 3 points, including the testing it
  names. This letter fails most often and is the one to check first.
- **Testable** - each Definition of Done criterion can be answered yes or no by
  someone who did not do the work.

## Sequencing

Document order is execution order, and every dependency is also recorded
explicitly, because position stops being trustworthy the first time a feature is
expanded in place.

Ordering heuristics, in priority order:

1. **Unknowns first.** Investigation whose findings would reshape downstream
   work goes before that work. Sequencing an implementation behind a spike whose
   answer might cancel it is the whole point of the spike.
2. **Baseline before remediation.** You cannot fix, count, or prove complete a
   population you have not enumerated. Inventory and mapping precede everything
   acting on the inventory.
3. **Foundations by dependent count.** Among unblocked items, the one with the
   most dependents goes first.
4. **Unblock others before yourself.** Work another team is waiting on outranks
   work only this team is waiting on, even when it is smaller value in
   isolation.
5. **Risk reduction per unit effort.** Among comparable items, the one that
   retires the most uncertainty for the least work.
6. **Evidence-producing work before work that consumes the evidence.** A story
   whose Completion Evidence another story's Development Approach reads has to
   precede it.

Two sequencing errors are worth checking for by name. A cycle, where two items
each list the other as a dependency, means the boundary between them is drawn
wrong and they should be merged or re-cut. And a critical path running through
an item nobody owns, which is a schedule risk masquerading as a planning
detail; surface it rather than sequencing around it.

## Investigation work

Investigation stories are first-class and close legitimately on a documented
finding. Their Definition of Done is the existence and review of the finding,
not a decision going a particular way.

Write them so they terminate. The criteria are that the question is answered,
the evidence is captured, the risks are recorded, and follow-up items are either
created or explicitly found unnecessary. "Determine whether X" closes whichever
way the answer goes; "make X work" does not close at all if X turns out to be
the wrong thing.

Every investigation story should say what it will do with each possible answer.
An investigation whose outcomes all lead to the same next step did not need to
happen.
