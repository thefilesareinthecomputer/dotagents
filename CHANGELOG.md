# Changelog

What each push changes, newest first, for machines pulling this repo.

## 2026-11-24

### Changed

- `markdown-kg`: the non-note link test asserts that no edge target carries a URL scheme, instead of matching a host substring, which CodeQL reads as URL sanitization.

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
