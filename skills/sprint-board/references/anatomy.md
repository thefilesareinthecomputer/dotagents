# Item anatomy

The canonical templates, the ID regimes, and what belongs in each field.

These templates are the specification. A target file's existing items are the
work, not the model - a partially built board is expected to diverge from this,
and closing that divergence is the job.

## Contents

- [Document shape](#document-shape)
- [Epic template](#epic-template)
- [Feature template](#feature-template)
- [Story template](#story-template)
- [ID regimes](#id-regimes)
- [Fence semantics](#fence-semantics)
- [What goes in each field](#what-goes-in-each-field)
- [Cryptic writing](#cryptic-writing)
- [Writing the user story sentence](#writing-the-user-story-sentence)
- [Writing acceptance criteria](#writing-acceptance-criteria)
- [Repairing a mis-slotted block](#repairing-a-mis-slotted-block)

## Document shape

Three heading levels carry the hierarchy, and nothing else uses them:

    # EPIC-{id}
    ## FEATURE-{id}
    ### STORY-{id}

Items appear in execution order, separated by a `---` horizontal rule with a
blank line either side.

**Parent is the only link an item must declare**, as `- Parent: FEATURE-{id}` directly under the title, carrying the prefixed ID so the reference reads on its own. Parentage is stated rather than implied by position, because position stops being trustworthy the first time a feature is expanded in place.

Two optional lines follow it. `- Predecessor: STORY-{id}` appears only where something genuinely blocks the start, and is omitted entirely otherwise rather than written as `none`. `- Related:` appears at most once, and only where it carries something the parent and predecessor chain does not.

**Downward links are never declared.** Children and successors are the inverse of a link that already exists, so writing them creates a second copy that drifts, and nothing checks the two against each other. A feature's children are whichever items name it as parent.

## Epic template

`````
# EPIC-000000
- [ ] {Epic Title}

**DESCRIPTION**
````
**OUTCOME**: 
{What this epic delivers or verifies, in two or three sentences.}

**PRIMARY QUESTION ANSWERED**: 
{The single question that, once answerable, means this epic is done.}

**OUT OF SCOPE**: 
- 

**END STATE**: 
- 

**COMPLETION EVIDENCE**: 
- 
````
`````

## Feature template

`````
## FEATURE-000000
- [ ] {Feature Title}
- Parent: 
- Depends on: 

**DESCRIPTION**
````
**PURPOSE**: 
{What this establishes, and the outcome that makes it worth doing.}

**KEY ACTIVITIES**: 
- [ ] 

**ACCEPTANCE CRITERIA**: 
- [ ] {Condition} (STORY-000000)

**SCOPE BOUNDARY**: 
{What belongs here, and what belongs to adjacent work.}

**PRIMARY OWNER**: 
**CONTRIBUTORS**: 
````
`````

## Story template

`````
### STORY-000000
- [ ] {Story Title}
- Parent: 
- Depends on: 

**DESCRIPTION**
````
**ORIGINAL REQUEST**: 
{The ask as it was made, in the requester's own terms. Omit only when the story originates from the decomposition itself rather than from a request.}

**USER STORY**: 
As a ({role} OR {team}), (I OR we) need {new functionality}. This is due to {business case}. To achieve this functionality, (I OR we) will {development actions}. This will enable {downstream functionality}.

**DEVELOPMENT APPROACH**: 
- [ ] Step 1: 
- [ ] Step n: 
````

**ACCEPTANCE CRITERIA**
````
- [ ] Criterion 1
- [ ] Criterion n

**VALIDATION**: 
_Starter queries, adapt or extend as needed._
- [ ] {Runnable query or command evidencing a criterion, against real object names}
- [ ] {Step that cannot be queried: an approval, a deploy, a confirmation from an owner}

**DEFINITION OF DONE**: 
- [ ] {Evidence linked, naming what it is: a commit, a run, a query result}
- [ ] {Reviewed and approved by the named reviewer}
- [ ] {Stored in the named location}
- [ ] {Impacted documentation updated, or confirmed unaffected}
- [ ] {One line for the work type where the standard carries one: CI checks, retained validation evidence, release evidence and rollback guidance}
````
`````

The heading above each fence is the tracker's field name, and the fence is what gets pasted into it. So the criteria need no label of their own - they are the first thing in the field that is already called Acceptance Criteria - while the blocks after them do, because one tracker field is carrying three things.

Only stories carry a separate `**ACCEPTANCE CRITERIA**` block. Epics and features
hold their completion conditions inside the description block, because that is
the single field their tracker item exposes.

## ID regimes

Three regimes, and which one applies depends on where the ID comes from.

### Existing IDs are immutable

An item carrying a real ID exists on a tracker, other people cite it, and a
renumber silently breaks every reference held outside the board file. Never
change one, reuse one, close a gap in a sequence, or invent something that
resembles a real number.

### Drafting a whole board from scratch

One running counter across all item types in document order, zero-padded to six
digits:

    EPIC-000000
      FEATURE-000001
        STORY-000002
        STORY-000003
      FEATURE-000004
        STORY-000005

Every parent reference resolves, and real numbers get find-and-replaced in after
upload.

### Filling gaps in a board that already has real IDs

Sequential zeros are wrong here: `000001` sitting beside a board's own six-digit
IDs reads as a real ID and sorts as one. New items instead take an `NNNN` prefix with a two-digit
counter, keeping the six-character shape so columns line up:

    ## FEATURE-NNNN01
    - [ ] {New Feature Title}
    - Parent: EPIC-{existing id}
    - Depends on: none

    ### STORY-NNNN02
    - [ ] {New Story Title}
    - Parent: FEATURE-NNNN01
    - Depends on: STORY-{existing id}

The counter is unique across the file and continues across item types, so every
parent and dependency line resolves. A new item may depend on an existing one
and an existing item may be given a dependency on a new one; both are normal.

`NNNN` is unmistakably a blank. Never hand a board back with a placeholder the
user could mistake for a number, and list every placeholder in the handoff report
so they know exactly what to backfill.

### Fixtures are not real IDs

Every identifier in this skill's templates, tests, evals and examples is a
fixture: the `NNNNnn` form, a repdigit run such as `111111`, a consecutive run such
as `123456`, or a zero-padded counter. No tracker issues those, and `EPIC-`,
`FEATURE-` and `STORY-` are the universal agile terms rather than anything
project-specific. None of it is sensitive, and a scanner for leaked work-item IDs
passes those shapes silently. A six-digit value that is none of them gets surfaced
for a human or agent to judge, never hard-failed - the rare legitimate
`STORY-777777` cannot be told from a leak by shape, and a test that tries goes
stale the day it is written.

### Splitting and merging

Splitting an item that already has an ID: the original ID stays with the child
carrying the original intent, and the new sibling takes an `NNNN` placeholder.
Say which child kept it. Merging two items that both have IDs is a decision for
the user and never an inference, because one of the two has to be closed on the
tracker.

## Fence semantics

Block bodies live inside code fences because the text is copied verbatim into a
tracker field. Consequences:

- The fence content is a paste buffer. Write plain text with light markdown -
  bold labels, hyphen bullets, checkboxes - and nothing that only renders in the
  authoring tool. No wiki-links, embeds, callouts, block references or
  footnotes.
- Inner fences are four backticks, so a whole block can be quoted inside a
  five-backtick fence. Never use three, and never nest a fence inside a body.
- Trailing spaces after a label such as `**USER STORY**: ` are part of the
  template. Preserve them.

## Concision

Every body is written to be scanned by someone who has ten other items open. The
budgets below are limits, not targets - come in under them.

| Field | Budget |
|---|---|
| Epic outcome | 2-3 sentences |
| Epic out of scope / end state / completion evidence | 3-7 bullets each, one line each |
| Feature purpose | 2-4 sentences |
| Feature key activities | 3-7 checkboxes, one line each |
| Feature acceptance criteria | 4-8 checkboxes, one line each |
| Story user story | the one-paragraph pattern, nothing more |
| Story development approach | 3-4 checkboxes, one line each |
| Story definition of done | 3-7 checkboxes, one line each |
| Story testing approach | 2 checkboxes, one line each |

Rules that apply to every body:

- **Checkboxes wherever the content is a list of things to be done or
  confirmed.** Trackers that render markdown make these tickable, which is how
  the item gets worked. Activities, steps, criteria and test cases are all
  checkboxes. Prose statements and scope boundaries are not.
- One line per checkbox. A checkbox that wraps to three lines is two checkboxes
  or a paragraph in the wrong place.
- No preamble. Start at the substance; nobody needs a sentence explaining that
  the section is about to describe the work.
- Do not restate the title, the parent, or the obvious.
- Cut every intensifier, hedge and throat-clear: comprehensive, robust,
  seamless, it is important to note, in order to, as needed, various,
  appropriate.
- **No performed authority.** These bodies get read by the engineer doing the
  work and by whoever wrote the thing being fixed, so writing that reaches for
  effect costs credibility. Three habits to cut: the "X, not Y" antithesis
  ("this is wall-clock, not effort"), the closing kicker that adds no
  information ("adding engineers does not move it"), and the compressed formula
  where a sentence belongs. State the fact once and stop.
- Progressive disclosure. The first line of any body carries the point; detail
  follows. Someone reading only the first line should still know what the item
  is.
- Name things once and then use the same name, and let that name be the one the
  artifact already has. Synonym variation reads as literary and costs the reader
  a lookup; a role-noun standing in for a filename costs them the file. See
  [Cryptic writing](#cryptic-writing), which carries the five habits that make an
  item unreadable to anyone who was not in the room.
- **Every line states its check and stops.** "X rather than Y" and any trailing
  clause opening "so", "which is" or "since" are arguing for the line to a reader
  who has already accepted it. The reasoning goes in Purpose, once.

If a body cannot fit its budget, the item is too big. Split it rather than
compressing the prose.

## What goes in each field

### Epic

An epic is a multi-sprint outcome answering one primary question.

**Out of Scope** is what stops an epic becoming a permanent container, so it is
never left empty. **End State** lists the observable conditions that hold when
the epic closes. **Completion Evidence** lists the artifacts that prove it, each
one a thing that can be handed to someone.

End State and Completion Evidence are a contract. Every evidence line should be
produced by some item beneath the epic; a line no item produces is a gap, and an
item producing nothing listed is scope drift.

### Feature

A feature is a coherent slice of an epic with one accountable owner, completable
within a release or quarter.

**Key Activities** are the work, as actions. **Acceptance Criteria** are the
conditions for completion, and each one ends with the stories that satisfy it.
**Scope Boundary** states what belongs here versus in adjacent work, and matters
most where a feature could plausibly absorb its neighbours.

    - [ ] Every configured row is confirmed as scheduled or manual-only (STORY-NNNN01)
    - [ ] The declared schedule and the runtime configuration agree (STORY-NNNN02, STORY-NNNN01)

The reference is a pointer, not part of the condition, so it does not count
against the line budget. It only ever names stories under that same feature: a
criterion closed by someone else's story means the criterion or the story is
under the wrong parent.

This makes the feature a coverage map that reads both ways, and both directions
find real defects. A criterion with no story behind it is scope the feature
claims and nothing delivers. A story no criterion names is either work the
feature never asked for or a condition nobody wrote down. Enforced by
`board_lint.py`: `criterion-untraced` and `criterion-misrouted` are errors,
`story-uncovered` is a warning.

### Story

**Original Request** holds the ask in the requester's own terms, before refinement touched it. It is the control against silent expansion: with it present, anyone can see whether the story still answers what was asked, and a scope change becomes visible rather than absorbed. Omit the field only when the story came out of the decomposition rather than from someone's request.

**Development Approach** holds ordered checkbox steps that define the scope of the work. Three to six; beyond six the story is a feature. Each step is a discrete action, but the block is a boundary rather than a method - it says what is included, not how to build it. An engineer picking the story up decides the implementation, and a block that prescribes it either goes stale against what they actually do or reads as being told their job.

**Validation** holds the evidence for the criteria. A runnable query or command where the system can answer the question, written against real object names and pasteable without editing; a short step list where it cannot, one line per step for the approvals, deploys and confirmations that only a person can produce. Most stories carry both. This replaces a separate testing block, because a test case nobody runs and a criterion nobody evidences are the same defect.

Every query opens with one lowercase comment line naming what it returns, because the query gets copied out and read detached from the prose around it. That line is a label, not a sentence: `-- all schemas`, `-- last commit on the table, showing its writer`. Roughly eight words, and nothing about why the result matters, which belongs to the criterion the query evidences. A comment reading `-- distinct source systems configured in the framework, which the register's own count is checked against` has buried its one useful word under the argument for running it.

Any query in this block opens with `_Starter queries, adapt or extend as needed._` on its own italic line. The queries are a head start, not a specification: whoever picks the item up knows the data better than the board does, and without that line a supplied query reads as the only sanctioned way to prove the criterion. The criteria say what must be true; the queries are one way to show it.

**Definition of Done** is a short checklist of the standard's conditions that actually apply to this item, not a citation of the standard and not a copy of it. A bare reference is unusable at the moment someone is trying to close the item, because they have to go and read another document to find out which of its clauses bite here. A full copy buries the two or three conditions that differ between items.

Four lines is usually the whole of it. Each one is a condition from the standard with its variable filled from something already stated in the story, and that derivation is what makes the line repeatable rather than a judgment call:

| Condition | The variable | Where its value comes from |
|---|---|---|
| Evidence is linked | which artifact | what the key activities produce: a commit, a run, a query result, a document |
| Review is complete | who, or nobody | the reviewer set at refinement. Where the standard only requires "a reviewer", do not name one |
| Stored in the agreed place | which branch, repo or path | where the change lands, named as the source names it |
| Impacted documentation updated | which document and section | the documents that name the object in the title |

Add one line where the standard carries a condition for this kind of work: continuous-integration checks for a code change, retained evidence for a reconciliation, release evidence and rollback guidance for a deployment.

Two failure modes to watch. **Never guess a variable.** If a value cannot be derived from the story, either the condition does not apply to this work type and the line is dropped, or it carries an explicit `TBD - <what is needed and who has it>`. Most standards say plainly that they do not require runbook updates for work with no operational impact, or new documentation where the existing text stays accurate, so dropping a line is usually sanctioned rather than a shortcut. **Never pull story content down into this field.** When a line starts restating an acceptance criterion, it is the wrong line: the criteria carry what this story delivers, and the Definition of Done carries what the team expects of any story.

Where no team standard exists, say so once at the board level rather than inventing a per-story one.

Where a grounding source was supplied, the steps act on things named in it. Use
that source's own identifiers for modules, services, endpoints and repos, and
start from what it shows already exists. A step reading "create the X component"
when the source shows X present and failing is the wrong story; the right one
starts from the failure.

Where source material supplied background prose for a story, keep it beneath the
Development Approach rather than discarding it. It is context the original author
had and you do not.

## Register: suggestive in the description, prescriptive in the criteria

The two halves of an item are written in different voices, and using one voice throughout is what makes a board read as though it were generated rather than written.

The description fields - original request, purpose, key activities - are calm and suggestive. They frame the problem and the shape of the work, and they leave the engineer room to decide how. Prefer "give this field a real source-side value, rather than the copy it gets today" over "set this field from the source read"; prefer "the thought from the review was that these checks would sit better at ingestion time" over "move the check to the ingestion job". The person picking the item up knows the codebase better than the board does, and a description that dictates method either goes stale against what they actually build or reads as being told their job.

The acceptance criteria are prescriptive, because they are the contract. Each one is a flat condition that holds or does not, with no hedging and no room for interpretation. "Every enabled row produces a comparison result" rather than "results should generally be produced".

The test is whether an engineer could satisfy every criterion by a route the description did not anticipate. If they could, the balance is right. If the description has already made all their decisions, it has taken over work that was not the board's to do.

## Cryptic writing

The register above governs how much room the engineer gets. This one governs whether they can read the item at all. The failure is writing that makes the reader solve a puzzle before they can start: every fact is technically present, and none of it is stated. It reads as knowing and costs the reader a second pass, or a question they should not have had to ask.

Five moves produce almost all of it. Each is a habit of adding, so each fix is a cut.

**Name the artifact, do not describe its role.** A file has a name and the board is not entitled to invent a second one. "The register", "the inventory", "the document" and "the export" are role-nouns, and a reader holding six open items cannot resolve them. Write `source-to-bronze-inventory.md`. This is the most common of the five and the most expensive, because a role-noun stays readable to whoever wrote it and to nobody else.

    - [ ] Check every source in the register against the schemas in warehouse_bronze
    - [ ] Check every source in source-to-bronze-inventory.md against the schemas in warehouse_bronze

**Cut the trailing rationale.** A criterion, a step or a query comment states the check. It does not argue for the check. Any clause opening with "so", "which is", "since" or "because" and closing the line is defending a decision to a reader who has already accepted it.

    - [ ] Compare the register against the schemas that exist, so a difference is a finding rather than an assumption
    - [ ] Compare the source-to-bronze-inventory.md tables against the warehouse_bronze schemas for each source

The rationale belongs in Purpose, once, where someone deciding whether the item is worth doing will read it. Repeated onto every line beneath, it is noise.

**Name the columns, do not describe their shape.** Identifying a thing by the pattern it makes is the purest form of the failure, because the reader has to reconstruct the query you already ran. "A `MERGE` with job and notebook both empty" asks them to guess which fields those are; naming `operation`, `job` and `notebook` hands it over.

**Cut insider deixis.** "Ours", "the newest commit", "the latest run" and "this one" resolve only for someone who already holds the context. "Ours" in particular assumes the reader knows where the repository boundary falls, which is the thing the item exists to establish. Say which repository, which field, which timestamp column.

**State the alternative, do not describe the act of explaining it.** A criterion offering an escape hatch names the second acceptable state. It does not ask for an explanation and leave the state undefined.

    - [ ] Every source has a bronze schema, or states that it does not and why
    - [ ] Every source has a bronze schema or is listed as no bronze target

A sixth case is not a rewrite. **A criterion nobody can act on is cut, not reworded.** "Each Fivetran schema records what writes it" survives a proofread because every word is defensible, and it still tells the engineer nothing: no artifact, no threshold, no destination. Reaching for a better phrasing keeps a line that was never a criterion. Delete it, and check whether the condition it gestured at is already carried by another line.

The test for all six: hand the item to an engineer who has not been in any of the meetings. Every noun should resolve to something they can open, query or point at.

## Writing the title

The pattern is `{verb the assignee performs} + {thing operated on} + {reason}`, in roughly twelve words. "Create new ingestion condition to avoid loading blank tables" carries all three in nine. "Add the source-to-bronze count check to the DQ monitor" carries only two, and an engineer reading it cannot tell why the check matters or when it is finished.

- The verb is what the assignee does, not what the system ends up doing: locate, diagnose, compare, baseline, identify and mitigate. A compound verb commits to both halves, so "determine and triage" is a larger item than "determine" and carries different criteria.
- The object is the specific thing being touched, named as the grounding source names it.
- The reason is the outcome that tells the assignee when to stop. It is the part most often dropped and the part that makes the title stand alone.

Cut the object when a title runs long, never the reason. A title needing more than twelve words to stay honest is usually describing an item that has not been split.

Each part answers to a field, and checking that mapping catches real defects. The verb comes from what the original request needs done, so a verb the request does not imply means the refinement replaced the ask. The object bounds the development approach, so a step operating on something the title does not name is scope creep. The reason is the purpose in one clause, and the acceptance criteria are what prove it, so criteria that do not verify the reason mean the title and the body have diverged.

## Writing the user story sentence

The pattern is: as a {role or team}, I or we need {new functionality}. This is
due to {business case}. To achieve this functionality, I or we will {development
actions}. This will enable {downstream functionality}.

- The role is a real role on this engagement, not "a user". If the beneficiary
  is the team itself, say so and name the team.
- The business case is the specific pain or obligation driving the work, with
  the concrete consequence of not doing it. "To improve quality" is not a
  business case; "because failures are currently found by users rather than by
  the system" is.
- The development actions summarize the approach in one clause. Detail belongs
  in Development Approach.
- The downstream functionality names a specific next capability, ideally another
  item on this board. If nothing downstream depends on it, question whether the
  story belongs in this scope at all.

## Writing acceptance criteria

Each criterion is one checkable state, answerable yes or no by someone who did
not do the work.

- State a condition that holds rather than an activity performed. "Connectivity
  is validated for every in-scope source" beats "validate connectivity".
- One criterion per line. A line containing "and" is usually two criteria.
- No unmeasurable adjectives: reliable, robust, appropriate, sufficient, clean.
  Replace with the threshold, the count, the window or the artifact.
- Do not restate the title. A criterion that only says the item was done carries
  no information.
- Cover the negative path. At least one criterion should address what happens
  when the thing fails, is absent, or falls out of tolerance.
- Say where the artifact ends up, by path. "Stored with the deliverables" cannot
  be checked; `ingest-runbook.md is merged to main under docs/ingestion/` can. A
  criterion naming an artifact names the repository or system it lands in.
- Every criterion has to leave someone with something to do. "Unconfirmable
  entries are marked unverified rather than assumed" records a feeling and
  changes nothing; either give the uncertainty a destination - a backlog item, a
  named owner, a follow-up story - or cut the line.
- **Name something the reviewer can open.** A closing condition is verified by
  somebody other than the author, so it has to point at a repository path, a
  tracker item, or a system they have access to. A line pointing at a working
  note in the author's own workspace reads as complete to whoever wrote it and
  as missing evidence to whoever reviews it, and the item stalls while each side
  assumes the other is wrong. The working note is a fine home for the work; it
  cannot be the evidence.
- A criterion naming no artifact, threshold or destination is cut rather than
  rewritten. "Each Fivetran schema records what writes it" reads as a condition
  and is not one, and looking for a better phrasing preserves a line that never
  belonged. Check first whether another criterion already carries the condition
  it was pointing at.
- Name the artifact as it is named on disk, and state each condition once with
  no clause defending it. Both are [Cryptic writing](#cryptic-writing), which
  criteria attract more than any other field.
- Where an outcome cannot be achieved, the criterion is that the limitation is
  documented and formally accepted. That is a legitimate close, and it is how
  investigation work terminates.

Testing Approach names the observation, not the intent. What that means depends
on whether the story ships code.

**A story that ships code gets runnable example tests.** Name the input, the
command or action, and the expected result, specifically enough that someone
can execute it without asking a question. "Submit the form with a required field
blank and confirm the request is rejected with a field-level message" beats
"test error handling". Cover at least one failure case alongside the happy path.

**A story that ships no code gets a few sound validation criteria** - what the
artifact must contain for the outcome to be real. For a document, name the
contents that make it executable: the job, the parameter, the query, the index
of what is stored where. Nominating a person outside the work to prove it reads
as distrust on a board the client sees, so use it only where the stakes genuinely
warrant a second operator. For an investigation, it is the evidence that would
change the conclusion if it came out differently. Two to four is enough; padding
this section on a documentation story is filler.

Acceptance-criteria sections carry a hard cap: Definition of Done at seven,
Testing Approach at two, a feature's Acceptance Criteria at eight. Past those
nobody reads the list. Exceeding one means the item is too big, so split it
rather than extending the list.

## Repairing a mis-slotted block

The most common defect in a partially built board: real content pasted into a
block while the template skeleton above it was left in place, so an item shows an
unfilled `As a ({role} OR {team})...` line with several paragraphs of genuine
prose underneath, and an unfilled `Criterion 1 / Criterion n` skeleton above a
real criteria list.

The prose is the valuable part. Repair, in order:

1. Read the pasted prose in full. It is the author's actual intent.
2. Compose the user story sentence from it. The role and business case are
   almost always recoverable from the background paragraphs.
3. Convert activity lists into Development Approach checkbox steps, and keep the
   remaining prose beneath as context.
4. Move the real criteria list into the acceptance criteria, splitting any line
   carrying two conditions.
5. Derive VALIDATION from the criteria. This is almost always the field genuinely
   absent, because source prose states what must be true and rarely how it is
   observed.
6. Derive DEFINITION OF DONE from the team standard, not from the prose.
7. Delete only the empty skeleton placeholders. Never delete prose.
