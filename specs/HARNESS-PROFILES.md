# Harness profiles

The core harnesses on this station side by side: what is installed, where it reads its config, whether it sees this repo's skills, what state its hooks are in, how it takes a model and an effort level, and what it is for.
One read here replaces opening the per-harness specs; each spec's Strengths section holds the detail and the provenance of every claim.

**Stamped 2026-10-14 on the laptop** from `python3 skills/agent-cc-configs-sync/scripts/harness_probe.py`.
A version bump is a re-probe trigger: rerun the probe, restate the date, and treat an unstamped row as unknown rather than current.

## The probe's output

```
harness      version             config home        present  skills canary          remote control
claude-code  2.1.280             ~/.claude          True     symlink present        off
codex        0.162.1             ~/.codex           True     no listing             off
cursor       2026.10.01-e373342  ~/.cursor          True     no listing             off
copilot      1.0.81              ~/.copilot         True     lists skill-authoring  off; per session only (--no-remote-export)
goose        1.54.0              ~/.config/goose    True     lists skill-authoring  off
pi           1.1.0               ~/.pi/agent        True     no listing             off
antigravity  1.3.3               ~/.gemini/config   True     skills.json present    off; telemetry switch unverified
```

The Antigravity row read `skills.json absent` before STORY-000074 wrote the file the same day, and a later probe that evening showed `agy` at 1.3.5: the binary updates itself, so the version here is the one the first probe saw. The remote-control column was added 2026-10-15 and read in a fresh shell after `PI_TELEMETRY=0` went into the profile.

"No listing" means the harness has no skill-list command that runs without a sign-in, so discovery is either verified another way or not verified yet; each spec says which.

"Remote control" is SPEC.md invariant 7: `off` means every remote-control, daemon and telemetry switch the harness exposes is off on this station, read from its config files and the process table; the row names the switch otherwise, and each spec's config table says where it lives.

## Side by side

| Harness | Version | Install route | Config home | Sees `~/.agents/skills/` | Hooks | Model and effort | Lane |
|---|---|---|---|---|---|---|---|
| Claude Code | 2.1.280 | official installer | `~/.claude/` | yes, by `sync-skills.sh` symlinks (observed) | 26 bindings seeded by `seed_hooks.py` | Anthropic models; `--effort low..max` | the station; work that matters |
| Codex | 0.162.1 | Homebrew cask | `~/.codex/` | yes (headless probe 2026-08-29) | captured, nothing wired until FEATURE-000039 | `-m <model>`; effort per model to `ultra` | medium stakes; second opinion; bounded delegation |
| Cursor | 2026.10.01 | Cursor's installer, self-updates | `~/.cursor/` | yes (print-mode probe 2026-08-29) | six events doc-derived; CLI sends shell events only; capture is FEATURE-000053 | 260 model ids on 2026-10-14; effort in the model name | medium stakes; editor; bounded delegation |
| Copilot | 1.0.81 | npm `@github/copilot` | `~/.copilot/` | yes, `copilot skill list` (observed) | `~/.copilot/hooks/` doc-derived, none here | GitHub-hosted picker; `--effort none..max` | medium stakes; GitHub artifacts |
| goose | 1.54.0 | Homebrew `block-goose-cli` | `~/.config/goose/` | yes, `goose skills list` (observed) | `PreToolUse` and `Stop` doc-derived; capture is FEATURE-000053 | Ollama `:cloud` tag; `thinking` pinned by the bench | medium stakes; open-source lane; recipes |
| pi | 1.1.0 | Homebrew `pi-coding-agent` | `~/.pi/agent/` | not yet observed (the bench runs under a fake home) | none; TypeScript extensions instead | BYOK, 20+ providers | medium stakes; configurable lane; sandboxed |
| Antigravity | 1.3.3, self-updated to 1.3.5 the same evening | `install.sh` to `~/.local/bin` | `~/.gemini/config/` | yes, through `skills.json` with an absolute path (model self-report in print mode; `~` is not expanded) | none here; `agy inspect` is gone at 1.3.3 | Google-hosted Gemini; `--effort low..max` | medium stakes; parked on the boards |

