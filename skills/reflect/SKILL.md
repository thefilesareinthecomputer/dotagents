---
name: reflect
description: End-of-session memory reconciliation. MUST be used when the user types /reflect, says "reflect", "reconcile", or "let's reconcile" - the sweep is a defined procedure with a user-approval gate, not an ad-hoc summary. Sweeps the session for anything newly learned, discovered, chosen, decided, or discussed that should become permanent memory, corrects or removes memories the session made stale, and prunes the memory index. Memory only - stale claims in the repo's own docs, skills, comments and configs belong to /notes. A whole-session closeout that also commits and pushes is /wrap-up, which runs this skill last.
---

# Reflect - session memory reconciliation

Two questions about what the session surfaced:

1. **Durable knowledge that should outlive the session?** → permanent memory.
2. **Did anything invalidate something memory holds as true?** → correct it.

**Reflect owns memory; `notes` owns every file in the repo.** A stale claim
spotted in the repo - a doc, a skill body, a code comment, a config - is handed
to notes as a report line, never edited here.

**Reflect proposes, the user approves, then reflect applies.** Nothing is written
off its own conclusions.

## Step 1 - Reconstruct

List what is now **true or known** that was not before - not what you did, which
is `notes`:

- **Learned** - non-obvious facts about the code, tools, environment, or intent.
- **Decided** - choices and the *why*.
- **Discussed** - preferences and corrections on how you should work.
- **Changed** - anything making a previously-true statement false.

Pull from the conversation and the tree; if wrap-up or notes already
reconstructed the session, start from that. **Do not invent insight that was
not there.** Nothing durable and nothing contradicted: say so, skip to step 5.

## Step 2 - Compile proposals (no writes)

### A. Durable knowledge

**The default is not to write a memory.** Every description loads into every
future session; a long index gets skimmed instead of read. Five tests, all
required:

