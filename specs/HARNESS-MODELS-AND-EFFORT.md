# Harness models and effort levels

Four CLIs, four model-discovery mechanisms, four effort vocabularies, and no two
alike. Every project that drives these harnesses meets this, so the table lives
here rather than in one repo's source comments.

**Probed 2026-08-30** against `codex-cli 0.150.1`, `cursor-agent
2026.08.25-3e8eec8`, `GitHub Copilot CLI 1.0.81`, `claude 2.1.251`.

**A version bump is a re-probe trigger.** A capability table with no date on it
is what produces the bug described at the bottom of this file: a contract probed
on 2026-08-27 recorded that Copilot had no reasoning-level flag, and three days
later that was false while code still asserted it. Restate the version and the
date whenever these tables are touched, and treat an unstamped row as unknown
rather than as current.

## Model discovery

| Harness | Version probed | Enumerable | How |
|---|---|---|---|
| codex | 0.150.1 | Not from the CLI | `~/.codex/models_cache.json` - structured, per-model, carries `supported_reasoning_levels` and `default_reasoning_level` |
| cursor-agent | 2026.08.25 | Yes | `cursor-agent --list-models`, scoped to the logged-in account |
| copilot | 1.0.81 | No | `copilot models` fails with "Invalid command format"; `--help` documents `--model` and enumerates nothing |
| claude | 2.1.251 | No | `--help` says "provide an alias for the latest model or the model's full name" and lists none |

codex holds the only machine-readable model data, and it is a cache file rather
than a documented interface, so treat its shape as unstable and read it
defensively.

## Effort and reasoning levels

| Harness | Flag | Values |
|---|---|---|
| claude | `--effort <level>` | low, medium, high, xhigh, max |
| codex | `-c model_reasoning_effort="<level>"` | low, medium, high, xhigh, max, ultra - **the set varies by model** |
| copilot | `--effort` / `--reasoning-effort` | none, minimal, low, medium, high, xhigh, max |
| cursor | none | effort is part of the MODEL: `gpt-5.6-sol-xhigh`, or a bracket parameter such as `claude-opus-4-8[context=1m,effort=high,fast=false]` |

Three consequences, each of which has already cost something somewhere:

1. **A shared effort constant across harnesses is wrong.** `ultra` is codex-only;
   `none` and `minimal` are copilot-only. Every harness rejects a level it does
   not know, so passing one through fails the spawn rather than degrading.
2. **Cursor does not lack effort, it locates it differently.** A cursor seat that
   should think harder needs its model changed, not its effort. "Cursor has no
   reasoning flag" is literally true and reads as false.
3. **codex effort is per-model, not per-CLI.** Sol and Terra accept `ultra`;
   Luna, 5.5 and 5.4 do not. A correct validator reads
   `supported_reasoning_levels` for the chosen model rather than a flat list.

**Validators degrade, they do not fail.** Model and effort names belong to the
vendor and change without notice, so anything validating them drops an unknown
value and proceeds rather than refusing to spawn.

## codex lineup, as of the probe

Recorded because it is not otherwise discoverable. Read from
`~/.codex/models_cache.json`, whose own `fetched_at` was `2026-08-30T00:05:27Z`.

| Model | Default effort | Levels | Note |
|---|---|---|---|
| `gpt-5.6-sol` | low | to ultra | frontier agentic coding |
| `gpt-5.6-terra` | medium | to ultra | balanced everyday |
| `gpt-5.6-luna` | medium | to max | fast and affordable |
| `gpt-5.5` | medium | to xhigh | frontier for complex work |
| `gpt-5.4`, `gpt-5.4-mini` | medium | to xhigh | **retire 2026-08-31T19:00:00Z**, upgrade path points at Terra |
| `gpt-reserve`, `codex-auto-review` | medium | to max | internal |

**The retirement timestamp is nested at `models[].upgrade.retirement_at`, not on
the model record.** Reading `model["retirement_at"]` returns nothing for every
model including the two that are actually retiring, so a staleness check written
against the obvious path silently reports that nothing ever expires.

## Why this is dated rather than tidy

A capability contract probed on 2026-08-27 recorded that Copilot had no
reasoning-level flag. By 2026-08-30 `--effort` existed, and a driver written
against the older probe discarded a seat's effort setting while a comment
asserted the flag did not exist. The setting looked applied and did nothing.

That is the failure this file exists to prevent: not a wrong table, but an
undated one.
