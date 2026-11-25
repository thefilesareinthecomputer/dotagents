# Changelog

What each push changes, newest first, for machines pulling this repo.

## 2026-11-25

### Action needed

- Re-seed the Claude Code hooks so `reject_bad_commit_message.py` picks up the CodeQL rule names: `python3 skills/agent-cc-configs-sync/scripts/seed_hooks.py apply --harness claude-code`.

### Added

- `skill-authoring`: `scripts/check_portable.py` flags constructs that break on Windows (POSIX-only `os` attributes and modules, text writes without `newline="\n"`, entry scripts without a UTF-8 console, a hardcoded interpreter). `references/cross-os.md` holds the rules, and the audit checklist and completion gate run the check over changed scripts.

### Changed

- `sprint-board`: stories have a relevance rule (intention, execution details and acceptance criteria; a known blocker stated as a fact in the step it affects). `references/anatomy.md` budgets story purpose at 1-3 sentences and story key activities at 3-6 checkboxes, which `board_lint.py` warns on.
- `specs/HARNESS-ENGINEERING.md` is now the hub for every harness. It covers:
  - what a harness is;
  - the required components, centered on the agent loop, each with the standard most harnesses use;
  - the loop's limits and failure handling;
  - an index of every harness spec;
  - a ten-question architecture template;
  - breakout sections on context, compaction, caching, permissions, sessions, rules files, ACP, subagents and evaluation.
- Every harness spec in `specs/` gains an `## Architecture` section answering the same ten questions. Each answer is marked source, docs, observed or unknown.
- `ai-engineering`:
  - B.6 compares how 14 coding-agent harnesses build their core loop, with 8 open-source harnesses read from source at pinned commits.
  - B.5 gains first-hand measurements on Ollama's MLX runner and five harness pitfalls.
  - New field notes cover Ollama 0.40.18, Inkling 2 Mini, embeddinggemma, LFM3-Audio (speech in and out verified locally) and Kimi CLI (repo archived).
  - The two local-agent stack decisions are stamped held (Ollama) and abandoned (sqlite-vec).

### Fixed

- `code-kg` tests run on Python 3.9 again: `fixture_copy.py` writes generated fixture files with `open(..., newline="\n")` instead of the 3.10+ `Path.write_text(newline=...)`.
- The commit-message rules in `reject_bad_commit_message.py` and `sanitize`'s `detect.py` accept CodeQL rule names such as "Incomplete URL substring sanitization" and their query ids. The bare verb elsewhere in the message still refuses.
- `lib/AGENTS.md` states the Python 3.9 rule and the `repo-lib` marker rule itself, so it no longer cites `hooks/AGENTS.md` or `tests/test_repo_lib.py`, which a published copy of `lib/` does not carry.
- Windows support in `lib/kg_core.py`, `markdown-kg`, `code-kg`, `project-knowledge-vault`, `sprint-board`, `compact-notes` and `gather-learnings`; output on macOS is unchanged:
  - `os.O_NOFOLLOW` is read with `getattr`, so `init` no longer raises `AttributeError` on Windows.
  - Generated files are written with LF line endings on every OS.
  - Entry scripts set their console streams to UTF-8 on Windows.
  - Symlink tests skip on Windows, and the `code-kg` coverage-command tests expect `python_cmd()` rather than `python3`.

## 2026-11-24

### Action needed

- Re-seed the Claude Code hooks: `python3 skills/agent-cc-configs-sync/scripts/seed_hooks.py apply --harness claude-code`.

### Changed

- `reaper.py` hook: reports any of the user's processes that has averaged 25% CPU or more for over an hour, whatever its name, such as a runaway app; it also runs on prompts, at most every 30 minutes, reporting each process once. It still only reports.
- `reaper.py` hook: reports an orphaned agent browser (launched with `--remote-debugging-pipe`, a temp `--user-data-dir`, or a Playwright build) after 2 minutes at any CPU, with CPU and memory summed over its process group and the group stop command when it leads a private group, and an orphaned Playwright or Chrome DevTools MCP server; a Dock-launched browser is never reported by this rule.

