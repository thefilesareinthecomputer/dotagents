# Evaluating a predictive model

An application of the core to models. The frame throughout is that **a model is
a measurement instrument**, and every question here is an inference question -
is this number real, how sure can we be, what would overturn it. Building the
model, engineering its features and serving it are a different job and are not
covered here.

## Contents

1. [Split discipline](#1-split-discipline)
2. [Cross-validation](#2-cross-validation)
3. [Leakage](#3-leakage)
4. [Choosing the metric](#4-choosing-the-metric)
5. [The decision threshold is not 0.5](#5-the-decision-threshold-is-not-05)
6. [Imbalance](#6-imbalance)
7. [Calibration](#7-calibration)
8. [Baselines](#8-baselines)
9. [Is the improvement real?](#9-is-the-improvement-real)
10. [Reporting](#10-reporting)

## 1. Split discipline

Three sets, with three distinct jobs, and the third one is the one people
overspend:

- **Training** fits the parameters.
- **Validation** chooses between configurations. Every comparison, every
  hyperparameter, every threshold, every feature set is decided here.
- **Test** is measured once, at the end, to estimate what happens next.

Rules that make the estimate mean something:

- **Split before anything touches the data.** Scaling, imputation, encoding,
  feature selection and outlier removal are all fitted on the training fold
  only. A scaler fitted on everything has already told the model about the test
  set's distribution.
- **Split on the unit that will be independent in production.** By customer, by
  patient, by document, by session. If a unit appears in both sets, the model
  memorizes rather than generalizes and the score is inflated.
- **Split by time when time exists.** Fit on earlier, evaluate on later, always.
  A random split of time-ordered data lets the model interpolate between rows it
  has seen on either side, which production will never allow.
- **Every look at the test set spends it.** Tuning against test scores turns the
  test set into a validation set, and its estimate becomes optimistic by the
  amount of tuning done. Cawley and Talbot (*Journal of Machine Learning
  Research*, 2010) is the reference for how large that selection bias gets.

## 2. Cross-validation

Repeated splitting, so the estimate does not depend on one arbitrary partition
and so it comes with a spread.

- **k-fold, k = 5 or 10.** Higher k means less bias and more compute and more
  correlation between folds.
- **Stratified** for classification, so each fold keeps the class balance.
- **Grouped** whenever rows share a unit, so a unit never straddles folds. This
  is the same requirement as section 1 and is the most commonly skipped one.
- **Time-series splits** for ordered data - expanding or rolling origin, never
  shuffled.
- **Nested** when hyperparameters are tuned: an inner loop selects, an outer
  loop estimates. Tuning and estimating in the same loop biases the estimate
  upward, quantified in Varma and Simon (*BMC Bioinformatics*, 2006).

**Report the spread, not just the mean.** The fold-to-fold standard deviation is
information, and a mean of 0.84 across folds ranging 0.71 to 0.93 is a different
result from one ranging 0.83 to 0.85. Note that the naive interval across folds
understates uncertainty because the folds share training data; treat it as a
lower bound on the uncertainty rather than a proper confidence interval.

## 3. Leakage

Information available at evaluation time that will not exist at prediction time.
It is the defect that produces implausibly good results, and the reason a metric
should be disbelieved before it is celebrated.

The catalog, in rough order of frequency:

- **Preprocessing fitted before the split.** Scaling, imputation, target
  encoding, feature selection, dimensionality reduction, resampling for balance.
- **A feature derived from the outcome.** Sometimes obvious, often not - a field
  populated only after the event occurs, a status that only takes its value once
  the outcome is known, an identifier assigned by a downstream process.
- **Future information in a time-ordered dataset.** Any aggregate computed over
  the whole period, including a mean, a rank, or a "total to date" that reaches
  past the prediction point.
- **Duplicate or near-duplicate rows** landing on both sides of the split.
- **The same unit on both sides** - the grouped-split failure.
- **A target computed with a look-ahead window** shorter than the gap between
  training and deployment.
- **Test-set reuse across many experiments**, which is leakage through the
  analyst rather than the code.

**The detection habit: when a result is far better than the problem should
allow, look for leakage before believing it.** Ask what the model would know at
prediction time, feature by feature, and check the timestamp of every field.
Removing the strongest feature and seeing performance collapse to near baseline
is a useful diagnostic.

## 4. Choosing the metric

The metric encodes what a mistake costs. Choose it before seeing any results,
because choosing after is a selection over metrics.

**Classification**

| Metric | Reports | Fails when |
|---|---|---|
| Accuracy | Share correct | Classes are imbalanced - predicting the majority scores 99% on a 1% positive rate |
| Precision | Of those flagged, how many were right | Ignores what was missed; trivially maximized by flagging only the surest case |
| Recall | Of the real positives, how many were caught | Ignores false alarms; trivially maximized by flagging everything |
| F1 | Harmonic mean of the two | Weights them equally, which is a claim about costs that is usually untrue |
| ROC AUC | Ranking quality across all thresholds | Looks reassuring under heavy imbalance because true negatives dominate |
| Precision-recall AUC | Ranking quality where positives are rare | Preferred under imbalance (Saito and Rehmsmeier, *PLOS ONE*, 2015) |
| Log loss, Brier score | Quality of the probabilities themselves | Only meaningful if probabilities are being used as probabilities |
| Cost-weighted error | The actual decision cost | Requires stating the costs, which is the point |

**Regression**

| Metric | Reports | Fails when |
|---|---|---|
| Mean absolute error | Typical error in original units | Nothing much; the sane default |
| Root mean squared error | Error with large misses weighted heavily | The tail dominates, and a single outlier moves it |
| Mean absolute percentage error | Relative error | Actual values near zero - it explodes; also penalizes over-prediction and under-prediction asymmetrically |
| R-squared | Share of variance accounted for | Comparing across datasets with different variance |
| Quantile loss | Error at a specific quantile | Only when the question is about the average |

The habit worth keeping: report the metric on the outcome's own scale next to
the metric that is easy to compare, because only the first tells anyone whether
the model is useful.

## 5. The decision threshold is not 0.5

A classifier produces a score; a decision needs a cutoff, and 0.5 is a default
of the software rather than a property of the problem.

Set it from costs: the cutoff that minimizes expected cost depends on the ratio
of the cost of a false positive to that of a false negative and on the base
rate. Where costs cannot be quantified, set it from a capacity constraint - how
many cases can actually be reviewed per day - which is the same arithmetic as an
alert budget.

Choose the threshold on validation data, never on test, and report the metric at
the chosen threshold as well as the threshold-free ranking measure.

## 6. Imbalance

- **Resample the training data if it helps, never the test data.** The test set
  must keep the real base rate or its metrics describe a world that does not
  exist.
- **Report the base rate with every metric.** It is the trivial baseline and it
  makes accuracy interpretable.
- **Prefer precision-recall to ROC** when positives are rare.
- **Calibration shifts when the training distribution is resampled.** The
  resulting scores are no longer probabilities on the original population and
  need to be corrected back if they are to be used as such.
- **Rare-event evaluation is dominated by counting error.** With 30 positives in
  the test set, every rate computed on them has a wide interval. Report it.

## 7. Calibration

Discrimination is whether the model ranks correctly. Calibration is whether a
score of 0.7 means the event happens 70% of the time. They are separate, and a
model can rank well while its probabilities are useless.

Calibration matters whenever the score enters an arithmetic decision - expected
value, expected cost, a threshold derived from costs, anything summed across
cases.

- **Reliability curve.** Bin the predictions, plot observed frequency against
  mean predicted probability, and look for departures from the diagonal.
- **Brier score** (Brier 1950) is the mean squared error of the probabilities;
  its decomposition separates calibration from discrimination.
- **Fixes** are Platt scaling (a logistic fit on the scores, Platt 1999) or
  isotonic regression (Zadrozny and Elkan, 2002) - both fitted on validation
  data, never on test, and isotonic needs enough data to avoid overfitting the
  step function.
- **Calibration decays** when the base rate shifts. A model calibrated last year
  on a 2% event rate is miscalibrated at 5%, regardless of how well it still
  ranks.

## 8. Baselines

A metric with nothing beside it is uninterpretable. Always report at least one:

- **Majority class** for classification, **the mean or median** for regression.
- **The previous value** for anything time-ordered - it is a strong baseline and
  frequently beats a model.
- **The existing rule or process** the model is meant to replace, scored the
  same way on the same test set.
- **A simple model** - a single feature, or a shallow one - which frequently
  lands within noise of the complicated one.

Report the gap to the baseline with an interval, and state the cost of the
complicated model in operational terms. A 0.3 point gain that needs a serving
stack is a different proposition from the same gain in a rule.

## 9. Is the improvement real?

This is the question the whole file exists for, and it is an ordinary inference
problem.

- **Compare on the same test set, paired.** The differences per case have far
  less variance than the two scores separately, and the pairing is what gives
  the comparison power.
- **Bootstrap the difference in metric**, resampling test cases, and report the
  interval on the difference. If it includes zero, the improvement is not
  established.
- **For paired binary predictions, McNemar's test** (McNemar 1947) uses exactly
  the cases where the two models disagree, which is where the information is.
- **Count the configurations tried.** Ten tuning runs and the best one wins by
  0.4 points is the multiplicity problem of `inference.md` section 8. The
  expected maximum of ten noisy scores exceeds the mean by a visible margin with
  no real improvement present.
- **Repeat across seeds** when training is stochastic. A gain smaller than the
  seed-to-seed spread of the same model is not a gain.
- **Then ask whether the size matters.** An improvement can be real and too
  small to justify anything.

## 10. Reporting

State: the split scheme and the unit it was split on; n in each set and the
class balance; the metric and why it was chosen; the score with an interval; the
baseline and the gap with an interval on the gap; the number of configurations
tried and how the winner was selected; the calibration check if scores are used
as probabilities; and the assumption whose failure would overturn it, which is
usually that the test set resembles what production will see.
