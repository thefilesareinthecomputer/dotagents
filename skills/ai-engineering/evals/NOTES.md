# Trigger eval caveats

Waived positives (user, 2026-09-15, after the three-skill merge): the six
build- and write-mode should-trigger cases - `log-what-broke`,
`check-for-staleness`, `documented-flag-does-not-exist`, `build-me-an-agent`,
`add-an-ai-feature-to-an-existing-app`, `review-a-proposed-architecture` -
score 0% recall in the `run_eval.py` harness and are accepted as-is. A
hand-replayed probe showed the model's first move on these action-shaped
prompts is to start working (Bash), not to consult a skill, and the harness
scores anything but a first-call Skill invocation as a miss. Precision is the
enforceable half: all six should-NOT cases pass and must keep passing.

Do not rephrase the waived cases into invocation-shaped prompts to move the
number - they document real usage. Read runs against the 2026-09-15 result
(5/11 recall, 6/6 precision), not against 100%.