- `markdown-kg`: the non-note link test asserts that no edge target carries a URL scheme, instead of matching a host substring, which CodeQL reads as URL sanitization.
- `code-kg`: the Next.js test fixture's `package.json` is written at test time by `tests/fixture_copy.py` instead of committed, so dependency scanners no longer flag its pinned versions.
- `tests/test_published_set_hygiene.py`: fails when a committed test fixture manifest pins an exact dependency version.
- `publish-mirror.sh`: `--branch <name>` copies onto a new branch cut from the target's freshly fetched remote default branch, for a mirror that takes changes only by pull request.

## 2026-11-23

### Action needed

- Run `bash sync-skills.sh` for the new `agent-team` skill.
- Re-seed Claude Code settings: `python3 skills/agent-cc-configs-sync/scripts/seed.py apply --harness claude-code`.

### Added

- `agent-team`: `/agent-team lead` and `/agent-team join <lead>` coordinate live Claude Code sessions in other repos by direct message; `scripts/packet_check.py` checks a delivery's evidence, its criteria against the assignment commit, the commits after the head and the story's state trail.

### Changed

- `sprint-board`: `board_query.py --story --json` adds a `comments` list holding the story's COMMENTS lines.
- Claude Code settings seed: `crossSessionInbound: accept` delivers direct messages from other local sessions without holding them; sessions in bypass-permissions mode then act on them with no prompt.
- `AGENTS.md`: rules restated as prose, with a trust and alignment section.

## 2026-11-22

### Action needed

- Re-seed the Claude Code hooks: `python3 skills/agent-cc-configs-sync/scripts/seed_hooks.py apply --harness claude-code`.
- Run `bash sync-skills.sh` for the new `goldfish` skill.

### Added

- `goldfish`: a fresh-context reader reviews a spec, its plan files and the code they name before implementation, and lists every guess, dangling reference and contradiction.
- `skill-authoring`: `scripts/trigger_eval.py` runs a skill's trigger evals against the installed skill, six probes at a time, and scores each case where the model commits.
- `ai-engineering`: corpus sections on weight-space programming and the Inkling open-weight models.
- `CHANGELOG.md`, updated with each push.

### Changed

- `skill-authoring`: `trigger_ab.py` runs on `trigger_eval.py`; `--jobs`, `--skill-creator` and `--variant-timeout` are accepted and ignored.
- `skill-authoring`: skill descriptions aim at 950 characters and fail above 1000; `check_descriptions.py` notes anything over 950.
- Web guard hooks: one host takes up to 100 requests per session, up from 20.
- Web guard hooks: a 429 or 503 blocks its host until the Retry-After time, else for one hour (`WEB_GUARD_BLOCK` sets the window in seconds); a 401 or 403 still blocks for the session. Block messages and `web_download.py` say when a block lifts.
- `markdown-kg`, `code-kg`: `migrate` drops an ignore row that names the legacy store folder itself, and reports it.
- `compact-notes`: `inspect`, `backup` and `verify` take `<heading>~N` to address the Nth section under a repeated heading.
- `repo-device-sync`: the push phase updates `CHANGELOG.md` first when the repo keeps one.

## 2026-11-21

### Action needed

- Re-seed the Claude Code hooks and settings: `python3 skills/agent-cc-configs-sync/scripts/seed_hooks.py apply --harness claude-code` and `python3 skills/agent-cc-configs-sync/scripts/seed.py apply --harness claude-code`.

### Added

- `sprint-board`: `scripts/board_state.py` sets a story's State and appends a timed record to its COMMENTS block; `board_query.py --story <ID> [--json]` lists a story's criteria, VALIDATION and Definition of Done lines.
- `sprint-board`: stories carry an empty `**COMMENTS**` block, ignored by box counts and content checks.

### Changed

- Downloads: the shell guard refuses a main-session file download and names `hooks/web_download.py` instead; every batch is scanned by the `scan` skill, and every scanner shares one lock.
- `task`: model-invocable, with each launch behind an `ask` permission rule.
- `AGENTS.md`: the download rule names `hooks/web_download.py`; two chat rules on disagreement and challenged claims.

