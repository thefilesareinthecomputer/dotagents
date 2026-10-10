# decision-hook

A draft station hook, not a skill: a local judgment (deterministic call features, and a small model or learned head on loopback where they are not enough) looks at every Bash, Write, Edit and MCP call before it runs and can only say "ask" or nothing. Everything starts in shadow mode, where it logs what it would have said and changes nothing. It lives under `specs/drafts/` because its judgment has not yet cleared the success numbers on real labels; until it does, no station copies, configures or wires it (`specs/drafts/README.md`). Design and phase records: `tasks/SPEC-DECISION-HOOK.md`; measurements and design history: `NOTES.md`.

## Operator commands

Stdlib Python, loopback only. The paths below are this repo's draft folder. After the move into the station tree they become `~/.claude/hooks/decision-hook/...`.

```bash
python3 ~/.agents/specs/drafts/claude-code/decision-hook/scripts/decide.py doctor          # endpoint, models pulled, modes, memory, index, Ollama app settings
python3 ~/.agents/specs/drafts/claude-code/decision-hook/scripts/decide.py report --days 14 # per day, event, permission mode: outcomes, flags, p95 latency
python3 ~/.agents/specs/drafts/claude-code/decision-hook/scripts/build_index.py --report    # routing exemplars from every skill's evals/triggers.json
python3 ~/.agents/specs/drafts/claude-code/decision-hook/scripts/label.py harvest --since 2026-09-01
python3 ~/.agents/specs/drafts/claude-code/decision-hook/scripts/label.py review --set risk --n 20
python3 ~/.agents/specs/drafts/claude-code/decision-hook/scripts/label.py review --set risk --recheck
python3 ~/.agents/specs/drafts/claude-code/decision-hook/scripts/label.py stats --set risk
python3 ~/.agents/specs/drafts/claude-code/decision-hook/scripts/evaluate.py --set risk --model tev1:0.8b --calibrate --sweep
python3 ~/.agents/specs/drafts/claude-code/decision-hook/scripts/evaluate.py --set risk --model laya --labels ~/.agents/specs/drafts/claude-code/decision-hook/references/scenarios.jsonl   # the 126-call scenario corpus, no labeling needed
python3 ~/.agents/specs/drafts/claude-code/decision-hook/scripts/evaluate.py --set routing
python3 -m unittest discover -s ~/.agents/specs/drafts/claude-code/decision-hook/tests                      # 85 unit and fake-server cases, no tokens
DECISION_HOOK_HARNESS=1 python3 -m unittest discover -s ~/.agents/specs/drafts/claude-code/decision-hook/tests/harness   # 4 cases through the real claude CLI, about $0.50
```

**Measured state (2026-10-09, laptop):** the plumbing passes the harness tests; the judgment does not yet pass the success numbers. On the scenario corpus tev1:0.8b reaches recall 0.12 to 0.23 and laya 0.36 to 0.45; a nearest-neighbor head over `embeddinggemma` reaches 0.86 but spends 19 false escalations per 100, nearly all on scary-looking benign calls. Shadow stays the only sane mode until a judgment clears both numbers; `NOTES.md` and the spec hold the detail.

## Wiring

Until `tasks/SPEC-DECISION-HOOK.md` records the judgment clearing recall and the base-rate budget on real labels, this folder stays in `specs/drafts/`, and no station copies, configures or wires it. After the judgment passes, wiring is the user's call on each machine. The snippet below is what that wiring will look like once it has moved to `specs/claude-code/hooks/` and the station copy exists.

The hook entries read the harness payload on stdin:

```json
{"matcher": "Bash|Write|Edit|MultiEdit|NotebookEdit|mcp__.*",
 "hooks": [{"type": "command", "timeout": 3,
            "command": "python3 ~/.claude/hooks/decision-hook/scripts/decide.py --event pre-tool-use"}]}
```

`--event session-start` (SessionStart, `timeout: 20`) warms the model once so the first call is not a cold load. `--event user-prompt-submit` is the routing hint and is off by default.

## Reading the output

- **A permission prompt whose reason starts `decision-hook:`** names the option that fired (`destroy`, `exfil`, `creds`, `config`, `install`), its calibrated probability, and the option's wording. Judge the call on its merits; the model only raises the flag.
- **`report`** prints counts only. `skipped` means another model held Ollama's single slot or the memory budget refused a cold load; `timeout` means the 1.5 s client budget passed; `capped` means the session hit the escalation cap. A rising skip rate means the model is being evicted; a rising flag rate means thresholds drifted or the work changed shape.
- **`doctor`** fails on a non-loopback endpoint, a missing model tag, a missing routing index, or an endpoint that does not answer. Warnings name any mode set to `active`.
- **`evaluate`** reports held-out recall and false escalations per 100 calls, per stratum, and the fitted thresholds and Platt parameters. `--write-params` copies them into `references/risk.json`; nothing else changes thresholds.

## Config and state

- Config: `~/.config/decision-hook/config.json`, per machine, never committed. `references/config.example.json` is the full shape. Modes are per event and per permission mode: `off`, `shadow` or `active`. The built-in default is shadow for PreToolUse in every mode but bypassPermissions, and off for routing.
- State: `~/.local/state/decision-hook/` (0700): `decisions.jsonl`, `sessions/` (escalation counters), `labels/`, `evals/`. All 0600. `DECISION_HOOK_CONFIG`, `DECISION_HOOK_STATE` and `DECISION_HOOK_INDEX` relocate them for tests.
- Every candidate the labeler stores is scrubbed first: secrets by shape, then the station term list through the identifier hook's matching rule. Counts are printed; values never are. This is the first layer only; training data still passes the full sanitize step before any fine-tune.

## Safety rails

- The code has no path that emits allow, deny or block, and a property test holds that.
- Every failure (Ollama down, 404, bad reply, timeout, budget refusal, hook defect) exits 0 with no output and a logged reason.
- Shadow is the shipped state. Switching any mode to `active`, wiring the hook, raising `OLLAMA_MAX_LOADED_MODELS`, or adding a dependency is the user's call.
- With `OLLAMA_MAX_LOADED_MODELS=1` the hook yields: if another model holds the slot it skips and logs. It never evicts a running `local-model-task` model.
- Auto and dontAsk modes turn "ask" into a denial, bypass turns it into an allow. Keep auto and dontAsk in shadow unless the measured false-escalation rate is 0.5 per 100 or lower; never activate bypass.
