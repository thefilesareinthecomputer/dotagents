# Framing

The decisions made before any data is loaded. All of them are cheap now and
expensive to revisit after a quarter of modeling, because everything downstream
inherits them.

## Contents

- [Is this an ML problem](#is-this-an-ml-problem)
- [The decision it serves](#the-decision-it-serves)
- [Defining the target](#defining-the-target)
- [Target timing, which is where leakage starts](#target-timing-which-is-where-leakage-starts)
- [The unit of prediction](#the-unit-of-prediction)
- [The baseline ladder](#the-baseline-ladder)
- [Cost of errors](#cost-of-errors)
- [Feasibility](#feasibility)
- [Problem shapes](#problem-shapes)
- [What to write down](#what-to-write-down)

## Is this an ML problem

Machine learning is worth its operating cost when all of these hold. If any one
fails, name it and stop.

1. **A pattern exists and is not expressible as a rule.** If the relationship
   can be written as twenty lines of `if`, write the twenty lines. They are
   auditable, they do not drift, and nobody has to monitor them.
2. **The pattern is stable enough to outlive training.** A pattern that changes
   faster than the retraining cycle produces a model that is wrong by the time
   it ships.
3. **Historical examples exist with outcomes attached.** No labels, no
   supervised learning. Collecting them deliberately is a legitimate first
   project, and often the whole project.
4. **Errors are survivable.** A wrong prediction has a cost; if any single wrong
   prediction is catastrophic and unappealable, the answer is a rule with a
   human in front of it.
5. **The output reaches a decision.** A model whose output nobody acts on is a
   dashboard, and a dashboard is cheaper to build directly.

Three cases that look like ML and are not: a reporting question ("how many
customers churned last quarter") which is a query, an optimization question
("what is the cheapest route") which is a solver, and a causal question ("will
this discount cause more purchases") which needs an experiment. A supervised
model answers "what is associated with what", and treating that association as
causal is the most common way modeling work gets misused after it ships.

## The decision it serves

Write one sentence: **"When ___ happens, ___ will use this prediction to decide
___ instead of ___."** Everything mechanical follows from it.

- Who consumes it decides the serving shape - a nightly list is a batch job, a
  checkout decision is an online service.
- When they consume it decides which features exist, because a feature that
  arrives after the decision moment cannot be used.
- What they do with it decides the metric and the threshold. A ranked list of
  the 100 accounts a team can call this week is a top-k problem, not a
  classification problem, and its metric is precision at 100.

If the sentence cannot be written, the project has no consumer.

## Defining the target

The target is a modeling artifact, not a fact of nature. Two teams predicting
"churn" on the same data usually mean different things.

- **Make it explicit and testable.** "Churn" becomes "no purchase in the 90 days
  following the prediction date, among accounts active on that date". Now it can
  be computed, and two people compute the same thing.
- **Prefer the outcome to its proxy.** Clicks proxy for interest, complaints
  proxy for dissatisfaction, a manual review flag proxies for fraud. Every proxy
  carries the bias of the process that produced it: a fraud label built from
  investigated cases teaches the model to predict which cases get investigated.
- **Check the base rate before anything else.** A 0.3 percent positive rate
  changes the metric, the split, the sample size and possibly the decision to
  proceed. Compute it first, per relevant segment, not only overall.
- **Beware targets defined by the current system.** If the label comes from a
  rule engine's decisions, the ceiling is that rule engine. Reproducing it
  exactly is the expected result, not success.
- **Decide the horizon deliberately.** "Will churn eventually" is unlearnable
  and unactionable. A 30-day horizon and a 180-day horizon are different
  problems with different features and different achievable accuracy.

## Target timing, which is where leakage starts

Draw a timeline for one row before writing any query.

```
   feature window            prediction         label window
[----------------------)         |          [----------------)
        past                 decision              future
                              moment
```

Every feature is computed from the feature window only. The label is computed
from the label window only. A gap between the prediction moment and the start of
the label window is often required: if the decision takes a week to act on, a
label that starts the next day is not the thing being decided.

The failures this drawing prevents:

- **Post-outcome features.** `cancellation_reason` is populated when the account
  cancels. Included, it produces a near-perfect model and no value at all.
- **Aggregates computed over all time.** `customer_lifetime_value` computed
  today includes the future relative to a row dated last March. Every aggregate
  needs an as-of date.
- **Slowly changing attributes read as current.** The customer's current segment
  is not the segment they were in at the prediction moment. Reading current
  state is time travel unless the attribute is genuinely immutable.
- **Labels that overlap the feature window.** A 30-day feature window ending
  after the label starts means the features already describe the outcome.

The single test: **could this value have been computed, with the data available,
at the prediction moment, without knowing the outcome?** Anything that fails it
is not a feature.

## The unit of prediction

One row is one what: one customer, one customer-month, one transaction, one
session, one customer-product pair. Fixing this early prevents two later
problems.

- **Duplicates and repeated entities.** If the unit is one transaction but the
  same customer appears 400 times, a random split puts that customer on both
  sides and the score is optimistic. Split by the entity instead, or aggregate
  to one row per entity. See `data-construction.md`.
- **Grain mismatch with the decision.** Predicting per transaction while the
  decision is per customer means someone will average the predictions, and the
  average of 400 transaction scores is not the customer's risk.

State the unit as a sentence, the way a fact table's grain is stated, and check
that the primary key of the assembled frame matches it exactly.

## The baseline ladder

**A model's score is meaningless alone.** Climb the ladder until it stops being
cheap, and report every rung reached alongside the model.

| Rung | Baseline | Applies to |
|---|---|---|
| 0 | Predict the majority class, the mean, or the median | Any supervised problem |
| 1 | Predict the last observed value, or the seasonal naive value from one period ago | Anything time-ordered |
| 2 | The rule the business already uses, scored on the same split | Anywhere a manual process exists |
| 3 | One feature and a simple model - logistic regression, a depth-3 tree | Anything |
| 4 | The model currently in production, re-scored on the same split | Any replacement |

Rung 4 is the one people skip, and it is the only baseline that answers the
question that gets asked in review. Rung 1 on a time series routinely beats
substantial modeling effort, which is why it must be computed before that effort
is spent, not after.

The baselines must be scored on the same split, with the same metric, and
reported in the same table. A model that beats rung 0 by a wide margin and rung
1 by nothing has learned the seasonality and nothing else.

## Cost of errors

Both error types have a price, they are rarely equal, and the ratio decides both
the metric and the threshold.

Write the confusion matrix with costs in it before choosing a threshold:

|  | Predicted positive | Predicted negative |
|---|---|---|
| **Actually positive** | value of catching it | cost of missing it |
| **Actually negative** | cost of the false alarm | 0 |

A fraud false negative costs the transaction amount; a false positive costs a
declined legitimate customer, which has a churn cost attached. A model that
optimizes accuracy on this problem optimizes neither. The threshold is a
business decision informed by these numbers, chosen on validation data, and
re-examined whenever the costs change.

Two constraints belong here as well. **Capacity**: if the team can call 100
accounts a week, the metric is precision at 100 and everything below rank 100 is
irrelevant. **Latency and cost per prediction**: an accurate model that takes
400ms in a 50ms budget does not ship.

## Feasibility

Before modeling, three checks that end projects early and cheaply.

1. **Does the signal exist?** Fit the simplest possible model on a sample. If it
   lands at the base rate, more features or a bigger model rarely rescue it -
   look for a missing data source instead.
2. **Is the data available at serve time, from the same source, with the same
   freshness?** A feature computed in the warehouse from a nightly load cannot
   be recomputed inside a 50ms request unless something serves it. This kills
   more features than any modeling constraint.
3. **How many examples of the rare class exist in absolute terms?** Percentages
   mislead. A million rows at 0.05 percent is 500 positives, which supports a
   simple model and will not support a tuned one, and the confidence interval
   around any metric computed from them is wide.

## Problem shapes

The shape determines the split, the metric family and the model families worth
trying. Naming it wrong is a framing error that survives all the way to
production.

| Shape | One row predicts | Watch for |
|---|---|---|
| Binary classification | One of two outcomes | Base rate; accuracy is the wrong metric below roughly 20 percent positives |
| Multiclass | One of k outcomes | Class imbalance across k; whether classes are ordered, which makes it ordinal regression |
| Multilabel | Any subset of k tags | Metrics differ from multiclass; per-label base rates vary enormously |
| Regression | A continuous quantity | Skew and outliers; whether the error should be absolute or relative |
| Ranking | An ordering within a group | Group-aware splits are mandatory; the metric is top-k, not pointwise |
| Time series forecasting | A future value | Split forward in time only; the naive baseline is strong |
| Anomaly detection | Outlier or not | Usually no labels, so evaluation is the hard part, not detection |
| Clustering | A group assignment | No ground truth; the result must be validated against a decision, not a score |
| Survival | Time until an event | Censoring; rows whose event has not happened yet are not negatives |

Two shapes are commonly misfiled. **Ranking as classification**: scoring each
item independently and sorting them optimizes the wrong thing when the decision
is "which 10 of these 500". **Survival as classification**: labeling everyone
who has not churned yet as a negative discards the information that they have
only been observed for two weeks.

## What to write down

One page, before modeling, revisited when any of it changes:

- The decision sentence and who consumes the prediction.
- The target definition, its horizon, and its base rate overall and by segment.
- The unit of prediction and the primary key that enforces it.
- The prediction-moment timeline and the as-of rule for every aggregate.
- The baselines reached and their scores.
- The metric, the threshold, and the cost matrix behind them.
- What would make this model wrong in production.

The last line is the one that makes monitoring possible. Written before the
model exists, it is an honest list of assumptions; written afterwards, it is a
rationalization of whatever the model happened to learn.
