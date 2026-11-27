---
name: wrap-up
description: Close a session cleanly so the next one starts strong - review the session's files, bring the docs and the handoff up to date, commit and push on the right branch, then write memory. MUST be used when the user closes out a SESSION, however phrased - wrap up, end the session, close it out, that is everything for today - and whenever they name three or more of security review, inbox, reflect, notes, commit, sync and push together. Session scope is the discriminator - wrapping up a task, a feature or a bug is not this, a mid-session save is not this, and a single verb alone belongs to its own skill. Also on /wrap-up.
---

# wrap-up

When this ends, the session's files are reviewed, every claim in the repo is true, the tree is committed and pushed on the right branch, memory holds what was learned, and `tasks/todo.md` holds everything the next session needs. Nothing it needs is left only in this conversation.

Work the user asked for is finished before wrap-up starts, not handed to the next session. `todo.md` lists only work outside this session's ask; an in-scope leftover is either finished now or named to the user as unfinished, never filed as a next step.

This skill owns the order and the one approval stop. Each sub-skill and agent owns its procedure: `my-security-reviewer` owns the review, `notes` the repo's text, `repo-device-sync` git, and `reflect` memory. Where one is not installed, its step is done by hand and the report says so.

**One stop for the user.** A sub-skill's approval gate does not stop the closeout on its own. Its proposals are held and asked together in step 6. Markdown prose corrections to claims this session's own changes made false are applied without asking and listed in the report; config, script and hook corrections go to step 6.

## It runs once per session - never loop

The review runs once, at the end. Its findings get fixed or dismissed, and then it is over:

- Never send the fixes back for another review.
- Never start wrap-up again because the fixes changed files.
- Never treat a reviewer's or curator's suggestion as new work that needs another pass.

Fix, close, commit, push, end. `review_gate.py` holds this for you. `close` (step 5) records the tree once every finding is settled. A review run earlier in the session, before a push, counts as this review: it is closed the same way, so the check scopes wrap-up to what changed after it. `check` (step 1) compares the tree with that record:

- **PASS:** nothing changed since the review closed. Skip steps 2 and 5. Commit what is uncommitted, or report and end.
- **REVIEW:** it lists the files changed since the close. Those files are the only scope. A small follow-up (a typo, a doc line, a fix from the review) is an ordinary commit with no review. Review again only when the list shows major edits to other files, or new files, made after the push. That is rare. Then tell the user the session has run past its closeout, and suggest `/clear` or a new session for further work.

## 1. Assess

```bash
git status --porcelain && git fetch origin && git status -sb && git branch -vv
python3 "<skill-dir>/scripts/review_gate.py" check   # PASS: the review already ran on this tree
```

Stop if there is nothing to wrap up, if the tree holds changes this session did not make (ask before staging them), or if the branch has diverged (run `repo-device-sync` Phase 3 first).

## 2. Review, in the background

List the session's files from `git status --porcelain` and the unpushed range (a new skill counts as its whole folder), sweep them, and fix each FAIL. A false positive (a stand-in value, or a line the session did not change) is named in the report with its reason instead; never rerun the sweep hoping for clean.

```bash
python3 "<skill-dir>/scripts/closeout_lint.py" <files>   # exit 1 on FAIL
```

Run the session's tests once, scoped to what changed; never a whole-repo sweep. The script maps each changed file to the one suite or test that covers it, runs them on the Python 3.9 floor (`--both` adds the newest), skips any check that already passed on the same content, and exits 1 on a failure. After a fix, rerun it with `--files` naming only the fixed files.

```bash
python3 "<skill-dir>/scripts/affected_tests.py"            # --list to see the plan first
```

Run the resource check beside it.
- The spawn lint covers the session's files. A finding is fixed like a FAIL.
- The reaper reports heavy processes left running with no owner. A finding goes in the report and to the user; nothing is stopped without their yes.

```bash
python3 "<skill-dir>/../skill-authoring/scripts/check_spawns.py" <files>   # exit 1 on a finding
timeout 30 python3 ~/.claude/hooks/reaper.py --report                       # skip if the hook is not installed
```

Spawn `my-security-reviewer` with the file list and the sweep's FAIL and WARN lines in the prompt, each with what you already ruled on it; it reads the diff from git itself. Pass `model: sonnet` unless the list holds executable surface (scripts, hooks, settings, a new skill) or a claim about the outside world (a package, endpoint, version). Skip the review only when the list is under ten prose files, none under `skills/`, `specs/`, `agents/`, `commands/` or `app/`, and the sweep is clean.

Spawn `curator` alongside it only when the user asks for a presentation pass, over the changed reader-facing files that `notes` does not write: skill bodies, references, agent and command files, and published docs. Its scope never includes frontmatter, `README.md`, `SPEC.md` or `tasks/`.

Do steps 3 and 4 while the agents work, and never poll or re-spawn them.

## 3. Inbox

Only when the session-start notice reported unprocessed mail, or the user asks: run `agent-mail`, and name in the report what is still open.

## 4. Notes and the reflect slate

Run `notes`. Then run `reflect` through its slate (steps 1 to 3) without stopping: hold the slate for step 6. A stale in-repo claim reflect finds is fixed now, before the commit. Hold any graduation `notes` proposes (a shipped spec's or a verified learning's durable facts into `docs/`, per the `project-knowledge-vault` skill's `references/lanes.md`) for step 6 as well.

## 5. Join and fix

Take the reviewer's verdict, and the curator's report when one ran. Fix each finding with the smallest edit and a test, rerun `affected_tests.py --files` on the fixed files only, and re-sweep what changed. Only a finding the fix cannot settle goes to step 6, and nothing commits with a finding open. What the reviewer could not verify is checked here or goes to step 6.

Then close the review, after the step 6 answers when a finding went to the question. Write each finding to a JSON list as `{"finding", "status": "fixed" | "dismissed", "reason"}`; a dismissal needs a reason. Write `[]` when there were no findings or the review was skipped.

```bash
python3 "<skill-dir>/scripts/review_gate.py" close <findings.json>   # exit 1 while a finding is open
```

## 6. One question

```bash
python3 "<skill-dir>/scripts/gitignore_audit.py" audit   # exit 1 on findings
```

Ask everything that needs the user in one `AskUserQuestion`: review findings the fix could not settle, uncovered gitignore patterns, unprocessed inbox items that need a ruling, graduations into `docs/`, and reflect's slate. Recommend an answer for each. When nothing needs the user, skip the question.

## 7. Commit and push

Run `repo-device-sync` from Phase 2 through Phase 4, as one commit. A divergence stop there still stops.

## 8. Write memory

Apply the approved part of reflect's slate (its step 4 onward). Nothing in the repo is edited or committed after the push.

## Report

Report in one block: the verdict and what was fixed or accepted; the resource check; anything unverified and its outcome; the curator's edits and the inbox result, when those steps ran; what notes moved and the hot-file line counts; the commit hash and each ref's position; what reflect wrote or removed; anything undone; every gate and the user's decision.

## Never

- Merge a branch or PR, or publish to the mirror unless the user says so in that message.
- Drop a sub-skill's gate instead of folding it into step 6, or commit with an unresolved security finding.
- Stop for the user more than once, outside a divergence stop or a commit or push gate that blocks.
- Review the review's own fixes, or restart wrap-up after `review_gate.py` printed `CLOSED`.
- Stop a process the reaper reports without the user's yes.