Gemini CLI has no row: the consumer product was retired on 2026-06-18 (doc-derived, recorded in the Gemini spec), Antigravity is its successor, and the laptop's never-run npm install was removed on 2026-10-15.
dsh, deepagents-code and kimi are not installed on the laptop.

## What each one is for

Each claim below is marked the way the specs mark it: **observed** (a run, a bench or a conference here), **doc-derived** (the vendor's documentation), **ruling** (a decision in `SPEC.md`) or **impression** (the user's working sense, not yet measured).

**Claude Code** is the whole station: the only harness here using skills, subagents, slash commands, hooks, plugins and the memory daemon together, and the delegating end of every task skill and of `agent-conference` (observed).
It is Anthropic-direct, so it is the lane for work that matters (ruling).
As a conference answerer it ranked third and fourth; its role there is the chair (observed).
Spec: [`claude-code/SPEC-CLAUDE-CODE.md`](claude-code/SPEC-CLAUDE-CODE.md).

**Codex** is the strongest second opinion on reasoning questions, ranked first of five valid members on 2026-10-13 and third of six on 2026-10-12 (observed).
`codex-task` runs it headless in a detached worktree with the sandboxed shell, network off and edits as `apply_patch`, and effort is a per-model dial that reaches `ultra` on the `sol` and `astra` models and `gpt-5.6-terra` (observed).
The user's sense that it drafts frontend and component work well is an impression with no bench task behind it yet.
Spec: [`codex/SPEC-CODEX.md`](codex/SPEC-CODEX.md).

**Cursor** is the editor lane and a reliable second model, ranked second in both conferences on `grok-4.7` (observed).
`cursor-task` bounds it with a per-run `sandbox-exec` profile, so the write bound is the operating system's rather than the agent's flag, and one seat reaches many vendors' models with effort encoded in the model name (observed).
Its hooks are documented for six events but the CLI is reported to send only the shell events (doc-derived, partly disproved).
Spec: [`cursor/SPEC-CURSOR.md`](cursor/SPEC-CURSOR.md).

**Copilot** is the GitHub lane: its agent ships GitHub's own repository, issue and pull-request tooling through a built-in GitHub MCP server on the `gh`-authenticated account (doc-derived).
It has the strictest `SKILL.md` parser of the set and lists the file and reason for every rejection without a sign-in, which makes it this repo's portability check (observed).
It sits on no panel and has no task skill, so there is no measured quality figure for it here.
Spec: [`copilot/SPEC-COPILOT.md`](copilot/SPEC-COPILOT.md).

**goose** is the open-source lane that completed the bench, 33 of 33 on `glm-5.3-flash:cloud`, and it truncates large tool output where pi does not, which made it the cheaper harness on long multi-file tasks (observed).
Recipes are its repeatable unit: a YAML file with the instructions, model settings, allowed extensions and sub-recipes, run headless with `goose run --recipe` (doc-derived).
Spec: [`goose/SPEC-GOOSE.md`](goose/SPEC-GOOSE.md).

**pi** is the leanest harness on the bench, 33 of 33 with 25 to 60 percent fewer input tokens than goose on ten of eleven tasks, and the most expensive on the one task where its missing tool-output cap sent a 258 KB file to the model whole (observed).
It is a four-tool core extended in-process by TypeScript, with per-run tool allow and deny lists and 20+ providers (doc-derived).
It has no built-in permission system, so it runs only under an outside sandbox (ruling).
Spec: [`pi/SPEC-PI.md`](pi/SPEC-PI.md).

**Antigravity** is Google's terminal agent on Gemini; it now sees this repo's skills through `skills.json`, and on `agent-conference` it scored zero on 2026-10-12 and returned no text on 2026-10-13, so it stays parked on the boards (observed).
Spec: [`antigravity/SPEC-ANTIGRAVITY.md`](antigravity/SPEC-ANTIGRAVITY.md).

## Related

[`HARNESS-MODELS-AND-EFFORT.md`](HARNESS-MODELS-AND-EFFORT.md) records how each CLI enumerates models and names effort levels, stamped with the version and date it was probed.
[`SEEDING-SHAPES.md`](SEEDING-SHAPES.md) defines the shapes each spec's Seeding table uses.
