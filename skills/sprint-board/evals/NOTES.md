# Trigger eval notes

## Expected score: 6/16 (waived 2026-08-07)

The ten failing positives all name an existing board file. They are expected to
fail and should not be chased.

**Measured, twice.** Two description versions - a 379-char one and a 991-char one
written to the situation-clause pattern with MUST framing - both scored 6/16. The
description is not the lever.

**Ground-truth probe** with the real skill installed, outside this harness, on a
real board fixture:

| Prompt shape | Tool sequence | Skill fired |
|---|---|---|
| `Use the sprint-board skill to audit user-stories.md` | `Skill` first | yes |
| Goal stated, no file present | `Skill` first | yes |
| `Go through user-stories.md and tell me what's wrong with it` | `Bash, Bash, Read` | no |

So the skill is invocable and does self-invoke when nothing needs opening. When a
board file is named, the model reads it and writes items from its own instincts
instead. This matches the documented pattern that procedure-shaped skills do not
model-invoke, because the model believes it already knows the procedure.

**Resolution:** explicit `/sprint-board` invocation is the primary path, by the
user's decision. Do not inflate the description to chase these cases - that is
the anti-pattern the house profile names, and it was measured not to work here.

## Harness caveat

`run_eval.py` counts a hit only when the skill is the **first** tool call: its
detection returns on the first `tool_use` event whatever that event is. Any
prompt that requires locating a file therefore cannot pass, even when the skill
does load a moment later. For this skill the harness verdict and ground truth
agreed, but a future score change should be confirmed by direct probe rather than
trusted from the number alone.

Every entry in `triggers.json` is run as a live prompt, so the file holds only
real cases - notes go here.
