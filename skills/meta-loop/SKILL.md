---
name: meta-loop
description: Orchestration loop - plan, delegate to parallel workers, verify, synthesize - with a premium advisor consulted off the hot path. The session model orchestrates, fan-out runs as Agent calls against two pinned subagents (`reader` for read-only gathering, `worker` for anything that changes the tree), and the advisor agent is pulled in for decomposition critique, risk, and taste. MUST be used whenever the user asks to run something as a loop, orchestrate, fan out, or delegate to workers, whenever a requested task visibly splits into three or more independent subtasks, and for any mid-loop situation - verifying a worker's result against its claims, re-delegating a rejected subtask, or critiquing a decomposition. Also on "/meta-loop". Not for single-step tasks.
---

# meta-loop

Three-tier loop: **orchestrator** (this session) runs the hot path
plan → delegate → verify → synthesize; **workers** (`reader` on sonnet,
`worker` on opus) do parallel execution; **advisor** (fable, fresh context)
is a consulted advisor off the
hot path. The economics: parallelism is the leverage, not a cheaper worker. A
worker runs on the same tier the orchestrator would have used doing the work
itself, so fanning out costs wall-clock and context - never quality. The saving
is structural rather than per-token: no single agent fills a context window, so
several shorter threads cost less in aggregate than one long thread that maxes
out and compacts repeatedly.

Session-model note: a skill cannot set the main-thread model. Run the session
on Opus (`/model opus`) so the orchestrator matches its writers; on a Fable
session the loop still works - the advisor then buys a fresh, unanchored
context rather than a model upgrade. Worker tier never follows the session:
`reader` and `worker` pin their own models in frontmatter, because an agent
with no pin inherits the session model, which silently downgrades a fan-out on
a cheap session and silently runs it on the priciest tier on an expensive one.

## Phase 1 - Plan (orchestrator)

