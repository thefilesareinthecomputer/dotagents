---
name: skill-authoring
description: House profile for authoring and auditing Claude Code skills, subagents, commands, rules, and hooks that stay compliant with the open Agent Skills standard (agentskills.io) while using Claude Code extensions deliberately. Use whenever creating, editing, improving, renaming, or reviewing ANY skill, subagent, slash command, hook, or rules file - e.g. "make/write/build a skill to X", "change/update/fix/improve the X skill", "add a subagent/command for X", "audit my skills", "why isn't my skill triggering", or "which frontmatter fields are valid". Also use when deciding between a skill vs command vs subagent vs hook. Pairs with the skill-creator plugin for scaffolding and evals.
---

# skill-authoring

House rules for building agent tooling in this repo: Claude Code-opinionated,
open-standard compliant. A skill valid under the open Agent Skills standard is
automatically valid in Claude Code (Claude Code makes every field optional), so
the profile is: **write to the standard's rules as if mandatory, add Claude Code
extensions only as progressive enhancement.**

Verified against official docs 2026-07-01 (code.claude.com/docs/en/skills,
agentskills.io/specification, platform.claude.com agent-skills best-practices).
Re-verify before trusting version-sensitive details.

## The profile

### Core (open standard, treat as mandatory)

| Field | Rule |
|---|---|
| `name` | lowercase a-z 0-9 hyphens, 1-64 chars, **must match the directory name**, no leading/trailing/consecutive hyphens, no "anthropic"/"claude" |
| `description` | 1-1024 chars hard limit, **600-800 is the house target**, **third person**, states what the skill does AND the concrete conditions that should trigger it, no XML tags. A plain scalar must contain no `: ` (colon followed by space) or the YAML fails to parse; use a spaced hyphen, or a `>-` folded block. |
| `license` | optional, include when a skill may be shared |
| `metadata` | optional string map; put custom keys (e.g. `version`) HERE, not top-level |
| `allowed-tools` | optional, experimental in the standard |

### Claude Code extensions (use deliberately; no-ops elsewhere)

`when_to_use`, `argument-hint`, `arguments`, `disable-model-invocation`,
`user-invocable`, `disallowed-tools`, `model`, `effort`, `context`, `agent`,
`hooks`, `paths`, `shell`. A skill must still work if these are stripped.
Common deliberate uses:

- `disable-model-invocation: true` for command-like skills that should never
  auto-fire (also removes the description from the context listing).
- `user-invocable: false` for model-only background knowledge.

Top-level fields outside these two sets (e.g. `version`, `last-modified`) are
ignored by Claude Code and may fail other consumers' validators. Anything a
tool genuinely consumes goes under `metadata:`; `version`/`last-modified`
specifically are not tracked on skills at all - see the Eval convention below.

### Structure (both specs agree)

- SKILL.md body **under 500 lines**; split extra content into `references/`.
- `scripts/`, `references/`, `assets/` are the conventional dirs; keep
  reference files **one level deep** from SKILL.md; give reference files over
  100 lines a table of contents. (`tests/` fixtures may nest; they are not
  read as references.)
