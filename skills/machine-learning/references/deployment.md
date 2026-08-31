# Deployment and operation

Getting the model into production and knowing when it has gone wrong. The
validation score is where the modeling work ends and the operating work begins,
and the gap between the two numbers is the subject of this file.

## Contents

- [The validation score is not the production number](#the-validation-score-is-not-the-production-number)
- [Serving shapes](#serving-shapes)
- [Train/serve skew](#trainserve-skew)
- [The single-source rule for features](#the-single-source-rule-for-features)
- [What to log at prediction time](#what-to-log-at-prediction-time)
- [Delayed labels](#delayed-labels)
- [Drift](#drift)
- [Detecting drift](#detecting-drift)
- [Monitoring that is worth having](#monitoring-that-is-worth-having)
- [Retraining triggers](#retraining-triggers)
- [Releasing a new model](#releasing-a-new-model)
- [Rollback](#rollback)
- [The model artifact](#the-model-artifact)
- [The pre-launch checklist](#the-pre-launch-checklist)

## The validation score is not the production number

**Never present a validation score as expected production performance.** It was
measured on data assembled by a batch process, from a population that has since
moved, with features computed by code that is not the serving code, on a
distribution the split may have flattered. Every one of those differences moves
the number, and all of them move it the same way.

State it as: "0.81 AUC on a held-out test set from January to March, against a
baseline of 0.68. Production performance will differ - the known risks are X and
Y, and the monitoring watches Z." That is a claim someone can hold you to and
that survives its first month.

## Serving shapes

| Shape | Prediction happens | Fits when | Main risk |
|---|---|---|---|
| Batch, scheduled | Ahead of the request, written to a table | Decisions are periodic, features update slowly | Predictions go stale between runs |
| On demand, synchronous | Inside the request | The input arrives with the request | Latency budget, feature availability |
| Streaming | On each event | Continuous decisions | State management, out-of-order events |
| Embedded (device, browser) | On the client | Offline or privacy constraints | Updating the model, drift you cannot see |

Batch is the right default and is chosen too rarely. It is simpler to build,
cheaper to run, trivially observable, and the features can come from the same
warehouse tables the training data came from - which removes an entire class of
skew. Choose online serving because the decision genuinely needs fresh input,
not because it sounds more modern.

## Train/serve skew

The most common reason a good model disappoints, and the hardest to see, because
each cause is invisible from inside training.

**Different code computes the features.** Training features come from SQL over
the warehouse, serving features from application code over a request payload.
The two implementations agree until one is changed. This is the single largest
source of skew and the fix is structural, below.

**Different data sources for the same value.** The warehouse column has been
cleaned, deduplicated and back-filled; the request payload has not. The
distributions differ before any code does.

**Time travel in training.** A feature was computed from data that did not exist
at the prediction moment. At serve time the honest version is weaker, so the
model relies on something it will not get.

**Different freshness.** Training used a value as of midnight; serving uses a
value that is up to 24 hours old, or one that is seconds old and therefore
noisier.

**Different preprocessing.** The scaler, encoder or imputer at serve time was
fitted differently, or the category mapping has drifted. Serializing the whole
pipeline as one artifact prevents this.

**Different defaults for missing values.** Training filled with the median;
serving fills with zero, or with whatever the caller sent.

**Feedback loops.** The model's own predictions change the data it later trains
on. A fraud model that blocks transactions never sees their outcomes; a
recommender only sees clicks on what it recommended. Left alone, the model
trains on a world it created and its measured performance detaches from reality.
The fix is to keep a small holdout of decisions made without the model, and to
log what was suppressed.

## The single-source rule for features

**One implementation of each feature, used by both training and serving.** Every
alternative degrades into two implementations that agree at first.

In practice this is one of three arrangements:

1. **Batch scoring from the same tables** that produced the training data. The
   simplest correct answer.
2. **A feature store or a shared feature library** that both paths call, with
   point-in-time correct reads for training and low-latency reads for serving.
3. **The transformation lives inside the serialized model artifact**, so serving
   passes raw input and the pipeline does the rest. This covers scaling,
   encoding and imputation, which is most of the skew surface, but not the
   upstream aggregates.

Whichever is chosen, add a test that computes a handful of features both ways and
asserts they match. It fails the day someone changes one path, which is exactly
when it is needed.

## What to log at prediction time

Logging only the prediction makes every later question unanswerable. Log, per
prediction, with an identifier that the outcome can later be joined to:

- The input features actually used, after preprocessing where feasible.
- The prediction, and the score behind it, not only the thresholded decision.
- The model version and the code version.
- The timestamp, and the freshness of each input that has one.
- Whether a fallback path was taken.

This is what makes drift detection, incident analysis and the next training set
possible. Retrofitting it after an incident means waiting a month for data.

## Delayed labels

The outcome usually arrives long after the prediction: a 90-day churn label
arrives in 90 days, a loan default in months, a fraud chargeback in weeks. Three
consequences.

1. **Performance monitoring lags.** By the time a drop is measurable, the model
   has been wrong for a full label period. Input monitoring is the early warning
   and is worth more than it looks.
2. **Proxy signals fill the gap.** The rate of positive predictions, the
   distribution of scores, downstream acceptance rates, manual override rates -
   all available immediately, none conclusive, together a usable tripwire.
3. **The training set is always old.** The most recent data cannot be labeled
   yet, so the model is trained on a world at least one label period behind.
   Account for it in the split and say so.

## Drift

Three kinds, with different symptoms and different fixes.

**Covariate drift.** The input distribution moves; the relationship between input
and target does not. A new marketing channel brings a different population. The
model is still correct in principle but is now extrapolating. Detectable from
inputs alone, which is why it is the first thing to monitor. Often fixed by
retraining on recent data.

**Prior drift.** The target's base rate moves. Fraud rises in December. The model
still ranks correctly but its calibration and its threshold are wrong.
Frequently fixed by re-thresholding rather than retraining.

**Concept drift.** The relationship itself changes: the same inputs now imply a
different outcome. A pricing change, a competitor, a regulation, a pandemic. Not
detectable from inputs at all - only from labels, which arrive late. Requires
retraining, and sometimes re-framing.

Drift also arrives as a step rather than a trend. A schema change, a unit change
(cents to dollars), an upstream bug filling a column with nulls, a vendor
changing a category taxonomy. These are the most common production failures in
practice and they look nothing like the textbook gradual drift, which is why data
validation on inputs belongs beside statistical drift detection.

## Detecting drift

| Signal | Method | Notes |
|---|---|---|
| Feature distribution | Population stability index, Kolmogorov-Smirnov, Wasserstein distance, or the simpler percentile comparison | Compare against the training distribution, per feature, on a fixed window |
| Categorical features | Chi-square, or the share of unseen categories | Unseen categories are usually a schema change |
| Prediction distribution | Mean predicted score, positive rate, score histogram | Immediate, no labels needed, catches most step changes |
| Data quality | Null rate, range violations, type changes, row counts | Catches the failures that are not drift at all |
| Performance | The chosen metric on labeled data | Conclusive and late |

Thresholds are conventions, not laws - population stability index above 0.2 is a
widely used alert level, and it is a starting point to calibrate against a few
months of history, not a rule. Test any threshold against past data and count how
often it would have fired: an alert that fires weekly gets muted, and a muted
alert protects nothing.

Feature-level drift alerts should be ranked by feature importance. A drifting
feature the model barely uses is not an incident.

## Monitoring that is worth having

Four layers, cheapest first, and the first two are non-negotiable:

1. **Operational.** Is it up, how fast, error rate, fallback rate.
2. **Data quality.** Schema, nulls, ranges, freshness, row counts. Most real
   incidents are here.
3. **Distribution.** Inputs and predictions against training, on the features
   that matter.
4. **Performance.** The metric, when labels arrive, segmented as well as overall.

Segmentation matters: aggregate performance can be stable while the model has
collapsed on a segment that represents most of the business value. Monitor the
segments the decision cares about.

## Retraining triggers

Choose deliberately, write it down, and automate whatever is chosen.

- **Scheduled.** Retrain every N weeks. Simple, predictable, and mismatched to
  reality in both directions - too often is churn, too rarely is stale. A
  reasonable default when nothing is known yet.
- **Performance-triggered.** Retrain when the monitored metric falls below a
  stated threshold. The most honest trigger and the slowest, because it waits for
  labels.
- **Drift-triggered.** Retrain when input drift exceeds a threshold. Fast, and
  prone to firing on drift that does not affect the decision.
- **Event-triggered.** A known change - a new product, a new market, a pricing
  change - is the strongest signal and is usually known in advance by someone
  who is not on the modeling team.

In practice: a schedule as the floor, plus performance and drift triggers on top,
plus a documented path for the event case.

Retraining is not free of risk. Retraining on data the model itself influenced
bakes in the feedback loop; retraining on a period containing an incident teaches
the incident. Every retrained model goes through the same evaluation gate as the
first one, including the baseline comparison, and it is compared against the
model currently in production on the same recent test window.

## Releasing a new model

1. **Offline evaluation** against the incumbent on the same recent holdout, with
   the baselines reported.
2. **Shadow mode.** The new model scores live traffic without acting. Compares
   the prediction distributions and catches skew, latency and crashes without
   risk. The highest-value step and the most often skipped.
3. **Canary or split.** A small share of traffic gets the new model, with the
   decision metric watched, not just the model metric.
4. **Full rollout**, with the previous version kept ready.

Whether a difference measured during a canary is real is an inference question,
and this skill does not answer it. What belongs here is making sure the
comparison is fair: same population, same period, same features, same threshold
policy.

## Rollback

Every deployment needs an answer to "how do we turn this off". Concretely:

- The previous model artifact is retained and loadable, not rebuilt from source.
- The switch is configuration, not a redeploy.
- There is a documented non-model fallback - the old rule, a default value, a
  human queue - for when both models are broken or the feature pipeline is down.
- The rollback is tested before launch, not during the incident.

A model that cannot be rolled back is a model that will be left running while
broken, because the alternative is worse.

## The model artifact

What ships is not the weights alone:

- The serialized pipeline, preprocessing included.
- The model and code versions, and resolved dependency versions.
- The data version and the seed.
- The training and validation metrics, the baselines, and the split definition.
- The expected input schema, with types and ranges.
- The threshold and the policy behind it.
- The known limitations and the population it should not be used on.

Serialization formats carry their own hazards. Pickle executes code on load, so a
pickled model is a code artifact and must be treated with the same trust as
source; formats such as ONNX are safer to exchange but do not always round-trip
custom preprocessing. Whichever is used, load the artifact in a clean environment
and re-score a fixed sample as an acceptance test, since a silent version
mismatch changes predictions without raising.

## The pre-launch checklist

- The decision it serves is written down, and the consumer has seen a sample of
  the output.
- Features are computed by one implementation, and a test asserts training and
  serving agree.
- The artifact carries its versions, seed, schema, threshold and limitations.
- Predictions and inputs are logged with an identifier that outcomes can join to.
- Monitoring covers operations, data quality, distributions and performance.
- Retraining trigger and cadence are chosen and automated.
- Rollback is a configuration change and has been tested.
- There is a written answer to "what would make this wrong", and the monitoring
  watches at least the top item on it.
