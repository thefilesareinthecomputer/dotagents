# Auditing a board

Defects that part-built boards carry, and the checklist run before handing work
back. Run the catalogue during Step 2 and the checklist during Step 7.

**`scripts/board_lint.py` decides everything mechanically decidable.** Run it
before reading any of this by hand:

    python3 scripts/board_lint.py BOARD.md

It covers ID form and regime, duplicate IDs, heading levels, parent and
dependency resolution, cycles, execution-order violations, missing blocks, fence
widths, template residue, body budgets, checkbox usage, compound titles, empty
features, epics with no closing condition, and the closeout shape - title against
body, State against box, done over an unmet condition. Checks below marked
**[lint]** are its job; the rest need judgment and are yours.

## Contents

- [Reporting](#reporting)
- [Structural defects](#structural-defects)
- [Coverage defects](#coverage-defects)
- [Sizing defects](#sizing-defects)
- [Content defects](#content-defects)
- [Grounding defects](#grounding-defects)
- [Closeout defects](#closeout-defects)
- [Pre-handoff checklist](#pre-handoff-checklist)

## Reporting

Report findings as a flat list of item ID, defect, and the fix, ordered by how
much rework each one causes if left. Do not soften a finding, and do not fix a
structural or coverage defect silently - those change what the team commits to,
so they go to the user as decisions. Content defects inside blocks you are
already authoring get fixed in place.

## Structural defects

- **Orphan.** A parent reference pointing at an ID not present in the file. It is
  either a typo, or the parent lives on the tracker but was never written into
  the board file. Confirm which; never invent the parent.
- **Missing parent reference.** Parentage implied only by document position.
  Position does not survive an edit.
- **A predecessor line reading `none`.** Omit the line instead. Most items have no
  predecessor, and a field repeating that on every one of them is noise.
- **A declared child or successor.** Both are the inverse of a link that already
  exists, so the second copy drifts and nothing compares the two.
- **Heading level collision.** Two levels of the hierarchy sharing a heading
  depth, so features and stories cannot be told apart structurally. Report it
  and ask before moving any heading.
- **Duplicate ID.** Two items carrying the same number. One is a copy-paste
  error, and the board itself will disagree with the file.
- **Template drift.** Blocks with different field names, fence widths or field
  ordering than the templates in `anatomy.md`. Normalize them.
- **Wrong placeholder form.** Zero-sequence IDs such as `000001` sitting in a
  board that already carries real numbers. They read as real and sort as real;
  convert to the `NNNN` form.
- **Colliding placeholders.** Two new items sharing a placeholder, so a parent
  or dependency line pointing at it cannot resolve.

## Coverage defects

- **Unevidenced Completion Evidence.** A line in an epic's Completion Evidence
  that no story underneath produces. This is the highest-value check in the whole
  audit, because it finds work the team committed to and never planned.
- **Unclaimed story.** A story producing something no parent lists. Either the
  epic understates its scope or the story does not belong.
- **Empty feature.** A feature with no stories under it. Either the stories are
  missing or the feature was a story.
- **Untraced criterion.** A feature criterion naming no story that satisfies it,
  or naming a story under a different feature. **[lint]**
- **Uncovered story.** A story no criterion of its own feature names. Either the
  feature never asked for it or a criterion is missing. **[lint]**
- **Overlap.** Two items whose acceptance criteria would be satisfied by the same
  work. One absorbs the other, or the boundary gets redrawn.
- **One job wearing two story headings.** The specific overlap that survives
  review, because both items look substantial and neither is wrong. The tell is
  two adjacent stories whose one-line summary is the same sentence - both
  "reconcile X against reality", both "document Y". Test it by asking what
  question each answers that the other cannot. A real answer is the boundary, and
  both get rewritten around it; no answer means it is one story. Reach for the
  boundary first, because it usually exists and it keeps both tracker IDs alive.
- **Missing negative path.** No item anywhere addresses failure, absence,
  recovery or out-of-tolerance conditions for a capability the epic claims.

## Sizing defects

- **Over the two-day ceiling.** A story that could not close in 1 to 2 days by
  one person or pair. The most common defect on any board and the one that
  quietly wrecks sprint predictability.
- **Container item.** No closing condition - "remediate all defects", "handle
  issues as they arise". Time-box it, or split it into today's known items.
- **Feature wearing a story's heading.** Multiple independent testable outcomes
  under one story ID. The reliable tell is a story whose acceptance criteria
  close on its own children - "all supporting user stories are completed or
  formally deferred", "the feature is reviewed and approved". A story cannot
  have supporting stories, so an item saying so was authored as a feature and
  demoted. Promote it back, keeping its ID, and write real stories underneath.
  Someone working to a year-long epic model demotes these routinely, because at
  that scale a two-week item does look like a story.
- **Story wearing a feature's heading.** A feature with one story, or a feature
  whose acceptance criteria are a single testable outcome.
- **Horizontal slice.** A story whose only evidence of completion is that a
  component now exists.

## Content defects

- **Unfilled skeleton.** Template placeholders left in place - `{role}`,
  `Criterion 1`, `Step n`. Distinguish an untouched item from one where real
  prose was pasted below a skeleton that was never cleared; the latter is a
  repair, and the procedure is in `anatomy.md`.
- **Untestable criterion.** Unmeasurable adjectives - reliable, appropriate,
  sufficient, robust, clean. Replace with the threshold, count, window or
  artifact.
- **Compound criterion.** One line carrying two conditions, usually joined by
  "and". Split it, because half of it will pass and half will not.
- **Title restated as a criterion.** Carries no information.
- **Non-additive criterion.** A line that records a state of mind and leaves
  nobody anything to do: "unconfirmable entries are marked unverified rather than
  assumed", "risks are understood". Give the uncertainty a destination - a
  backlog item, a named owner, a follow-up story - or cut the line.
- **Criterion with no destination.** An artifact criterion that does not say
  where the artifact lands. "Stored with the deliverables" and "added to the
  documentation" cannot be checked; the repository, branch and path can.
- **Build story for a thing that exists.** A story to create what the grounding
  source already contains. Usually a notebook, job or runbook nobody looked for.
  The repair is to rewrite the story around running, extending or correcting the
  existing artifact, starting from its real path.
- **Missing testing approach.** Almost universal in inherited boards, because
  source prose states what must be true and not how it is observed. Derive it
  from the criteria.
- **Placeholder role.** "As a user" where the engagement has actual named roles.
- **Absent business case.** A reason that is a restatement of the activity
  rather than the consequence of not doing it.
- **Unowned item.** No Primary Owner where the item's level calls for one.
- **Bloat.** A body over its budget in `anatomy.md`, prose where a checkbox
  belongs, a checkbox wrapping past one line, preamble before the substance, or
  intensifiers and hedges padding the text.
- **Missing checkboxes.** Activities, steps, criteria or test cases written as
  plain bullets or prose, so nobody can tick them off as the item is worked.

## Specificity defects

The dominant failure when writing from a rich grounding source. Each item below
is individually defensible and collectively produces a board nobody can act on.

- **Names nothing real.** A story referencing no object, table, job, source or
  endpoint from the grounding source. It reads identically on any system of its
  kind, so the engineer who picks it up has to come back and ask. **[lint]**
- **Placeholder phrasing.** "The table", "the inventory", "each source", "where
  practical", "representative", "as appropriate". The general shape of the work
  is easy to write; the specifics require going back to the source. **[lint]**
- **Unnamed test target.** A Testing Approach that says to verify something
  without naming what to run it against.
- **Category instead of instance.** "Validate the upstream feeds" where the
  source names each one, and where some behave differently from the rest.
- **Count stated vaguely.** "Some sources are not configured" where the source
  supports naming exactly which, and how many.

The repair is not rewording. Go back to the grounding source, take the real
names, and put them in.

## Grounding defects

These only apply when a repo, vault, document set or system was supplied as the
grounding source, and they are the ones that make a plausible board wrong.

- **Building what exists.** A story to create something the source shows already
  present. The real story usually starts from how the existing thing falls
  short.
- **Acting on what does not exist.** A story naming a component, job, table or
  endpoint absent from the source. Either it is planned by another item, or the
  story was written from the generic shape of this kind of work.
- **Renamed subject.** An item using its own vocabulary rather than the source's
  identifiers, so nobody can match the story to the thing.
- **Unsourced current-state claim.** An assertion about how things work today
  that traces to no observation. It is an assumption, and it gets labelled as
  one or removed.
- **Stale baseline.** The board was written against an earlier state of the
  source. Worth checking whenever inherited items predate recent changes.

## Closeout defects

These surface when a board is being closed against a tracker rather than written,
and every one of them is invisible until someone tries to close an item. Start
from `scripts/board_query.py BOARD.md --status`, which reports each item's own
box counts, its declared State, and for each parent whether it is closeable and
which children block it. `--trace` prints the feature coverage map whole, both
directions, rather than only where it is violated.

- **Title and body disagree.** A title ticked done with body boxes still open,
  or every body box ticked under a title left open. One of the two is stale.
  **[lint]** `done-with-open-boxes`, `boxes-done-title-open`.
- **Closed over an unmet required condition.** A title ticked done while a
  Definition of Done box is unchecked, with nothing recording why. Silently
  ticking the box is the failure this catches; the item either finishes the
  condition or carries an `**EXCEPTION**` section naming what is unmet, why, who
  owns it and the agreed disposition. The field set is the team's to define; that
  one exists is not. **[lint]** `done-without-exception` is an error.
- **Two criteria lists in two forms.** One list supplied by whoever owns the item
  externally, as plain bullets, and a working list in checkbox form, under
  headings that differ only in case. Traceability and status read only the
  checkbox list, and at closeout nobody knows which one closes the item. Keep one,
  or state which is the contract. **[lint]** `criteria-dual-form`,
  `duplicate-section`.
- **Parent with a body and no criteria.** Not empty - it has a title and prose -
  but nothing says when it closes. Distinct from an empty feature. **[lint]**
  `feature-no-criteria`.
- **State written as a hedge.** A `- State:` value such as two values with a
  slash and a question mark. A field the tooling treats as one value has had a
  doubt written into it, and nothing else validates it. **[lint]** `state-hedged`.
- **State vocabulary drift.** The same value in two spellings, a value used once
  on a board where another covers ten or more, or a state carried by both ticked
  and unticked titles. The linter never names a valid set; it discovers the set
  the board uses and flags what falls outside its shape. **[lint]**
  `state-variant`, `state-singleton`, `state-box-disagree`.

A parent's own boxes are the ones between its heading and the next heading of
any level. Counting to the next heading at the same or a shallower level folds
every child in, and makes the parent look far less complete than it is. The
parser stops at any heading, so both scripts count correctly; a hand-rolled
count usually does not.

## Pre-handoff checklist

Every line is answered before reporting the work done. State any that failed and
were left, with the reason.

1. `board_lint.py` exits 0, and every warning it raised was fixed or
   consciously accepted. **[lint]**
2. Every existing ID present at the start is still present, unchanged, in the
   same item. Diff against the original to prove it rather than recalling it.
3. Every placeholder is listed in the handoff report for backfill.
4. Every parent reference that the linter could not resolve is confirmed as
   living on the tracker rather than being a typo.
5. Every Completion Evidence line is produced by some item beneath its epic, and
   every item produces something its parent lists.
6. Every feature has an owner.
7. Every story has a user story sentence with a real role and a real business
   case, not a placeholder role or a restated activity.
8. Every story could close in 1 to 2 days by one person or pair.
9. Every Definition of Done criterion is singular and answerable yes or no by
   someone who did not do the work.
10. Every criterion states a condition that holds rather than an activity
    performed, and carries no unmeasurable adjective.
11. At least one criterion per story covers the negative path.
12. Every claim about current state traces to the grounding source or to the
    user, and everything else is labelled TBD or assumption.
13. No item duplicates another's scope.
14. Nothing was added that the user did not ask for and was not told about.
15. When closing items: `board_query.py --status` shows no flagged item, every
    parent reported closeable is the one being closed, and every item ticked done
    with an open Definition of Done box carries an exception section. **[lint]**