- **`references/` is the name, not `resources/`.** The three conventional dirs
  split by consumer: `references/` = docs the model reads, `assets/` = files that
  end up in the output, `scripts/` = code it runs. Data a script reads or writes
  fits none of the three, and `resources/` is the local name for that fourth
  category (ai-engineering's corpus TSVs) - an addition to the convention, never
  a substitute for `references/`. A skill that puts model-read docs in
  `resources/` is not broken, but it is off-convention and it teaches the next
  author the wrong default.
- Scripts beat inline generated code; state whether the agent should EXECUTE
  or READ each script; scripts solve errors explicitly, never punt.
- No time-sensitive facts inline (they rot); date any that are unavoidable.

## Description discipline (the whole game)

Descriptions are the only thing loaded at startup (~100 tokens each); the body
loads on invocation. A skill that never fires is dead weight, and the listing
budget is finite (about 1 percent of the context window; `/doctor` shows
truncation), so every marginal skill hides a better one.

- Lead with capability, then enumerate **when-to-fire conditions**: user
  phrasings, file types, situations. Field experience (Vincent, 2025-12)
  shows newer models skip loading skills whose descriptions only say WHAT,
  so the WHEN clauses carry the trigger.
- Third person always ("Sends templated messages...", never "I can...").
- Positive framing; anti-pattern-framed skills fire worse.
- If a skill still auto-fires unreliably, convert it to explicit invocation
  (`disable-model-invocation: true`) rather than inflating the description.
- Consolidate overlapping skills; two skills competing for one trigger both
  lose.
- Measured (2026-07-10, sonnet trigger evals across 16 skills): **situation
  clauses beat phrase lists** - describing the concrete moment ("ANY push
  intent, however casually phrased - do not just run git directly") moved
  recall 73%→93%, while quoting more user phrasings moved nothing; firm
  "MUST be used" framing cost zero precision. Orchestration-shaped skills
  (fan-out/delegation procedures) never model-invoke - the model plans
  directly instead of reading them; treat explicit invocation as their
  primary path.

## Surface discipline (SKILL.md is an interface, not a workshop)

The body an agent loads at invocation carries only what an operator needs at
the moment of use: what each command or step does, how to invoke it, how to
interpret its output, and the safety rails it must know exist. Everything
else - fixtures, answer keys, design rationale, benchmarks, test corpora -
lives in `tests/`, `references/`, or the spec that built the skill, where it
costs nothing until deliberately opened. The test: a skill may carry
thousands of lines of verification apparatus, and none of it belongs in the
file the agent reads to fire the scripts. Depth in the skill, brevity at the
interface.

## Subagents (agents/*.md)

Only `name` + `description` required. Recognized fields (2026-07):
`tools`, `disallowedTools`, `model` (sonnet/opus/haiku/fable/full-id/inherit),
`permissionMode` (camelCase), `maxTurns`, `skills`, `mcpServers`, `hooks`,
`memory`, `background`, `effort`, `isolation`, `color`, `initialPrompt`.

- Omitting `tools` inherits EVERYTHING including MCP; advisory/read-only
  agents need an explicit read-only allowlist (capability gates behavior,
  prose does not).
- Choose a subagent for isolation or tool restriction; choose a skill for a
  reusable workflow in the main context.

## Commands (commands/*.md)

Slash commands are merged into skills (Claude Code 2.1): same frontmatter
dialect. A command is the right shape when invocation should be explicit and
argument-driven (`argument-hint`), not model-triggered.

## Rules and hooks (placement guidance)

- CLAUDE.md: session-constant facts only, keep under ~200 lines.
- Multi-step procedures belong in skills, not CLAUDE.md.
- Path-scoped guidance: `.claude/rules/*.md` with `paths:` globs.
- Enforcement belongs in PreToolUse hooks or the permission system, never in
  prose; hook exit code 2 blocks, exit 1 does NOT (documented footgun).
- **Never write a bare hook invocation into a skill.** A hook reads its payload
  from stdin, so `python3 ~/.claude/hooks/x.py` with nothing piped blocks until
  the tool timeout kills it. The agent then reports a script defect that does not
  exist. Where a skill needs to confirm what a hook enforces, check the invariant
  directly with a few lines of shell, or pipe the payload the harness would send:
  `echo '{"tool_input":{"file_path":"..."}}' | python3 ~/.claude/hooks/x.py`.
- **Any command a skill prescribes against a script it does not own carries
  `timeout`.** A hang then fails in seconds and names itself, instead of
  consuming the whole tool budget and looking like a broken tool.

## Audit checklist

Run over `skills/*/SKILL.md`, `agents/*.md`, `commands/*.md`:

1. Frontmatter parses; `name` matches directory; lowercase-hyphen; <=64 chars.
2. `description` non-empty, 600-800 chars (1024 is the standard's hard cap),
   third person, has explicit when-to-fire conditions, no XML, and no `: ` in a
   plain scalar. Claude Code's parser is lenient about both, so neither shows up
   until a stricter harness reads the file - Copilot rejected 8 of 24 skills on
   these two faults on 2026-08-08. Check with `copilot skill list` and
   `opencode debug skill`, run from outside any repository; neither needs
   authentication and both name the file and reason for every rejection.
3. No top-level fields outside the standard + Claude Code sets; custom keys
   under `metadata:`; no `Version:`/`Last modified:` line anywhere in the file.
4. Body <=500 lines; references one level deep; scripts' execute-vs-read
   intent stated.
5. Advisory agents have read-only `tools:` allowlists.
6. Path hygiene per `my-security-review-checklist` (no `/Users/<name>/`).
7. Trigger sanity: does the description enumerate the situations this repo
   actually uses it in?

## Tooling

- **skill-creator plugin** (`/plugin install skill-creator@claude-plugins-official`):
  scaffolding (`init_skill.py`), packaging, `quick_validate.py`, and a full
  eval framework (`run_eval.py`, `run_loop.py`, `aggregate_benchmark.py`,
  grader/comparator/analyzer agents, HTML eval viewer).
- `skills-ref validate` (open-standard reference validator) for interop
  checks on anything shared outside Claude Code.

### Eval convention (house wrapper around the plugin)

The plugin is the eval ENGINE; this skill sets the house conventions it runs
under. Division of labor: plugin = mechanism, this profile = policy.

- **The plugin has TWO eval concerns with two schemas, and documents only one.
  Name each file for its consumer, or it needs hand-conversion every run:**

  | File | Shape | Read by |
  |---|---|---|
  | `evals/triggers.json` | flat JSON list of `{query, should_trigger}` | `run_eval.py`, `run_loop.py`, `improve_description.py`, `generate_report.py` |
  | `evals/evals.json` | `{skill_name, evals[].{id, prompt, expected_output, expectations}}` (the shape in the plugin's `references/schemas.md`) | `aggregate_benchmark.py` |

  Triggering is the concern nearly every skill needs, so `triggers.json` is the
  default and `evals.json` is for skills that also want behaviour benchmarks.
  Putting trigger cases in a file named `evals.json` is the trap: it matches
  neither consumer and no tool will tell you (cost two sessions of manual
  conversion before it was caught, 2026-07-30).
- **Extra keys in `triggers.json` are tolerated** - `run_eval.py` does a plain
  `json.loads` and indexes only `query` and `should_trigger`, with no schema
  validation. So carry `name` and `why` per case; the rationale is what lets you
  tell a bad case from a real miss when one fails.
- Minimum 3 cases per skill, including at least one should-trigger and one
  should-NOT-trigger case (trigger precision matters as much as recall).
- Write evals BEFORE polishing prose on a new skill; re-run after any
  description change (that is the field most likely to regress triggering).
- `tests/` (does the code work) sits alongside `evals/` (does the skill fire and
  behave); they answer different questions and both gate merge. See the test
  convention below for what a skill shipping executable code owes.
- **Invocation, which is not obvious and has cost time twice.** Run it **as a
  module from the plugin's own skill directory**, because a direct path
  invocation dies on `ModuleNotFoundError: No module named 'scripts'`. The flags
  are `--eval-set` and `--skill-path`, not `--evals` and `--skill`. Do not wrap
  it in `timeout`; macOS has no such command.

  ```bash
  cd ~/.claude/plugins/cache/claude-plugins-official/skill-creator/*/skills/skill-creator
  python3 -m scripts.run_eval \
    --eval-set <skill>/evals/triggers.json \
    --skill-path <skill> --model claude-sonnet-5 --num-workers 1
  ```

  It spawns a fresh `claude -p` per case, and `--runs-per-query` defaults to 3,
  so the real unit is cases times three: a 20-case set is 60 serialized spawns at
  roughly 20 seconds each, near 20 minutes. Budget from that arithmetic rather
  than from the case count, and run it in the background. Send its output
  straight to a file; piping it through `tail` or `head` buffers the whole run,
  so progress stays invisible until the process exits. Drop to
  `--runs-per-query 1` when the question is only whether a description change
  moved recall by a lot, and keep 3 when a flaky miss has to be told from a
  real one.
- Run `run_eval.py` with `--num-workers 1` and an explicitly pinned `--model`
  (probes must never inherit the session tier; a cheap tier is fine for trigger
  probes): parallel workers register their
  synthetic uuid-named command copies in the same project root simultaneously,
  so the model invokes another worker's copy and the scorer counts a miss
  (observed 2026-07-26: identical set scored 3/8 at 4 workers for this reason).
  If the skill under test is already installed (symlinked into
  `~/.claude/skills`), unlink it for the duration of the run - the model will
  invoke the real name instead of the uuid-suffixed eval copy, which also
  scores as a miss - and re-run `sync-skills.sh` afterward even if the eval
  run fails, so the station never stays desynced.
- **Repo-bound skills score zero recall structurally.** Probes spawn `claude -p`
  outside the target repo, so a skill whose firing precondition is repo-bound (a
  vault, a local corpus, a project database) fails every should-trigger case no
  matter how good the description is - the probe has nothing to mine, so
  answering directly looks correct to it. Precision cases stay meaningful; treat
  recall for such skills as untestable by this harness and validate in vivo,
  with the user waiving the recall gate explicitly. Also: a dot-prefixed
  directory rename does NOT hide a skill from registration, so it is not a way
  to clear a name collision during a run (both observed 2026-08-29).
- **No version numbers on skills.** Not in frontmatter, not as a body footer.
  Nothing reads them, nothing bumps them, and a hand-maintained number that
  drifts from the file is worse than no number: git already holds the version
  history, with real timestamps and diffs. (Skills carried a `Version: X.Y.Z`
  footer until 2026-07-13; the footers were stripped and the rule inverted.)
  Genuinely niche metadata that some tool actually consumes goes under
  `metadata:` in frontmatter - never as a custom top-level key.

### Test convention (skills that ship executable code)

A skill that ships anything runnable - a script, a linter, a checker, an engine -
owes tests, at every level that practically applies to it:

- **Unit** - the pure logic, especially any function whose output other parts key
  on. Canonicalization, parsing, classification and merge rules earn cases with
  their edge inputs, not just their happy path.
- **Integration** - the parts that meet something real: files written and read
  back, a database rebuilt, a subprocess driven. Redirect any module-level paths
  at a temporary directory so a test run can never touch real data.
- **End to end** - drive the actual entry point the way a user does, through the
  CLI surface rather than the internals, and assert the observable result. For
  anything that regenerates a file, assert idempotence: running twice produces
  identical bytes. Skipping this level is how a suite passes while the command
  itself is broken.

Stdlib `unittest`, runnable with a plain `python3 -m unittest discover -s tests`,
matching the other script-bearing skills. A skill that ships no executable code
owes evals only.

Tests are written against the behavior the code should have. When a test fails,
decide which is wrong before editing either - a test encoding a mistaken
expectation gets fixed, a defect in the code gets fixed in the code, and saying
which one it was is part of reporting the work.

## Completion gate (MANDATORY before a new or changed skill is committed)

A skill is not done when the prose is written. In order:

1. **Slop pass** - run `ai-slop-magic-eraser`'s `scripts/slop_check.py` over
   SKILL.md and every `references/` file; fix the findings or consciously keep
   them (terms of art and corrective antitheses are legitimate keeps; symbols,
   filler, and meta-commentary are not).
2. **Security pass** - apply `my-security-review-checklist` in full: personal
   constants, user-specific paths, secrets, and untrusted-input handling for
   any scripts or hooks the skill ships.
3. **Tests written AND passing** - if the skill ships executable code, `tests/`
   exists per the test convention above, covers unit, integration and end-to-end
   at whatever levels apply, and the full suite passes. A green suite is the
   evidence; "it worked when I ran it" is not.
4. **Evals written AND run** - the two eval files answer different questions:
   `evals/triggers.json` asks whether the skill **fires**, `evals/evals.json`
   asks whether it **behaves** once fired. Every model-invocable skill has
   `evals/triggers.json` carrying a minimum of 3 cases in both polarities (at
   least one should-trigger and one should-NOT-trigger), and those cases have
   actually been run with the model pinned. Three is a floor: a skill whose
   trigger scope is contested, because it borders another skill or fires on a
   situation rather than a phrase, needs more to draw that boundary. A skill with
   `disable-model-invocation: true` never auto-fires, so it is exempt from
   `evals/triggers.json`. `evals/evals.json` is required only where behavior is
   complex enough to be worth benchmarking - a skill shipping executable code, a
   destructive failure mode, a multi-step procedure with a defined output.
   Failures are fixed or explicitly waived by the user, not ignored. Run
   `scripts/check_eval_coverage.py` for which file each skill has, and to catch
   a file whose contents match the other file's schema.

Only then commit. The audit checklist above covers structure; this gate covers
quality, safety, correctness, and triggering. Both gates 3 and 4 report real
results: a skipped suite, a waived failure or an unrun eval is stated plainly
rather than implied to have passed.

## Anti-patterns

- Renaming a skill other tooling invokes by name (breaks the reference graph).
- Descriptions that summarize behavior but list no firing conditions.
- Stuffing procedures into CLAUDE.md or enforcement into prose.
- A subagent with default (inherited) tools doing advisory-only work.
- Custom top-level frontmatter keys instead of `metadata:`.
- Hand-maintained `Version:` / `Last modified:` lines on a skill - git is the
  version history.
- **Overfitting a skill to the incident that prompted it.** A lesson learned on
  one project arrives with that project's vocabulary attached. Encode the
  principle with generic examples; put the domain-specific examples in the
  project's own CLAUDE.md. Before committing an edit, grep the skill for the
  triggering project's product names, file names and lifted phrases.