Write the plan before spawning anything: subtasks, each with a concrete
deliverable and acceptance criteria the orchestrator can check from evidence
(diff, test output, file list - not the worker's own say-so). Mark which
subtasks are independent (parallel) and which chain. If fewer than ~3
independent subtasks fall out, stop - do the work directly; the loop is
overhead, not leverage.

Where the goal is too vague to write acceptance criteria against, clarify it before planning rather than handing the same ambiguity to five workers at once.
`interview-me` is the tool when the gap is in the ask itself.

**A loop that will outlive this session writes its plan to a file.**
In a repo following this one's docs lifecycle that file is the goal's own `tasks/SPEC-<NAME>.md`, already the source of truth for what remains, with `tasks/todo.md` carrying the one-line handoff naming the loop and the next action.
Anywhere else, use the repo's own planning doc, or create one working file and name its path in the plan.
Each entry carries state, deliverable, acceptance criteria and an evidence pointer, so a later session - or the other station - can read what this one meant:

    - [ ] S3 - regenerate the adapter fixtures
      deliverable: tests/fixtures/adapters/*.json rewritten from the live schema
      acceptance: `pytest tests/test_adapters.py` green, no fixture older than the schema
      evidence: -

Three rules keep that file trustworthy.
Only the orchestrator writes it; workers return evidence and never touch it, which is what keeps two writers off one document.
On resume, fetch origin before reading it.
Then re-verify every ticked subtask against its recorded evidence before continuing, because a ticked box is a claim and the file is git-tracked on more than one station.
When the loop finishes, the file leaves the working set by the repo's normal archival route.

**An existing backlog is an input, never an output.**
Where a board, backlog or spec already covers the goal, decompose from it instead of inventing a parallel list; the loop never writes one.
Read it and never write back to it - its IDs may exist on a tracker outside this repo, and a loop is not entitled to change them.
State entries name the item IDs they cover and carry their own acceptance and evidence, never a copy of the item body, which is what stops the two files drifting about what the work is.
An item is not automatically a subtask: backlog items are sized for one person over a day or two, so some split, some group, and some sequence rather than run in parallel - two items under one parent routinely touch the same files.
Record that mapping against the IDs so a resuming session can see why five items became three subtasks.

## Phase 2 - Advisor consult (on demand, pre-delegation)

Spawn the `advisor` agent with the plan and one specific question
(default: "critique this decomposition - seams, ordering, risk").
Apply the verdict - proceed / revise / stop - before any worker starts.

**The advisor is available, and it is the expensive tier.** It runs on
`fable`, the priciest model in the loop; it is a scalpel, not a habit.

- **Consult when:** subtasks touch shared files or a common interface; any
  step is irreversible (migrations, deletions, published output); the
  decomposition itself is uncertain and a wrong split would waste the whole
  fan-out; the user asked for it. When one of those holds, do not skip it to
  save tokens - that is exactly the call the advisor pays for.
- **Skip when:** the fan-out is routine, the seams are obvious, and a bad
  plan would be cheap to redo. Most loops need zero or one consult.
- **Budget:** typically 0–2 advisor calls per loop - one at plan time, at
  most one taste/escalation pass later. Never one advisor call per subtask,
  never as a substitute for the orchestrator's own verification (Phase 4),
  and never to review work that already passed its acceptance criteria. If a
  loop is reaching for a third consult, the plan is the problem - stop and
  re-plan rather than buying more opinions.

## Phase 3 - Delegate (workers, parallel)

- One `Agent` call per subtask, in a single message so they run concurrently;
  background by default.
- **Check the roster before spawning a generic worker.** `agents/` is the list
  of record; read it if this is stale. It currently holds:
  - `reader` - read-only gathering and tracing (sonnet)
  - `worker` - anything that changes the tree (opus)
  - `researcher` - source-cited research on one bounded angle, capsule return
  - `advisor` - strategy, decomposition, risk and taste, off the hot path
  - `supervisor` - watches in-flight work for drift; pushed, not pulled
  - `my-security-reviewer` - the agent-tooling security checklist
  - `ai-engineer` - AI and agent builds

  A specialized definition carries a purpose-built prompt plus its own pinned
  tools and model, none of which a generic worker prompt can reconstruct. So
  `reader`/`worker` are the fallback when nothing fits, not the default.
- **Writing a new subagent is allowed, and it is the last option.** If no
  existing definition meets the subtask's requirements, author one per
  `skill-authoring` rather than papering over the gap with a longer prompt.
  Name which existing agents you rejected and why before doing it: a definition
  is a durable addition to the repo, not a throwaway for one loop.
- **The tier comes from the definition, not the call.** `reader` is pinned to
  sonnet and `worker` to opus, so a fan-out cannot silently inherit whatever
  model the session happens to be running. Gathering facts against a cited
  source is well-specified work the orchestrator verifies anyway; changing the
  tree is not, and a writer's output is only as trustworthy as the model that
  wrote it. A weak writer does not save money - it moves the cost into
  re-delegation, missed edge cases, and defects the verify step may not catch.
- **Override per call only with a reason, stated in the plan.** A call-site
  `model` beats the frontmatter. Raise a reader to opus when the question needs
  real judgment rather than retrieval (tracing intent across a subsystem,
  reconciling sources that disagree). Drop a writer to sonnet only when the
  subtask is mechanical and fully specified, trivially reversible, and
  machine-checkable - a rename sweep, a formatting pass. Never re-tier a whole
  fan-out at once.
- Each worker prompt is self-contained: context, exact deliverable,
  acceptance criteria, what NOT to touch.
- **A worker prompt carries task content only.** It is an input to a fresh
  context, not a message to a colleague. Cut the session narrative ("we just
  finished X", "the user then asked"), the justification for why the task
  exists, apologies, encouragement, and any commentary about the loop itself.
  A worker that has to read past framing to find its instructions has been
  handed a worse prompt. Include a fact only if the worker's output changes
  without it.
- **Both directions are asymmetric on purpose:** be exhaustive in the searching
  and the doing, ruthless in what crosses a context boundary. That applies to
  the prompt going out and the findings coming back.
- **Pick the subagent by what the subtask does**, via `subagent_type`. The
  allowlist lives in the definition and the harness enforces it, which is why
  this is not left to the prompt:
  - **`reader`** (`tools: Read, Grep, Glob`) for anything that only needs to
    find things. It *cannot* write, whatever its prompt says. Parallelize
    readers freely over the same paths - they share no state, and the point is
    that the searching stays in their context while only the conclusion comes
    back. This is where the loop's context saving actually comes from.
  - **`worker`** (adds `Write`, `Edit`, `Bash`) for anything that changes the
    tree. Two workers must not write the same file - that seam belongs to the
    orchestrator or to sequencing, and no allowlist can express it.
  - Neither can spawn agents, so a fan-out stays one level deep by
    construction rather than by instruction.
- A loop that needs only one kind uses only one kind. Reading first and
  writing second is a common and useful shape, not a required one.

## Phase 4 - Verify (orchestrator)

Check each result against its acceptance criteria using evidence, not the
worker's summary. Reject → re-delegate once with tightened criteria and the
specific failure named. Second failure, or a failure that is ambiguous about
whose fault it is (plan vs worker) → escalate to the advisor with the
transcript evidence. Never synthesize an unverified claim.

## Phase 5 - Synthesize (orchestrator)

One coherent deliverable in the final message - resolved, deduplicated,
in-voice - not a concatenation of worker reports. For user-facing or
high-stakes output, an optional advisor taste pass before shipping - within
the Phase 2 budget, not on top of it.

## When NOT to use

Single-file edits, single-step tasks, tasks under ~3 independent subtasks,
or anything where reading the fan-out reports would cost more than doing the
work. The loop pays for itself only when workers run in parallel.

## Boundaries

**A loop is a mid-session primitive, not a session lifecycle.**
A loop finishing is not a session ending.
Session closeout - reflect, notes, commit, sync, push - belongs to `wrap-up`, which triggers on session scope and is invoked by the user.
The loop never starts it, and high context mid-loop is a signal to finish the current subtask rather than to close the session.

**The loop does not replace the build cadence.**
Where a subtask changes code it is still delivered in thin verified slices against its acceptance criteria.
`spec`, `plan`, `build`, `test`, `review` and `ship` are user-invoked and route on their own descriptions; the loop governs how work is split and verified, not how a slice is written.

**Delegation does not lower the evidence bar.**
Phase 4 is the loop's gate, not a substitute for the review the change would have needed had one agent written it.

## Related tooling

`advisor` agent (this skill's off-path judgment and counsel),
`supervisor` agent via cover-me (in-flight watcher, push not pull).