1. **Would a future session get this wrong without it?** Not "is it interesting".
2. **Would the mistake cost more than one declined proposal?** A fact whose
   whole value is sparing the user one "no" is not a memory. The user ruling
   on something sessions rarely touch (a dead repo, a one-off cleanup, a
   station's leftovers) fails here even when tests 1, 3 and 4 pass.
3. **Is it durable?** True next month. Work in flight belongs in `todo.md`.
4. **Is it non-derivable?** Not recoverable from code, tests, git history,
   `AGENTS.md`, `README.md`, a skill body or the session record - those already
   load, or are one grep away when the subject comes up.
5. **Does no existing memory cover it?** Grep first. **Extending an existing file
   beats creating a neighbor** - two entries on one subject split recall.

Most session learnings fail at least one. A session that writes no memory is
normal, and a slate of one is more often right than a slate of three: when
the third item is the weakest, drop it before presenting rather than letting
the user do the pruning.

**Route before proposing.** `memory-routing.sh` fires on every write and
`memory_lint.py` fails one lacking a `MEMORY.md` pointer or valid frontmatter.
Only a belief specific to THIS repo becomes a memory: universal principles go to
global `~/.claude/CLAUDE.md`, invariants to a hook, procedures to a skill, and
client/project facts to that project's own docs - never here, since a copy has no
staleness detection and will silently contradict its source.

Draft per the memory rules in `~/.claude/CLAUDE.md`, already loaded and not
restated here.

### B. Stale memory

One grep of the memory folder for the old name/value finds every memory that
now contradicts the truth. A hit inside the repo goes to `notes` as a report
line, never proposed as an edit here: two skills correcting one file is how a
sweep takes half an hour and lands contradictory wording.

Capture `file:line`, old text, proposed new text. A plan, not edits. **The
proposed text is shorter or equal**: a stale claim is deleted or rewritten in
place, never annotated with an update note, and a rule the session exposed as
missing is first sought as a sharper wording of a rule already there.

### C. Prune the index - every sweep

```bash
cd ~/.claude/projects/<slug>/memory && ls *.md | grep -vc '^MEMORY.md$'
```

The tiers match the ones `memory-routing.sh` enforces on every new memory file:

| Count after the addition | Rule |
|---|---|
| under 50 | Propose a removal when you see one. |
| 50-74 | **MUST consider a trade** per addition; if you propose none, say what you considered. |
| 75-100 | **Every addition is paired with at least one removal or merge.** If nothing is stale enough to trade, the addition has not cleared the bar in A - drop it. |
| 101+ | The hook blocks new files. Propose removals that bring the folder under the cap before any addition. |

**Start at the oldest, but age is not the criterion** - it is the cheapest place
to begin: `ls -t *.md | tail -15`. Look for **superseded** entries (delete, do not
hedge-rewrite), **near-duplicates** (merge into the better one), **expired
scaffolding** (shipped work, fixed bugs, retired tools - these read as permanent
because nothing dates them), **never-recalled trivia** (if you cannot name a
situation where it changes what you do, it is not earning its line), and **rules
in disguise** - a corrective or prohibitive memory ("never", "always") applied in
most sessions. Check the hooks first: one that already enforces it makes the
memory redundant. Otherwise propose moving it to a path-scoped rule in
`.claude/rules/` if it governs a set of files, or to a hook if a script can check
it.

**Islands** - memories nothing links to - are candidates, not defects:

```bash
for f in *.md; do s="${f%.md}"; [ "$f" = MEMORY.md ] || grep -qE "\[\[$s([|#]|\]\])" $(ls *.md | grep -vxF "$f") || echo "NO-INBOUND: $f"; done
```

Link each from the memory it extends with `[[name]]`, merge it, or leave it when
it genuinely stands alone.

**The index is the highest-leverage text in memory** - it is the only part loaded
every session, and recall depends on it. Each `MEMORY.md` line says what the
memory holds and when to open it, under 220 characters, matching the file's
`description`: "No framing openers in chat" is a title; "No framing openers in
chat - start with the first finding; applies to every reply" is an index line.
Past 50 entries, propose a few section headers grouping related memories.

**A sweep that adds without proposing a removal says why.**

## Step 3 - Play it back (gate)

Present the complete slate, grouped and skimmable, then **stop and wait**:

- **What I now believe is true** - each fact, where it came from, the file it
  creates or updates, which of the five tests it passed. For an update, why that
  beat a new file.
- **What went stale** - `file:line` → old → proposed new.
- **Removals and merges** - with why, and the index count before and after. An
  empty list needs a sentence saying you looked.

Apply **only** what is approved; carry wording changes through verbatim.

## Step 4 - Apply

Memory files plus `MEMORY.md` pointers - read before edit, preserve surrounding
voice. Where an approved fix is bigger than a surgical correction, do what was
agreed and flag the rest.

**Before deleting a removed or merged memory, repoint its inbound links** - this
step is the only one that knows the removal happened:

```bash
for s in <removed-or-merged-stems>; do grep -lE "\[\[$s([|#]|\]\])" *.md; done
```

Each hit links to the survivor instead, or drops the link.

**Verify the index before reporting.** An unpointered memory is dead weight:

```bash
cd ~/.claude/projects/<slug>/memory
for f in *.md; do [ "$f" = MEMORY.md ] || grep -q "($f)" MEMORY.md || echo "ORPHAN: $f"; done
```

Fix any `ORPHAN` here. **Do not run `memory_lint.py` bare** - it is a PostToolUse
hook reading stdin and will block until timeout. Its verdict is already in the
write results above; the loop is the independent check.

## Step 5 - Hand off to /notes

If the session produced work belonging in the living docs, or step 2 spotted a
stale claim in the repo, say `/notes` looks warranted and **ask** whether to run
it now - do not auto-run. Hand over your reconstruction and those report lines,
so notes redoes neither. Under wrap-up notes has already run and the commit is
pushed, so the report lines go in the closeout report as follow-up work.

## Step 6 - Report

**Applied** (memory created/updated/deleted, stale memory corrected with
`file:line`), **dropped** (declined or amended), **deferred**, and **next** (the
`/notes` tickle and the user's choice).

## Guardrails

- **Non-destructive.** Read before edit; merge, never gut. `__archive/` for
  soft-deleting user content. Memory files are deleted only when wrong or
  superseded, and only with approval.
- **Don't name the user** in any memory.
- **Validate before concluding.** Grep before asserting; never bluff a
  reconciliation you have not confirmed.
- Does not commit or push unless asked.
