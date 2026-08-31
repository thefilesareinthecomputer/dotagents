# notes behavioral battery

Trigger evals (`skills/notes/evals/evals.json`, run by skill-creator's
`run_eval.py`) measure only whether the skill fires. They compute a trigger rate
and never read the `expectations` field. That cannot catch the failures this
suite exists for: a sweep that writes the root docs from an unsettled plan and
then revisits them, or one that wanders outside the six paths it governs.

`run_battery.py` builds a throwaway repo in a known-bad state, runs the skill
against it with `claude -p`, and grades the recorded tool sequence.

```bash
python3 tests/notes-behavior/run_battery.py --workdir <scratchpad>/nb
python3 tests/notes-behavior/run_battery.py --workdir <scratchpad>/nb --scenario legacy
python3 tests/notes-behavior/run_battery.py --workdir <scratchpad>/nb --build-only
python3 tests/notes-behavior/run_battery.py --workdir <scratchpad>/nb --grade-only
```

`--workdir` is destroyed and rebuilt on every run. Never point it at a real
repo: the skill under test writes documentation files, and the run uses
`--dangerously-skip-permissions` because it is non-interactive.

## The fixture

`tasks/plan.md` at 451 lines against a ~400 budget and `tasks/todo.md` at 121
against ~100, so the size gate has to fire. Inside them: two finished items that
must relocate, one in-progress item that must survive, a settled storage
decision that belongs in `SPEC.md`, a verbose rationale whose reasoning must be
preserved while its narration is cut, and a live gotcha that must stay hot.
Alongside: a shipped `tasks/SPEC-FEATURE-WIDGET.md` that must be moved with
`git mv`, an immutable past-day cold file, a `SPEC.md` carrying two claims the
session invalidated, and `AGENTS.md` plus `CHANGELOG.md` as out-of-scope decoys.
The `legacy` scenario swaps the cold store for a single `tasks/plan-completed.md`
append log, which the skill must flag rather than convert.

## Assertions

Ordering is only visible in the tool sequence, which is why the grader parses
the stream-json transcript rather than diffing the tree.

| | Assertion | Source |
|---|---|---|
| A1 | Root docs written once, in one uninterrupted block, after the bundle | tool sequence |
| A2 | Nothing written outside the six governed paths | tool sequence |
| A3 | The h1-h5 heading map runs before the first root-doc write | tool sequence |
| A4 | The shipped feature spec moves via `git mv` (standard layout) | tool sequence |
| A5 | Every pre-existing edited file was read first | tool sequence |
| B1 | The finished items reached the cold store this layout has | tree |
| B2 | Finished entries left `tasks/plan.md`, leaving a pointer | tree |
| B3 | In-progress work survived, under its own name | tree |
| B3b | The live gotcha stayed hot | tree |
| B4 | The reason behind the settled decision reached `SPEC.md` | tree |
| B4b | Both claims the session invalidated are gone from `SPEC.md` | tree |
| B5 | `AGENTS.md` and `CHANGELOG.md` untouched | tree |
| B6 | The past-day cold file is byte-identical (legacy: log not converted) | tree |
| B7 | The shipped feature spec is archived, or flagged where it cannot be | tree |

A1 allows a later bounded trim of a `tasks/` file, which the skill permits at
step 7: it cannot invalidate a root doc. What it rejects is a `tasks/` write
landing between two root-doc writes, which means the root docs were written from
an unsettled bundle.

Content assertions match anchors a faithful rewrite has to keep - an item's name,
a path, the reason behind a decision - not sentinel strings. The skill is
supposed to rewrite this prose, so sentinels planted in it fail on correct
behavior. Files that must NOT change are the exception and do carry exact
sentinels.

Final line counts are printed rather than asserted. The budget gate's pass
condition allows a user ruling instead of a cut, and a non-interactive run has
nobody to rule, so a file ending over budget is a result to read rather than an
automatic failure.

Exit 0 means every assertion passed. Model is pinned to `claude-opus-5` in the
script: the point is to test the model that actually runs the sweep.
