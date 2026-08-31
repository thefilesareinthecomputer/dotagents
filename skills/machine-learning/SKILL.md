---
name: machine-learning
description: Builds, ships and operates predictive models - framing the problem, constructing features and splits, training reproducibly, serving, and knowing when to retrain. Use when deciding whether something is an ML problem, defining a target and the baseline it must beat, designing splits for time-ordered or grouped data, choosing a model family and a tuning budget, reviewing training code, or diagnosing a model that validated well and disappoints in production - train/serve skew, drift, retraining triggers. Covers leakage prevention, imbalance, encoding and missingness. Not for whether an improvement is real (statistics), stack selection or LLM, RAG and agent design (ai-engineering), or pipelines and warehouses (data-engineering). Ships an offline AST auditor (scripts/ml_check.py).
license: MIT
---

# machine-learning

**A validation score is a claim about a construction, not a measurement of the
world.** It is only worth what the construction is worth, and most of the time
the construction is where the mistake is. A scaler fitted before the split, a
random split of dated rows, a target column that survived into the feature
matrix, a hyperparameter search that quietly consumed the test set: each of
these produces a number that is both excellent and meaningless, and none of them
looks wrong in the code.

So the order of work is fixed. Decide what is being predicted and what beats
doing nothing, construct the data so that no future or test information can
reach training, then train, and only then care which algorithm won. Algorithm
selection is the most documented and least decisive part of this, and it is the
part practitioners spend most of their time on.

Four questions answered before any model is fitted:

1. **What decision does this change?** If no decision changes, stop.
2. **What is the baseline?** Majority class, last observed value, the rule the
   business already uses. Beat it or the model is not worth operating.
3. **Is the information available at prediction time?** A feature that only
   exists after the event is not a feature, it is the answer.
4. **What would make this wrong in production?** Answer it now, in writing, so
   the monitoring has something to watch.

## First: which situation is this?

**Framing a new problem.** Work `references/framing.md` before touching data.
The target definition and the baseline are the two decisions everything else
inherits, and both are cheap now and expensive after a quarter of modeling.

**Building the data.** `references/data-construction.md` is the largest and most
load-bearing reference: split design, the leakage taxonomy, imbalance, encoding,
missingness, and feature engineering that survives contact with serving.

**Training and tuning.** `references/training.md` gives model family by problem
shape, what each family assumes and where it fails, tuning strategy and its
budget, and the reproducibility record.

**Shipping and operating.** `references/deployment.md` covers serving shapes,
train/serve skew, the three kinds of drift and how each is detected, retraining
triggers and rollback.

**Reviewing someone's training code, or your own.** Run the checker below, then
read `references/pitfalls.md` for the defects it finds and the larger set it
cannot see. Do not start from the algorithm - start from the split.

**"The model scored 0.94 in validation and is useless in production."** That is
the signature of one of four things, in descending order of likelihood: leakage
in construction, a split that did not match the data's structure, train/serve
skew, or drift since training. `references/pitfalls.md` sorts them; the checker
finds the first two mechanically.

## The seam with statistics

These two skills overlap more than any other pair, so the boundary is drawn on
one rule: **instrument versus artifact**. `statistics` owns whether a result is
real; this skill owns how the thing that produced it was built.

| Concern | Owner |
|---|---|
| Is this improvement real, and what is the CI on the metric | `statistics` |
| Is the model calibrated | `statistics` |
| Multiplicity across many tuning runs | `statistics` |
| Choosing a metric for the decision at hand | `statistics` |
| **Preventing** leakage with pipeline structure | `machine-learning` |
| Feature engineering, encoding, target definition | `machine-learning` |
| Model family selection, tuning strategy, training loops | `machine-learning` |
| Serving, drift monitoring, retraining triggers | `machine-learning` |

Leakage sits on the seam and is deliberately shared: `statistics` defines it and
detects it in a result, this skill prevents it structurally. Two decimal places
of difference between models is an inference question, not a modeling one - hand
it over rather than half-answering it here.

## What this is not

- **Not stack selection.** Which framework, which serving layer, which vector
  store belongs to `ai-engineering` and its dated corpus.
- **Not LLM or agent work.** Prompting, RAG and agent design are
  `ai-engineering`'s. This is supervised and unsupervised modeling on tabular,
  text and image data.
- **Not a data platform.** Pipelines, warehouses and dataframe engines are
  `data-engineering`'s.
- **Not deep learning practice.** Training loops, augmentation, checkpoint
  discipline and distributed training are a different literature and are out of
  scope here. What is in scope applies to them anyway: the split, the baseline,
  the seed, the leakage taxonomy.
