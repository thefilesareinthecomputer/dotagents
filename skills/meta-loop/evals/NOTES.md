# meta-loop trigger eval notes

## The eight positive cases are waived

Run 2026-08-23, 15 cases at 3 votes on `claude-sonnet-5`: 7 passed, 8 failed.
Every negative passed at a 0.0 trigger rate. Every positive failed at a 0.0 trigger rate - nothing fired at all.

**That is the expected result and it is not a defect to fix.**
The full-roster baseline of 2026-08-13 measured recall 31/207 against precision 161/161 across all 28 skills, so a near-zero floor is a property of the model rather than of this description.
Orchestration-shaped skills sit at the bottom of it: an earlier run scored meta-loop 0/3 with its own trigger phrase quoted verbatim in the description.

The user invokes this skill by name. The positives are kept because they document the situations the skill is for, which is what a future author needs when editing the description. They are not a target to optimize against.

**Do not rephrase the positive cases into invocation-shaped prompts to move the number.** That games the meter and destroys the cases as a record of real usage.

## What is enforceable here

The seven negatives are the half that measures cleanly, and they are the ones to keep green.
They draw the boundaries against a single-step edit, an indivisible large task, a two-step chain, a mechanical sweep, a lone delegation, and the two `skill-authoring` questions about agent definitions.
A negative starting to fire is a real regression and means the description has grown into a sibling's territory.

## Running the set

`run_eval.py` cannot be invoked by path; it fails on `ModuleNotFoundError: No module named 'scripts'`.

    cd <skill-creator skill directory>
    python3 -m scripts.run_eval \
      --eval-set <repo>/skills/meta-loop/evals/triggers.json \
      --skill-path <repo>/skills/meta-loop \
      --model claude-sonnet-5 --runs-per-query 3

Pin `--model`. Left unset it inherits the session model, which makes the numbers incomparable to the baseline.

## Related

The harness scores firing only. It never reads `expectations`, and it kills each run at a 30 second timeout, so it never observes the work.
Editing this skill's procedure changes nothing this harness measures - the body needs its own verification, which for the 2026-08-23 durable-state change was a cold-read probe against `tasks/SPEC-META-LOOP-DURABLE-STATE.md`.
