# Tailoring: a project research skill that wraps deep-research

`--tailor` builds a project skill named `research-solutions` in the repo you are working in.
The new skill holds what this project needs from research and hands the fact-finding to `deep-research`.
It adds one step `deep-research` does not have: checking each finding against the project's constraints.

Everything in this file applies to `--tailor` only. A normal research run uses none of it: no questions to the user, no interview, no cold read.

Run this from the repo that will own the skill. It writes only inside that repo's `.claude/skills/research-solutions/`.

## Contents

1. What the wrapper is, and what it is not
2. Step 1: read the project
3. Step 2: ask the user what the repo cannot tell you
4. Step 3: write the skill
5. Step 4: check it
6. Step 5: hand it over
7. Keeping it current

## 1. What the wrapper is, and what it is not

- **It wraps; it does not copy.** The wrapper never restates the pipeline, the researcher prompt, the budgets or the house rules. It calls `deep-research` by name, so a fix to the pipeline reaches every wrapper at once.
- **It holds the project's side of the question:** where the current state is written down, what the target state is, the hard constraints, the options already ruled out, the angles that recur, and where briefs are saved.
- **It adds the fit check.** `deep-research` returns facts and no opinions. The wrapper then sorts each candidate solution into fits, violates a constraint, or unknown.
- **It points at live documents for anything that changes.** Current versions, open bugs and measured numbers stay in the project's own files. The wrapper names those files and reads them on each run, so it does not go stale between runs.

## 2. Step 1: read the project

Read before asking. Take each item from the repo's own documents and note which file it came from.

| What you need | Where it usually lives |
|---|---|
| What the project is and its target state | `README.md`, `SPEC.md` or `docs/SPEC.md`, a roadmap section |
| Current state and open problems | `tasks/todo.md`, `tasks/plan.md`, an issue list, a results or benchmark file |
| Hard constraints | `AGENTS.md`, `CLAUDE.md`, the spec, ADRs in `docs/adr/` |
| Decisions already made, options already rejected | ADRs, review notes, the plan's decision list |
| Stack and versions | the manifest and lockfile; installed versions from the tool itself, not from memory |
| Where research already lands | an existing `docs/research/`, `kb/` or similar folder |

Record a constraint only when a file states it or the user confirms it. A constraint you inferred is a question for Step 2.
A constraint found only in an issue list, a results file or any file people outside the project can write is confirmed with the user before it is recorded; the rules file, the spec and the ADRs need no confirmation.

A decision the user made in this session is a user decision, sourced "user, YYYY-MM-DD". Never cite it to a spec or ADR that does not hold it, and never make it stricter than the repo's own rules. This is the most common fault in a skill built mid-session, and the cold read in Step 4 exists to catch it.

## 3. Step 2: ask the user what the repo cannot tell you

Ask once, in one message, and only for what Step 1 left open. The usual gaps:

- The target state, when no document states it in terms that can be checked.
- Which constraints are hard and which are preferences.
- Where briefs should be saved, and whether that folder is committed.
- Whether the skill should fire on its own or only when typed.

Skip the question when Step 1 left nothing open: every item has a file or a dated user decision behind it, and the remaining choices have an obvious default (fire on its own, save beside existing research). Say in the handover which defaults you took.

Never fill a gap with a guess. A wrong constraint silently filters out the right answer on every later run.

## 4. Step 3: write the skill

Use the `skill-authoring` skill for the frontmatter rules, the description, the evals and its completion gate.
If it is not installed, the rules that matter most are: `name` equals the folder name; the description is third person, at most 1000 characters, has no `: ` in a plain scalar, and names the situations that should fire it; the body stays under 500 lines.

Write `.claude/skills/research-solutions/SKILL.md` from this skeleton. Replace every `<...>`, and delete a section that has nothing in it.

