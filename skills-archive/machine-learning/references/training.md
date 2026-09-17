# Training

Model family, tuning, and the record that makes a result reproducible. This is
the part of the work with the best documentation elsewhere and the smallest
effect on the outcome, which is why it gets a short reference and a hard budget.

## Contents

- [Start with the cheapest model that could work](#start-with-the-cheapest-model-that-could-work)
- [Model family by problem shape](#model-family-by-problem-shape)
- [What each family assumes and where it fails](#what-each-family-assumes-and-where-it-fails)
- [Tuning strategy and its budget](#tuning-strategy-and-its-budget)
- [The parameters worth tuning](#the-parameters-worth-tuning)
- [Regularization and overfitting](#regularization-and-overfitting)
- [Early stopping](#early-stopping)
- [Reproducibility](#reproducibility)
- [Diagnosing a disappointing model](#diagnosing-a-disappointing-model)
- [When to stop](#when-to-stop)
- [Ensembling](#ensembling)
- [What to record per experiment](#what-to-record-per-experiment)

## Start with the cheapest model that could work

Fit a baseline (see `framing.md`), then one simple model with default
parameters, on the real split, end to end, including the serving path if
possible. That first pass answers questions that no amount of tuning answers:
whether the signal exists, whether the pipeline is correct, how long a fit takes,
and how big the gap is between the baseline and something reasonable.

Tuning before that is spent on a construction that may be wrong. A five percent
gain from hyperparameters on a leaking split is worth nothing.

## Model family by problem shape

| Data | First choice | Why |
|---|---|---|
| Tabular, mixed types, thousands to millions of rows | Gradient-boosted trees | Handles mixed types, monotone-invariant to feature scale, robust to irrelevant features, strong out of the box |
| Tabular, small (under a few thousand rows) | Regularized linear model, or a shallow tree | Boosting overfits small data and the simpler model is interpretable |
| Tabular, need an auditable model | Logistic regression, single decision tree, rule list | The explanation is the deliverable, not the accuracy |
| Wide and sparse (text bag-of-words, one-hot) | Linear model with L2 or L1 | Linear models handle sparse high dimensions well; trees do not |
| Text, semantics matter | Pretrained encoder plus a classifier head | Beats bag-of-words when word order and meaning carry the signal |
| Images, audio | Pretrained network, fine-tuned | Training from scratch needs data nobody has |
| Time series, one or few series | Classical forecasting or a boosted model on lag features | The seasonal naive baseline is strong; beat it before adding complexity |
| Time series, many related series | Boosted trees on lag and calendar features, or a global model | One model across series shares structure |
| Unlabeled, want groups | Clustering, then validation against a decision | Without ground truth, the score is not the point |
| Unlabeled, want outliers | Isolation forest, one-class methods, or a simple threshold | Evaluation is the hard part |

Deep learning on tabular data is the standing exception to the fashion: on
mid-sized heterogeneous tables, gradient-boosted trees remain the reasonable
default, and the burden of proof sits with the network. Deep learning practice
is out of scope for this skill.

## What each family assumes and where it fails

**Linear and logistic regression.** Assumes the effect of each feature is
additive and, on its link scale, linear. Fails on interactions and thresholds
unless they are engineered in. Sensitive to feature scale, collinearity and
outliers. Coefficients are interpretable only when features are on comparable
scales and not collinear. Cheap, stable, and a strong baseline on small data.

**Decision tree.** Assumes the target is well approximated by axis-aligned
splits. Fails at smooth relationships and at diagonal boundaries, and is
unstable - a small data change produces a different tree. Needs depth or leaf
limits or it memorizes.

**Random forest.** Averages decorrelated trees, so it is robust and needs little
tuning. Fails to extrapolate beyond the training range (a serious problem for
trending time series), gets large in memory, and its probability estimates are
usually poorly calibrated.

**Gradient-boosted trees** (XGBoost, LightGBM, CatBoost, histogram boosting).
Fits trees sequentially on residuals. The default for tabular problems. Fails
the same way on extrapolation, overfits with too many rounds unless early
stopping is used, and is sensitive to learning rate and depth. Handles missing
values natively in most implementations. Feature importances are biased toward
high-cardinality features, which is a reason to prefer permutation importance or
SHAP for the explanation.

**Support vector machines.** Strong on small, clean, high-dimensional data with a
clear margin. Fails on scale (roughly quadratic to cubic in rows), requires
scaling, and gives no probability without an extra calibration step.

**k-nearest neighbors.** No training, all cost at prediction. Fails in high
dimensions, where distances concentrate and every point is equally far, and
requires scaling. Useful as a sanity check and inside recommender-style problems.

**Naive Bayes.** Assumes features are conditionally independent given the class,
which is nearly always false and often harmless. Very fast, decent on text, and
its probabilities are typically extreme and untrustworthy.

**Neural networks.** Assume enough data to learn the representation. Fail on
small tabular data, need scaling, and carry a much larger tuning surface. Their
advantage appears on unstructured data.

**k-means.** Assumes spherical, similar-sized, similar-density clusters and
requires k up front. Fails on elongated or nested structure and on unscaled
features. The chosen k is a decision, not a discovery.

## Tuning strategy and its budget

Set the budget before starting: **how many fits, on what hardware, by when.**
Without one, tuning expands to fill the schedule and produces a fraction of a
point.

- **Random search over grid search.** For the same number of fits, random search
  explores more distinct values of each parameter, which matters because only a
  few of them are important. Grid search is defensible only over two or three
  parameters with a handful of values each.
- **Successive halving** trains many configurations on a small budget, keeps the
  best fraction, and repeats with more. It gets more out of the same wall clock
  than either search, and it can discard a configuration that would have won with
  more resources.
- **Bayesian and tree-structured search** pays off at expensive fits and large
  spaces, and is overhead below that.
- **Coarse to fine.** One wide random pass to find the region, one narrow pass
  inside it. Two passes is usually the whole of it.

Three rules that matter more than the search algorithm:

1. **Tune on validation, never on test.** With cross-validation, the search must
   run inside the folds, and preprocessing must sit inside the pipeline being
   searched.
2. **Report the tuned score honestly.** The best of 200 configurations on
   cross-validation is optimistically biased by selection. Nested
   cross-validation, or a clean holdout scored once, gives the number worth
   quoting.
3. **Stop when the improvement is inside the noise.** The spread of the metric
   across folds is the yardstick; a gain smaller than that spread is not a gain.
   Whether an observed difference between two models is real is a question for
   inference, and this skill does not answer it.

## The parameters worth tuning

Most parameters do nothing. These are the ones that move the score.

**Gradient-boosted trees.** Learning rate together with the number of rounds
(they trade off directly - halve the rate, roughly double the rounds), maximum
depth or number of leaves, minimum samples or minimum child weight per leaf,
subsample and column-sample fractions, and L2 regularization. Set the learning
rate low and the number of rounds by early stopping, then tune the rest.

**Random forest.** Number of trees (more is never worse, only slower - set it as
high as the budget allows rather than tuning it), features considered per split,
and minimum samples per leaf. Depth rarely needs limiting.

**Linear models.** The regularization strength, on a log scale, and the penalty
type. That is nearly all of it.

**SVM.** C and, for the radial basis kernel, gamma - both on a log scale, and
they interact, so search them jointly.

**k-nearest neighbors.** k, and the distance weighting.

## Regularization and overfitting

Overfitting is diagnosed by the gap between training and validation performance,
not by the validation score alone. A model with 0.99 training and 0.72 validation
is overfitting; one with 0.74 and 0.72 is underfitting and has room.

The levers, in the order they usually help: more data, fewer or better features,
stronger regularization, a simpler model family, and early stopping. Feature
selection is itself a modeling decision that must happen inside the pipeline -
selecting features on the full dataset before splitting is leakage.

## Early stopping

Fit until a held-out metric stops improving for a set number of rounds, then keep
the best iteration. It is the most effective single guard against overfitting in
boosting, and it is also the most common route by which the test set gets
consumed.

The rule: **early stopping needs its own validation split, carved out of the
training data.** Watching the test set is the `TEST_USED_IN_TUNING` defect - the
number of rounds is then a hyperparameter chosen on the test set, and the test
score is no longer an estimate of unseen performance. Inside cross-validation,
the early-stopping split must come from the training folds.

## Reproducibility

**A result that cannot be reproduced is an anecdote.** Three things travel
together and are useless separately:

1. **The seed.** One module-level constant, passed to the split, the shuffle, and
   every stochastic estimator. Missing seeds are `NO_RANDOM_STATE`.
2. **The data version.** A snapshot identifier, a table version, a query with an
   as-of date, or a content hash of the input file. "The customers table" is not
   a version.
3. **The code version.** The commit, and the resolved dependency versions, not
   the ranges. A minor version bump in a boosting library changes results.

Seeding is not complete determinism. Thread counts, GPU kernels, floating-point
reduction order and hash randomization can all move results slightly; where exact
reproduction is required, pin the thread count and record the platform. What the
seed guarantees is that a rerun on the same machine with the same data gives the
same number, which is enough to make two experiments comparable.

Record all three in the artifact itself - alongside the serialized model - rather
than in a notebook cell that will be re-run.

## Diagnosing a disappointing model

Work in this order. It is roughly the order of likelihood and inversely the order
of cost.

1. **Is the target right?** Wrong horizon, wrong population, inconsistent
   labeling. Re-read the target definition against a handful of raw rows.
2. **Is the baseline actually beaten?** Sometimes the answer is that the problem
   is nearly unlearnable and the naive prediction is the right product.
3. **Is the split correct?** A too-good score means leakage; a too-poor score can
   mean the test set is a different population.
4. **Is the signal absent or the model wrong?** Compare training performance. Low
   training performance means the model cannot fit at all - more capacity or
   better features. High training and low validation means overfitting.
5. **Look at the errors, individually.** Thirty misclassified rows read by hand
   teaches more than any aggregate metric. Group them: one segment, one time
   period, one data source, one label error.
6. **Only then, tune.**

## When to stop

Stop when any of these is true:

- The improvement per experiment has fallen below the noise across folds.
- The remaining gap is dominated by label noise, which no model can cross.
- The model is good enough for the decision it serves, which was written down
  during framing.
- The next gain requires a feature that cannot be served in production.

More data usually beats more model, and a better target usually beats both. If
the learning curve (score against training set size) is still rising at the full
dataset, more rows are the highest-value next step; if it is flat, they are not.

## Ensembling

Averaging several different models reliably gains a little and costs a lot: more
artifacts, more failure modes, more latency, harder explanations. Worth it in a
competition, rarely worth it in production for the first version of a model. If
used, ensemble genuinely different families rather than seeds of the same one,
and keep the single best model as the fallback.

## What to record per experiment

One row per experiment, in a file or a tracking tool:

- Identifier, date, and the question the experiment asked.
- Data version, split definition, seed.
- Model family and full parameter set.
- Metric on validation with the spread across folds, plus the baseline's score.
- What changed since the previous experiment, and what was learned.

The last column is the one that prevents the same experiment being run three
times by three people.
