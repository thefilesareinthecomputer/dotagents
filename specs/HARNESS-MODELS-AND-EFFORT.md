# Harness models and effort levels

Four CLIs with four model-discovery mechanisms, five effort vocabularies once
Antigravity's flag is counted, and no two alike. Every project that drives these harnesses meets this, so the table lives
here rather than in one repo's source comments.

**Probed 2026-08-30** against `codex-cli 0.150.1`, `cursor-agent
2026.08.25-3e8eec8`, `GitHub Copilot CLI 1.0.81`, `claude 2.1.251`.
**Re-probed 2026-10-14** against `codex-cli 0.162.1`, `cursor-agent
2026.10.01-e373342`, `GitHub Copilot CLI 1.0.81`, `claude 2.1.280`: the four
discovery mechanisms and the effort flags and their value sets are unchanged;
the codex lineup below is rewritten from that day's cache and cursor's list
is summarized after it.

**A version bump is a re-probe trigger.** A capability table with no date on it
is what produces the bug described at the bottom of this file: a contract probed
on 2026-08-27 recorded that Copilot had no reasoning-level flag, and three days
later that was false while code still asserted it. Restate the version and the
date whenever these tables are touched, and treat an unstamped row as unknown
rather than as current.

## Model discovery

| Harness | Version probed | Enumerable | How |
|---|---|---|---|
| codex | 0.150.1, same at 0.162.1 | Not from the CLI | `~/.codex/models_cache.json` - structured, per-model, carries `supported_reasoning_levels` and `default_reasoning_level` |
| cursor-agent | 2026.08.25, same at 2026.10.01 | Yes | `cursor-agent --list-models`, scoped to the logged-in account |
| copilot | 1.0.81, same on 2026-10-14 | No | `copilot models` fails with "Invalid command format"; `--help` documents `--model` and enumerates nothing |
| claude | 2.1.251, same at 2.1.280 | No | `--help` says "provide an alias for the latest model or the model's full name" and lists none |

codex holds the only machine-readable model data, and it is a cache file rather
than a documented interface, so treat its shape as unstable and read it
defensively.

## Effort and reasoning levels

| Harness | Flag | Values |
|---|---|---|
| claude | `--effort <level>` | low, medium, high, xhigh, max |
| codex | `-c model_reasoning_effort="<level>"` | low, medium, high, xhigh, max, ultra - **the set varies by model** |
| copilot | `--effort` / `--reasoning-effort` | none, minimal, low, medium, high, xhigh, max |
| antigravity (`agy`) | `--effort <level>` | low, medium, high, xhigh, max (1.3.3, read from `--help` 2026-10-14; not probed in a run) |
| cursor | none | effort is part of the MODEL: `gpt-5.6-sol-xhigh`, or a bracket parameter such as `claude-opus-4-8[context=1m,effort=high,fast=false]` |

Three consequences, each of which has already cost something somewhere:

1. **A shared effort constant across harnesses is wrong.** `ultra` is codex-only;
   `none` and `minimal` are copilot-only. Every harness rejects a level it does
   not know, so passing one through fails the spawn rather than degrading.
2. **Cursor does not lack effort, it locates it differently.** A cursor seat that
   should think harder needs its model changed, not its effort. "Cursor has no
   reasoning flag" is literally true and reads as false.
3. **codex effort is per-model, not per-CLI.** The Sol models, Astra and
   `gpt-5.6-terra` accept `ultra`; the Luna models and the internal pair stop at
   `max`. A correct validator reads
   `supported_reasoning_levels` for the chosen model rather than a flat list.

**Validators degrade, they do not fail.** Model and effort names belong to the
vendor and change without notice, so anything validating them drops an unknown
value and proceeds rather than refusing to spawn.

## codex lineup, as of the re-probe

Recorded because it is not otherwise discoverable. Read from
`~/.codex/models_cache.json`, whose own `fetched_at` was `2026-10-15T01:56:10Z`
(a refresh the CLI made during the 2026-10-14 probe). The 2026-08-30 cache listed
`gpt-5.5` and the retiring `gpt-5.4` pair; both are gone, and no model in this
cache has a retirement timestamp.

**The retirement timestamp is nested at `models[].upgrade.retirement_at`, not on
the model record.** Reading `model["retirement_at"]` returned nothing for every
model in the 2026-08-30 cache, including the two that were retiring, so a
staleness check written against the obvious path silently reports that nothing
ever expires.

| Model | Default effort | Top level |
|---|---|---|
| `gpt-6.1-sol` | low | ultra |
| `gpt-6-astra` | low | ultra |
| `gpt-6-sol` | medium | ultra |
| `gpt-6-luna` | medium | max |
| `gpt-5.6-sol` | low | ultra |
| `gpt-5.6-terra` | medium | ultra |
| `gpt-5.6-luna` | medium | max |
| `gpt-reserve`, `codex-auto-review` | medium | max |

## cursor lineup, as of the re-probe

`cursor-agent --list-models` on 2026-10-14 printed 260 model ids for the
signed-in account. They cover Anthropic (Fable 5.1 and 5, Opus 5.5 through 4.5, Sonnet 5.5
through 4, Haiku 5.5), OpenAI (GPT-5.6 Sol, Terra and Luna, GPT-5.5, 5.4, 5.3
Codex, 5.2, 5.1), Google (Gemini 4 Argon, 3.8 through 3 Flash, 3.1 Pro), xAI
(Grok 4.7, 4.6, 4.5), Cursor's Composer 2.5, Muse Spark 1.3, Kimi K3 and K2.7
and GLM 5.2. Effort and thinking are suffixes on the id (`-low` to `-max`,
`-thinking`, `-fast`), which is the effort table's cursor row in its current
form. The Fable ids are marked `(NO ZDR)` in their display names.

## Why this is dated rather than tidy

A capability contract probed on 2026-08-27 recorded that Copilot had no
reasoning-level flag. By 2026-08-30 `--effort` existed, and a driver written
against the older probe discarded a seat's effort setting while a comment
asserted the flag did not exist. The setting looked applied and did nothing.

That is the failure this file exists to prevent: not a wrong table, but an
undated one.