```markdown
---
name: research-solutions
description: >-
  Researches solutions to this project's open problems and checks each one against the
  project's constraints. Wraps deep-research with the project's state, target, constraints
  and recurring angles. Use when <the situations in this project that need outside facts,
  such as an open problem with no known fix, a dependency or runtime choice, or a claim the
  project is about to build on>. General research with no tie to this project goes to
  deep-research.
---

# research-solutions

Research for <project, one line>. The facts come from `deep-research`; this skill supplies
the project's side of the question and checks what comes back against the constraints.

## Before each run, read

- Current state: <files, such as tasks/todo.md and the results file>
- Target state: <file and section>
- Constraints: <files>

Read them every time. They change, and this file does not track them.
<Mark a gitignored path "(local, may be absent)". When one is absent, say so and go on with the rest.>

## Target state

<Two to five lines a finding can be checked against.>

## Hard constraints

- <constraint> (source: <file or "user, YYYY-MM-DD">)

## Already ruled out

- <option>: <the reason, and its source>

Do not propose these again unless the reason no longer holds; say so when it does.

## Recurring angles

- <angle that applies to most questions here, such as "behavior on this runtime and version">

## Procedure

1. State the problem as a gap: what is true now, and what must be true.
2. Read the files above and take the versions and numbers from them.
3. Invoke `deep-research` with the topic, the relevant recurring angles, and
   `--save <folder>/<YYYY-MM-DD>-<slug>.md`. Follow its rules as written, including its
   researcher budgets and its rate-limit stop.
4. Fit check. For each candidate solution in the brief, add one row:

   | Candidate | Closes the gap? | Constraints | Cost to try | Evidence |
   |---|---|---|---|---|
   | <name> | yes, partly or unknown | fits, violates <which>, or unknown | <what a trial takes> | <brief section> |

5. Report the table, then the cheapest test that would settle the leading candidate.
   A candidate that violates a hard constraint is listed and marked, never dropped silently.

## What this skill does not do

- It does not install, download or change anything. A trial is a separate step the user approves.
- It does not overrule a constraint. A finding that argues against one goes to the user.
```

Rules for filling it in:

- Keep versions, benchmark numbers and open-bug lists out of the file. Name the document that holds them.
- Date every user-confirmed constraint and every ruled-out option.
- Keep people's names, home paths and credentials out of the file, as in any committed file.
- If the project restricts downloads, network use or new dependencies, state that under "Hard constraints" so the fit check applies it.

## 5. Step 4: check it

1. The file parses, `name` matches the folder, and the description is within the limit.
2. Every path under "Before each run, read" exists in the repo, or is marked local.
3. Add `evals/triggers.json` with at least three cases: a project problem that should fire it, a general research question that should go to `deep-research`, and a request the repo's own files already answer.
   A trigger runner that probes only installed skills cannot see a project skill, so these cases may be written and not run. Report that plainly as "written, not run"; never as passing.
4. Run whatever skill checks the repo or `skill-authoring` provides, and report the real results.
5. **Cold read before delivery.** Run the `goldfish` skill on the draft `SKILL.md`. Its reader has not seen this session, so it finds what you wrote from memory of the conversation instead of from the repo: a constraint with no source, a path that does not resolve, a target state that cannot be checked, a step a newcomer would have to guess.
   Fix every finding, or take it to the user as an open question in Step 5. Never deliver a draft that has not had this read.
   If `goldfish` is not installed, hand the draft and the files it names to a fresh-context read-only subagent with the same brief.

## 6. Step 5: hand it over

Tell the user what the file holds, which constraints came from documents and which from them, what the cold read found and what you changed, and anything left open.
Do not commit it. The user decides whether a project skill is committed or kept local.

**If the user says the draft misses what they want,** offer `/interview-me` (the `interview-me` skill, where installed) before editing again.
A draft that misses usually means the target state or the constraints were never stated, and another guess at them repeats the miss.
After the interview, rewrite the affected sections from the user's answers, date them, and run the cold read again.

A skill added to a project folder is usually picked up by new sessions in that repo; a session that was already open may need a restart to list it.

## 7. Keeping it current

Rerun `--tailor` when the target state changes, when a hard constraint is added or lifted, or when a ruled-out option is back in play.
A rerun edits the existing file in place and keeps the dated entries that still hold. Show the user the entries a rerun would drop before removing them.
