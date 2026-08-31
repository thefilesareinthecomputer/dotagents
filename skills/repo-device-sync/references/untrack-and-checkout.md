# Why untracking plus checkout destroys files

Standing rationale behind the Phase 4 rule. Read once; the rule itself is in
`SKILL.md` and does not need this to be followed.

## The mechanism

`git rm --cached` is safe on its own. **Committing it and then checking out
another branch is not.** The checkout restores those files, because the other
branch still tracks them, and the fast-forward back onto the untracking commit
then deletes them from the working tree.

Newly ignored files never appear in `git status`, so nothing warns and nothing
shows as a pending change. The directory is simply empty the next time anyone
looks.

## What it cost

This destroyed 28 files during a routine untrack-and-sync: ten certifications and
eighteen dated research artifacts. They were recovered only because the prior
commit still held them. Files untracked and deleted the same way that had never
been committed are gone outright.

## Verifying, when HEAD deletes paths the target branch still tracks

Advance the other branch by refspec rather than checking it out, and **verify by
counting files on disk, not by reading plain `git status`**. Ignored files are
hidden in its default mode, which is exactly why the loss goes unnoticed;
`git status --ignored` does show them. Count recursively, because `ls <dir>/*`
neither recurses into subfolders nor excludes directories:

```bash
find <dir> -type f | wc -l                                  # before and after
git ls-files --others --ignored --exclude-standard <dir>    # the at-risk set
```

## Recovery

```bash
git restore --source=<prior-commit> --worktree -- <paths>
```

restores the working tree without re-staging. Prove it with a per-file hash
compare against `git show <commit>:<path>`, because `git diff <commit> -- <path>`
reports ignored files as deleted and makes a complete restore look like total
loss.

## The general shape

A destructive git operation is not finished when the command exits. Untracking,
checkout and merge interact, and the damage lands one step after the command that
caused it.
