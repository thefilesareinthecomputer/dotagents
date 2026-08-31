---
name: repo-device-sync
description: Multi-device git sync ritual for repos worked on from several machines, sometimes concurrently. Fetches and diffs origin before work starts, reconciles inbound commits from other devices, re-fetches immediately before every push, and verifies branch parity afterward. Divergence is a stop-and-ask condition - never force-push, rebase shared history, or hard reset. Commits default to ONE per session and verify the staged set first, because `git commit` writes the whole index rather than the paths just added. MUST be used for ANY commit, push, or pull intent in such a repo, however casually phrased ("ok push this up", "ship it", "just commit it all") - the ritual is the point, not the git command.
---

# repo-device-sync

Keeps one repo consistent across devices that may commit concurrently. Prevents
starting on stale state, or pushing over a commit another machine landed
mid-session. **Fetch before trusting anything, diff before pulling, re-fetch
before pushing, verify after.**

## Phase 1 - Assess (always first)

```bash
git status --porcelain      # uncommitted local work?
git fetch origin            # never reason about origin without this
git status -sb              # ahead/behind for current branch
git branch -vv              # ahead/behind for all tracked branches
```

Report per branch: in sync / ahead N / behind N / diverged. Surface uncommitted
changes first - they change what is safe below.

## Phase 2 - Reconcile inbound (behind)

1. Show what is coming: `git log --oneline HEAD..origin/<branch>` plus
   `git diff HEAD...origin/<branch> --stat`.
2. **Deletion pre-flight.** A commit that untracked newly-ignored paths arrives as
   a working-tree deletion, and those paths are then ignored, so the loss leaves
   no trace where default views look. Locally modified files make the pull refuse
   loudly; unmodified ones go quietly, and quiet is the dangerous case.

   ```bash
   git diff --name-status HEAD origin/<branch> \
     | awk '$1=="D"{print $2}' | git check-ignore --stdin
   ```

   Any output: stop, show the list, ask. **Run this same check against both sides
   of a merge in Phase 3 and against the staged set in Phase 3.5** - one check at
   three moments.
3. Clean fast-forward (no divergence, no conflicting uncommitted files, clear
   pre-flight): `git pull --ff-only`, without asking. That is the ritual working,
   and it is the reversible direction.
4. Uncommitted changes overlapping the incoming diff: stop, show the collision,
   ask (stash / commit / abort).

## Phase 3 - Diverged (stop-and-ask)

Both machines committed. Never resolve it silently.

1. Show both sides: `git log --oneline origin/<branch>..HEAD` and
   `git log --oneline HEAD..origin/<branch>`, plus stat diffs.
2. Propose a strategy - normally `git pull --no-rebase`; flag files touched on
   both sides and run the Phase 2 pre-flight against both. Change no history until
   the user chooses.
3. **Hard rules:** no `push --force` or `--force-with-lease`, no rebasing pushed
   commits, no `reset --hard`, no stash-drop, no `git clean -f`, no branch
   deletion, no `checkout --`/`restore` over uncommitted work. History rewrites
   and discarded work are the user's call, made explicitly.

## Phase 3.5 - Commit

**One commit by default.** Splitting is where commits get mixed up, and a tidy
history is worth less than a correct one.

**`git commit` writes the ENTIRE index, not the paths you just staged.** Anything
staged earlier - a `git mv`, an abandoned `git add` - rides along under a message
that does not describe it. So, every time:

```bash
git diff --cached --name-only     # EXACTLY what the message describes?
```

If not, unstage what does not belong (`git restore --staged <path>`) rather than
writing the message around it. For separate commits use the pathspec form, which
ignores the rest of the index:

```bash
git commit -m "..." -- path/one path/two
```

Never chain `git add A B C && git commit` and assume the commit equals A B C.

**An untrack commit is a distributed deletion.** When the staged set holds
D-status paths that are now gitignored, this commit deletes them from every other
clone on its next pull:

```bash
git diff --cached --name-status \
  | awk '$1=="D"{print $2}' | git check-ignore --stdin
```

Any output: tell the user which paths and that other machines lose them, and
confirm first. `git rm --cached` reads as local and index-only, which is exactly
why this needs saying out loud.

## Phase 4 - Outbound

1. **Re-fetch immediately before pushing.** Phase 1's fetch is stale. If origin
   moved, loop back to Phase 2 or 3.
2. Push, then verify: `git fetch origin && git status -sb` shows in-sync.
3. **Branch parity.** Where a repo keeps two branches equal (`develop == main`),
   advance the trailing one **by refspec, never by checkout**:

   ```bash
   git log --oneline origin/develop..develop   # MUST be empty
   git push origin main:develop                # advances origin, no checkout
   git fetch origin develop:develop            # advances the local ref
   ```

   Both refuse a non-fast-forward rather than forcing one, and `fetch <src>:<dst>`
   also refuses while `dst` is checked out anywhere (git 2.35+). **That refusal is
   the safety property - never reach for `git branch -f` or `push --force` to get
   past it.**

   Read the rejection before routing it: *non-fast-forward* means the trailing
   branch has its own commits, which is Phase 3. Anything else - pre-receive hook,
   protected branch, permissions - is policy, not divergence: surface it verbatim
   and stop.

   Confirm all four refs match:
   `git rev-parse develop main origin/develop origin/main`.

### Never check out across a commit that deletes tracked files

The checkout restores them (the other branch still tracks them) and the
fast-forward back then deletes them - silently, since newly ignored files never
appear in `git status`. This destroyed 28 files in one routine untrack-and-sync.

Whenever HEAD deletes paths the target branch still tracks: advance by refspec,
and **verify by counting files on disk** (`find <dir> -type f | wc -l`), never by
reading plain `git status`.
[references/untrack-and-checkout.md](references/untrack-and-checkout.md) has the
mechanism, the at-risk query and the recovery.

## Report

A compact table: branch → state found → action taken → final state. One line for
uncommitted work.

## Not this

General git questions, and in-repo branch work that never touches origin. Phase
3.5 still applies in a single-device repo; the origin-facing phases do not.
Checking a station against `specs/claude-code/` is `agent-cc-configs-sync`.