## 2026-11-20

### Changed

- `project-knowledge-vault`: a new vault's location is asked once, with a default (`kb/` in a code repo, `PROJECTS/<NAME>/` in a multi-project folder); `--into` refuses a folder that is not a vault and holds subfolders.

## 2026-11-19

### Action needed

- Re-seed the Claude Code hooks, run `bash sync-skills.sh`, and restart sessions.

### Changed

- `code-kg`: incremental ingest; a parse cache rewrites only changed files.
- `code-kg`, `markdown-kg`: reads that find the graph out of date take a rebuild lock in turn, so one rebuilds and the others reuse it.
- `deny-bash-file-writes` hook: nested shells, `eval` and command substitution are rescanned; shell writes to literal temp paths pass; copying temp content to another path is refused.
- `wrap-up` asks its questions once; the `worker` subagent runs on Sonnet.

### Removed

- The foreign-edit warning hook.

## 2026-11-18

### Changed

- `code-kg`, `markdown-kg`: the shared core lives in `lib/kg_core.py`; a skill that imports `lib/` declares `metadata.ships: repo-lib`.
- `code-kg`, `markdown-kg`: `.kg/` ignores only the databases, so configs are committed; every file and note carries its git status, with a `--git` filter; credential-named files are never opened.

## 2026-11-17

### Action needed

- In each repo or vault with a legacy graph folder (`.code-kg/`, `vault-kg/`), run the engine's `migrate` command.

### Changed

- **Breaking:** `code-kg`, `markdown-kg`: one shared `.kg/` folder per repo or vault, with plain-JSON configs; membership comes from `.kgignore` alone; `--path` on `search` and `query`.

## 2026-11-16

### Action needed

- Re-seed the Claude Code hooks and settings, and run `bash sync-skills.sh`.

### Added

- Process lifecycle: every spawn goes through `procguard.py`, with background and orphan hooks and a spawn linter (`check_spawns.py`).
- `code-kg`: Dockerfiles, compose, CI workflows, `package.json` scripts, Makefiles and Terraform read at code depth; a file inventory with `tree`; `diff` against a checkpoint; `related` and `relate`.

### Changed

- `markdown-kg`: incremental ingest with a parse cache, and a faster full ingest.
- Claude Code settings seed: `idleCompaction` is off.
- One review rubric and one security reviewer; `wrap-up` runs affected test suites under `procguard`.

## 2026-11-15

### Added

- `code-kg`: call, reference and data edges for Python, JS/TS, bash, SQL, HTML and CSS; data flow; observed calls from a traced test run (`coverage run --yes --calls`); symbol-level liveness (`dead --symbols`).
- `markdown-kg`, `code-kg`: each answers across the other (`refs`, `code`, `docs`, `--mentions`, `resolve`).

### Changed

- **Breaking:** `markdown-kg spans` and `code-kg docs` print 50 rows by default; `--limit 0` returns all.

## 2026-11-14

### Action needed

- Re-seed the Claude Code hooks and permissions: `python3 skills/agent-cc-configs-sync/scripts/seed_hooks.py apply --harness claude-code` and `python3 skills/agent-cc-configs-sync/scripts/seed.py apply --harness claude-code --key permissions`.

### Added

- Web access hooks: a host's refusal is final for the session, requests to one host are spaced, subagents do not fetch in the shell, and the main session downloads a batch from a manifest with `hooks/web_download.py`. Government and military hosts ask in the main session and are denied to subagents.
- `markdown-kg`, `code-kg`: each extends through its own config file, with a `config` check; markdown links resolve to the heading or block they name.

## 2026-11-13

### Action needed

- Re-seed the Claude Code settings: `python3 skills/agent-cc-configs-sync/scripts/seed.py apply --harness claude-code`.

### Changed

- Claude Code settings seed: the Artifact tool is off and the Claude Docs connector is denied.