- **Not a maths reference.** It states what an algorithm assumes and where it
  fails, not how it is derived.
- **Not a compute engine.** It reasons about training code and audits it; it
  does not train models.

## Gate the code

EXECUTE:

```bash
python3 scripts/ml_check.py train.py
python3 scripts/ml_check.py notebooks/model.ipynb --json
python3 scripts/ml_check.py src/ --recursive --warnings-as-errors
```

Stdlib only, offline, and it never imports or runs what it reads: audited
training code is untrusted input. Exit 1 on any error, and on warnings too under
`--warnings-as-errors`. Notes never affect the exit code.

| Code | Defect | Severity |
|---|---|---|
| `FIT_BEFORE_SPLIT` | a scaler, encoder or imputer is fit on the full frame before the split | error |
| `TEMPORAL_SPLIT_MISSING` | a datetime column is present and the split is random, so training saw the future | error |
| `TEST_USED_IN_TUNING` | the test split appears in a search, fit or early-stopping call | warning |
| `NO_RANDOM_STATE` | a split, shuffle or stochastic estimator with no seed, so the result is not reproducible | warning |
| `TARGET_IN_FEATURES` | the target column, or a trivially derived copy, remains in the feature matrix | warning |
| `NO_BASELINE` | a model is scored with nothing to compare it against | warning |
| `RESAMPLE_BEFORE_SPLIT` | SMOTE or similar applied before the split, leaking synthetic neighbors across it | warning |
| `METRIC_MISMATCH` | accuracy is the only metric and nothing acknowledges class balance | warning |
| `GROUP_LEAK` | repeated entity ids span train and test with no group-aware split | warning |

The first two are errors because they are the two that most reliably produce a
model that looks excellent and fails in production.

Known limits, stated so the checker is not over-trusted. It reads structure, so
it cannot see data: `METRIC_MISMATCH` approximates class balance by asking
whether accuracy is the only metric and nothing in the file handles imbalance,
and `GROUP_LEAK` approximates repeated entities by looking for an id-shaped
column that is never dropped. It follows one file at a time, so a split in one
module and a fit in another read as unrelated. On notebooks it parses code cells
in cell order, which is not execution order, so it emits a note saying the
ordering assumption is unverifiable and downgrades the order-dependent findings
to warnings. It is a tripwire for the mechanical half, not a review. Per-code
detection rules and their blind spots are in `references/pitfalls.md`.

## Boundaries

**Always**

- Name the baseline before reporting a model's score.
- State the split strategy and why it fits the data's structure.
- Record the seed, the data version and the code version together.
- Say what would make the model wrong in production, not only how it scored.

**Ask first**

- Adding any third-party dependency to the skill itself.
- Promoting a checker rule from warning to error.

**Never**

- Report a score without saying what it beat.
- Present a validation score as expected production performance.
- Recommend a model for a consequential human decision - credit, hiring,
  medical, criminal justice, housing, insurance - without stating the fairness
  and recourse questions this skill does not answer: which groups the error rate
  differs across, what the subject is told, and how a wrong decision is appealed
  and reversed. Those questions are out of scope here, and a model that ships
  without them is a liability regardless of its metrics.
- Run the code being audited. Static analysis only, since audited code is
  untrusted input.

## Where the rest lives

| File | Contents |
|---|---|
| `references/framing.md` | Whether this is an ML problem at all, the decision it serves, target definition and its timing, the unit of prediction, the baseline ladder, cost of errors, feasibility, problem shapes |
| `references/data-construction.md` | Split design by data structure, the leakage taxonomy with the fix for each, imbalance, encoding, missingness, feature engineering that survives serving, point-in-time correctness |
| `references/training.md` | Model family by problem shape with what each assumes and where it fails, tuning strategy and budget, nested validation, reproducibility record, when to stop, ensembling |
| `references/deployment.md` | Serving shapes, train/serve skew and its sources, covariate/prior/concept drift and detection, delayed labels, retraining triggers, shadow and canary, rollback |
| `references/pitfalls.md` | The audit catalog: one entry per checker code with its detection rule, why it matters and what clears it, plus the defects no static checker can find |

## Verify

```bash
python3 -m unittest discover -s tests
```

`tests/fixtures/defective/` holds one script per catalog code, each of which
must produce its own code and no other. `tests/fixtures/clean/` holds correct
scripts that must produce nothing at all, and that is the test that matters: a
checker that fires on correct code gets muted, and a muted checker protects
nothing. Fixtures are read, never executed.
