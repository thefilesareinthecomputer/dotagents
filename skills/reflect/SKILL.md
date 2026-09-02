---
name: reflect
description: End-of-session truth reconciliation. MUST be used when the user types /reflect, says "reflect", "reconcile", or "let's reconcile" - the sweep is a defined procedure with a user-approval gate, not an ad-hoc summary. Sweeps the session for anything newly learned, discovered, chosen, decided, or discussed that (a) should become permanent memory, or (b) invalidated an existing stated claim in any docs, comments, configs, or memory - then correct those so everything lines up with current truth. Distinct from /notes (the docs sweep) - reflect promotes durable knowledge to memory and fixes stale claims, then hands off to /notes. A whole-session closeout that also commits and pushes is /wrap-up, which runs this skill first.
---

# Reflect - session truth reconciliation

Two questions about what the session surfaced:

1. **Durable knowledge that should outlive the session?** → permanent memory.
2. **Did anything invalidate something already written as true?** → correct it.

**`notes` owns the six doc paths; reflect does not touch them.** Reflect handles
memory, code comments and configs, then hands doc corrections over.

**Reflect proposes, the user approves, then reflect applies.** Nothing is written
off its own conclusions.

## Step 1 - Reconstruct

List what is now **true or known** that was not before - not what you did, which
is `notes`:

- **Learned** - non-obvious facts about the code, tools, environment, or intent.
- **Decided** - choices and the *why*.
- **Discussed** - preferences and corrections on how you should work.
- **Changed** - anything making a previously-true statement false.

Pull from the conversation and the tree. **Do not invent insight that was not
there.** Nothing durable and nothing contradicted: say so, skip to step 5.

## Step 2 - Compile proposals (no writes)

### A. Durable knowledge

**The default is not to write a memory.** Every description loads into every
future session; a long index gets skimmed instead of read. Four tests, all
required:

1. **Would a future session get this wrong without it?** Not "is it interesting".
2. **Is it durable?** True next month. Work in flight belongs in `todo.md`.
3. **Is it non-derivable?** Not recoverable from code, tests, git history,
   `AGENTS.md`, `README.md` or a skill body - those already load.
4. **Does no existing memory cover it?** Grep first. **Extending an existing file
   beats creating a neighbor** - two entries on one subject split recall.

Most session learnings fail at least one. A session that writes no memory is
normal.

**Route before proposing.** `memory-routing.sh` fires on every write and
`memory_lint.py` fails one lacking a `MEMORY.md` pointer or valid frontmatter.
Only a belief specific to THIS repo becomes a memory: universal principles go to
global `~/.claude/CLAUDE.md`, invariants to a hook, procedures to a skill, and
client/project facts to that project's own docs - never here, since a copy has no
staleness detection and will silently contradict its source.

Draft per the memory rules in `~/.claude/CLAUDE.md`, already loaded and not
restated here.

### B. Stale claims

One grep for the old name/value finds every site. **Your scope is everything
`notes` does not own:**

- **Memory** files that now contradict the truth.
- **Code comments** describing behavior the session altered.
- **Configs** encoding a stale assumption - renamed path, dropped flag, changed
  default.
- **Every other in-repo doc**: skill bodies, `references/`, `specs/`, `AGENTS.md`,
  secondary specs. Notes explicitly disclaims these, so if you do not correct
  them nothing does - and they are the largest doc surface in a skills repo.

**Only the six paths go to `notes`** - `SPEC.md`, `README.md`, `tasks/plan.md`,
`tasks/todo.md`, `tasks/SPEC-*.md` and `tasks/completed/`. A hit in one of those
is handed over as a report line, never proposed as an edit: two skills correcting
one file is how a sweep takes half an hour and lands contradictory wording.

Capture `file:line`, old text, proposed new text. A plan, not edits. **The
proposed text is shorter or equal**: a stale claim is deleted or rewritten in
place, never annotated with an update note, and a rule the session exposed as
missing is first sought as a sharper wording of a rule already there.

### C. Prune the index - every sweep

```bash
cd ~/.claude/projects/<slug>/memory && ls *.md | grep -vc '^MEMORY.md$'
```

| Count | Rule |
|---|---|
| under 25 | Propose a removal when you see one. |
| 25+ | **MUST consider a trade** per addition; if you propose none, say what you considered. |
| 50+ | **Every addition is paired with at least one removal or merge.** If nothing is stale enough to trade, the addition has not cleared the bar in A - drop it. |

**Start at the oldest, but age is not the criterion** - it is the cheapest place
to begin: `ls -t *.md | tail -15`. Look for **superseded** entries (delete, do not
hedge-rewrite), **near-duplicates** (merge into the better one), **expired
scaffolding** (shipped work, fixed bugs, retired tools - these read as permanent
because nothing dates them), and **never-recalled trivia** (if you cannot name a
situation where it changes what you do, it is not earning its line).

**A sweep that adds without proposing a removal says why.**

## Step 3 - Play it back (gate)

Present the complete slate, grouped and skimmable, then **stop and wait**:

- **What I now believe is true** - each fact, where it came from, the file it
  creates or updates, which of the four tests it passed. For an update, why that
  beat a new file.
- **What went stale** - `file:line` → old → proposed new.
- **Removals and merges** - with why, and the index count before and after. An
  empty list needs a sentence saying you looked.

Apply **only** what is approved; carry wording changes through verbatim.

## Step 4 - Apply

Memory files plus `MEMORY.md` pointers. Surgical edits elsewhere - read before
edit, preserve surrounding voice. Where an approved fix is bigger than a surgical
correction, do what was agreed and flag the rest.

**Verify the index before reporting.** An unpointered memory is dead weight:

```bash
cd ~/.claude/projects/<slug>/memory
for f in *.md; do [ "$f" = MEMORY.md ] || grep -q "($f)" MEMORY.md || echo "ORPHAN: $f"; done
```

Fix any `ORPHAN` here. **Do not run `memory_lint.py` bare** - it is a PostToolUse
hook reading stdin and will block until timeout. Its verdict is already in the
write results above; the loop is the independent check.

## Step 5 - Hand off to /notes

If the session produced work belonging in the living docs, say `/notes` looks
warranted and **ask** whether to run it now - do not auto-run. Hand over your
reconstruction and any doc corrections your grep found, so notes redoes neither.

## Step 6 - Report

**Applied** (memory created/updated/deleted, stale claims corrected with
`file:line`), **dropped** (declined or amended), **deferred**, and **next** (the
`/notes` tickle and the user's choice).

## Guardrails

- **Non-destructive.** Read before edit; merge, never gut. `__archive/` for
  soft-deleting user content. Memory files are deleted only when wrong or
  superseded, and only with approval.
- **Don't name the user** in any memory, doc, comment or config.
- **Validate before concluding.** Grep before asserting; never bluff a
  reconciliation you have not confirmed.
- Does not commit or push unless asked.
