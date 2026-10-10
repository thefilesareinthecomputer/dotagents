# Reading this skill's trigger evals

On 2026-10-08, with claude-sonnet-5 and one run per case, `run_eval.py` scored
the four should-NOT cases 4/4 and the should-trigger cases 1/4. Two different
descriptions gave the same result.

The misses come from the harness, not the description. Three of the four
should-trigger cases name material that does not exist in the probe's empty
directory ("the API notes", "this repo", "this ticket list"), and the harness
scores a miss as soon as the first tool call is anything but the skill. In a
replay of the qwen extraction case with the skill installed and an
`API_NOTES.md` present, the first call invoked the skill (then named
`model-task`), as read from `claude -p --output-format stream-json`.

## Consequences

- The should-NOT cases are the enforceable half. They check that the skill
  does not trigger on requests for codex-task, plain summaries, model-install
  advice or Ollama debugging, and they need to keep passing.
- Judge recall by replaying a case with its material present and reading the
  tool sequence from stream-json, rather than from this harness's
  should-trigger scores.
- Do not reword the should-trigger cases into invocation-shaped prompts to
  raise their scores. That games the metric, and the cases would stop
  documenting real requests.
