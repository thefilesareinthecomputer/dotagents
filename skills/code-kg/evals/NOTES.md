# Reading this skill's trigger evals

Measurement caveat, verified 2026-08-14 by replaying a probe by hand:
`run_eval.py` scores a miss the moment the probe's first tool call is anything
but Skill or Read. On repo-shaped queries ("find dead code in this repo") the
model's correct first move is filesystem exploration - the replayed probe
opened with `Bash: pwd && ls -la` - so every should-trigger case reads 0%
regardless of how good the description is. The exploration-then-skill sequence
this skill actually lives in is invisible to the harness.

Consequences:

- The should-NOT cases are the enforceable half: they draw the boundary
  against `obsidian-kg` (vaults, markdown docs trees) and against review and
  debugging work, and they measure cleanly. Keep them passing.
- Judge recall changes by diffing the description against the positive cases
  by hand, or by probing with a real repo present and reading the full tool
  sequence, not by this harness's positive-case numbers.
- Do not inflate the description or rephrase the positive cases into
  invocation-shaped prompts to make the numbers move; that games the meter
  and degrades the cases as documentation of real usage.
