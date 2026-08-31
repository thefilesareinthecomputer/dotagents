# Data construction

Where models are actually won and lost. Every defect here produces a validation
score that is too good and a production result that is not, and none of them is
visible in the score itself.

## Contents

- [The split is a simulation of production](#the-split-is-a-simulation-of-production)
- [Choosing the split](#choosing-the-split)
- [The three-way split, and what each part is for](#the-three-way-split-and-what-each-part-is-for)
- [Cross-validation](#cross-validation)
- [The leakage taxonomy](#the-leakage-taxonomy)
- [The pipeline is the structural fix](#the-pipeline-is-the-structural-fix)
- [Duplicates and near-duplicates](#duplicates-and-near-duplicates)
- [Class imbalance](#class-imbalance)
- [Encoding categorical variables](#encoding-categorical-variables)
- [Missing values](#missing-values)
- [Outliers and scaling](#outliers-and-scaling)
- [Feature engineering that survives serving](#feature-engineering-that-survives-serving)
- [Point-in-time correctness](#point-in-time-correctness)
- [The construction checklist](#the-construction-checklist)

## The split is a simulation of production

The test split exists to answer one question: **how will this perform on data it
has never seen, drawn the way production data will be drawn?** Every split
decision follows from making that simulation faithful.

Production data differs from training data in specific ways, and the split
should reproduce whichever ones apply:

- It arrives **later in time**. So the test set should be later in time.
- It concerns **entities the model has not seen**. So repeated entities should
  not span the split.
- It arrives **one row at a time**, without the rest of the batch to normalize
  against. So no transformation may be fitted across the split.
- It has **no label yet**. So nothing derived from the label may be a feature.

A random split is correct only when rows are genuinely exchangeable: no time
ordering that matters, no repeated entities, no nesting. That is rarer than the
default suggests.

## Choosing the split

| Data structure | Split | Why |
|---|---|---|
| Independent rows, one per entity | Random, stratified on the target | Rows are exchangeable |
| Rows carry a timestamp and the model predicts forward | Cutoff date, or forward-chaining folds | Production predicts the future from the past |
| Repeated entities (customers, patients, devices, images from one subject) | Group-aware, split on the entity | A seen entity is not an unseen one |
| Both time and repeated entities | Group-aware within a time cutoff | Both failures apply |
| Hierarchy or panel (stores within regions, pupils within schools) | Split at the level the model will generalize to | Generalizing to new stores requires holding out stores |
| Severe imbalance | Stratified, always | Otherwise a fold can contain zero positives |
| Data collected in batches, sites or sessions | Split by batch | Batch effects are learnable and do not transfer |

Two rules make this concrete. **Stratify on the target for classification**,
which costs nothing and prevents a fold with no positives. **Never stratify on a
feature to make the splits look similar** - that is engineering the test set to
resemble training, which is the opposite of the point.

The size question has a simple answer: the test set needs enough positives that
the metric's uncertainty is smaller than the difference being decided. Below a
few hundred positives, the metric on a single split is too noisy to compare two
models, and repeated cross-validation is the answer rather than a bigger
percentage.

## The three-way split, and what each part is for

- **Train** fits parameters.
- **Validation** chooses hyperparameters, features, thresholds, model families
  and stopping points. It is consumed by that choosing - after a hundred
  decisions it is optimistic too.
- **Test** is scored once, at the end, and then the work is done. Every look at
  it spends some of its value.

The most common breach is not touching the test set directly, it is deciding
something after seeing its score - dropping the model that did worse on it,
adding a feature because the test score dropped, retuning after a disappointing
result. That is the test set influencing training through a human, and the
finished number is no longer an estimate of unseen performance.

If the test set must be re-scored (a genuine bug fix, for example), say so in
the write-up. A test score reported after three revisions is a validation score
that has been mislabeled.

## Cross-validation

Use it when a single validation split is too small to be stable, which is most
of the time below a few tens of thousands of rows.

| Scheme | When |
|---|---|
| K-fold, k=5 or 10 | Independent rows, enough data |
| Stratified k-fold | Classification, always the default over plain k-fold |
| Repeated stratified k-fold | Small data, where fold assignment itself moves the score |
| Group k-fold, group shuffle split | Repeated entities |
| Stratified group k-fold | Repeated entities plus imbalance |
| Time series split (forward chaining) | Time-ordered data |
| Nested cross-validation | Reporting a performance estimate after tuning, with limited data |
| Leave-one-out | Very small data only; high variance and expensive |

**Nested cross-validation** is the honest answer to "I tuned on
cross-validation, what is my expected performance". An inner loop chooses
hyperparameters, an outer loop scores the whole procedure including that choice.
A single cross-validation score after tuning is optimistic by an amount that
grows with the size of the search.

Forward chaining for time series means fold i trains on periods 1..i and tests on
period i+1. Two decisions matter: whether the training window expands or slides
(sliding is right when old regimes are misleading), and whether a gap is needed
between train and test to reflect the label delay in production.

## The leakage taxonomy

Leakage is any path by which information unavailable at prediction time reaches
training. Six kinds, each with a different fix.

**1. Target leakage.** A feature is a consequence of the outcome rather than a
predictor of it. `days_since_cancellation`, `refund_amount`,
`collections_flag`. Symptom: implausible performance and one feature dominating
importance. Fix: the prediction-moment test from `framing.md` on every feature.

**2. Train-test contamination via preprocessing.** A transformation fitted on the
full dataset before splitting. Scalers learn the mean, imputers learn the median,
encoders learn the categories, feature selectors learn which columns correlate
with the target - all from rows that end up in the test set. Fix: fit inside a
pipeline, after the split, on training rows only. This is `FIT_BEFORE_SPLIT` and
it is the single most common leak in real code.

**3. Temporal leakage.** Rows from after the test period are in training, or an
aggregate spans the prediction moment. A random split of dated rows guarantees
it. Fix: split on time, and give every aggregate an as-of date. This is
`TEMPORAL_SPLIT_MISSING`.

**4. Group leakage.** The same entity appears on both sides of the split. Three
X-rays of one patient, forty sessions of one user, several transactions of one
account. The model recognizes the entity rather than the pattern. Fix: group-aware
split. This is `GROUP_LEAK`.

**5. Duplicate leakage.** Exact or near-duplicate rows land on both sides. Common
in scraped data, in event logs with retries, and after any resampling done before
splitting. Fix: deduplicate before splitting, and resample after. Synthetic
oversampling before the split is the sharpest version, since SMOTE interpolates
between neighbors that then end up on opposite sides - this is
`RESAMPLE_BEFORE_SPLIT`.

**6. Leakage through repeated evaluation.** The test set is consulted many times
across a project. No single look is wrong; the accumulation is. Fix: budget the
looks, keep a genuinely untouched holdout when the stakes justify one, and state
how many times the test set was scored.

Two detection habits worth keeping. **Interrogate any implausible score** rather
than celebrating it: above roughly 0.95 AUC on a messy business problem, assume
leakage until proven otherwise. **Read the top of the feature importance list
against the timeline**, because target leakage almost always shows up as one
feature carrying the model.

## The pipeline is the structural fix

Most leakage of kind 2 disappears when preprocessing is expressed as a pipeline
rather than a sequence of statements, because the pipeline refits every step
inside every fold.

```python
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

numeric = Pipeline([("impute", SimpleImputer(strategy="median")),
                    ("scale", StandardScaler())])
categorical = Pipeline([("impute", SimpleImputer(strategy="most_frequent")),
                        ("encode", OneHotEncoder(handle_unknown="ignore"))])

preprocess = ColumnTransformer([("num", numeric, numeric_columns),
                                ("cat", categorical, categorical_columns)])

model = Pipeline([("prep", preprocess), ("clf", estimator)])
```

Everything downstream then behaves correctly by construction:
`cross_val_score(model, X_train, y_train, cv=cv)` refits the imputer and the
scaler per fold, `GridSearchCV` tunes preprocessing parameters without leaking,
and the fitted object serializes as one artifact so serving cannot use different
preprocessing from training. `handle_unknown="ignore"` matters more than it
looks: a category that appears only in production otherwise raises at serve time.

Resamplers do not belong in a scikit-learn `Pipeline` because they change the
number of rows; the imbalanced-learn `Pipeline` is the drop-in that applies them
to training folds only. Version-sensitive detail, written 2026-08-12 - re-check
against the installed versions.

## Duplicates and near-duplicates

Check before splitting, always:

- Exact duplicate rows, including the label.
- Duplicate keys with different labels, which means the unit of prediction is
  wrong or the labeling is inconsistent.
- Near-duplicates: the same text with different whitespace, the same image
  rescaled, the same event logged twice by a retry.

Deduplicating after splitting does not help - the copies are already on both
sides. Deduplicating before splitting can change the base rate, so record what
was removed.

## Class imbalance

First, decide whether it is a problem. Imbalance is a problem when the minority
class is the one that matters and the model ignores it; it is not a problem
merely because the classes are unequal. Many estimators handle moderate
imbalance without help.

In order of preference:

1. **Change the metric and the threshold, not the data.** Precision, recall,
   average precision (precision-recall AUC) against the positive class. Almost
   every classifier outputs a score; the default 0.5 threshold is a convention,
   not a result, and moving it is free.
2. **Class weights.** `class_weight="balanced"`, or `scale_pos_weight` in the
   gradient boosting libraries. One parameter, no new rows, no leakage surface.
3. **Resampling, inside the pipeline.** Random undersampling of the majority
   discards data but is cheap and often effective. Synthetic oversampling (SMOTE
   and its relatives) invents rows by interpolating between minority neighbors,
   which is defensible for continuous features and awkward for categorical ones.
   Both must run on the training fold only.
4. **Collect more of the minority class**, when possible, which beats all of the
   above.

Two rules. **Never resample the test set** - it must keep the production base
rate or every metric computed on it is fiction. **Never resample before
splitting**, for the reason in the taxonomy above.

Below a few hundred positive examples in absolute terms, the honest answer is
often that the problem is anomaly detection or a rule, not classification.

## Encoding categorical variables

| Method | Use when | Cost |
|---|---|---|
| One-hot | Low cardinality (under roughly 15 levels), linear models, neural networks | Dimensionality; unseen categories need `handle_unknown` |
| Ordinal | The categories are genuinely ordered, or the model is a tree | Imposes a false order on unordered categories for non-tree models |
| Native categorical support | LightGBM, CatBoost, recent scikit-learn histogram boosting | Library-specific; check the version |
| Target (mean) encoding | High cardinality where the category carries signal | **Leaks unless computed out of fold**; needs smoothing for rare levels |
| Frequency or count encoding | High cardinality, tree models | Loses the identity of the category |
| Hashing | Very high cardinality, streaming | Collisions, unintelligible features |

Target encoding is the one that ruins projects. Computing the per-category mean
of the target over the whole training set leaks the row's own label into its
feature. Compute it out of fold (each row encoded from folds it is not in), with
smoothing toward the global mean for rare categories, and inside the pipeline so
it refits per fold.

Two things to plan for regardless of method: a category that appears in
production and never in training, and a level whose meaning changes over time.
Both are handled with an explicit "unknown" bucket rather than a crash.

## Missing values

Why a value is missing is a modeling question, not a data cleaning one.

- **Missing completely at random**: dropping rows is unbiased but wasteful.
- **Missing at random** given the observed data: imputation from other columns
  works.
- **Missing not at random**: the missingness itself carries the signal - income
  is missing more often at the extremes, a test result is missing because nobody
  ordered the test. Imputing it away destroys the information.

Practice:

- **Add a missing-indicator column** whenever missingness might be informative.
  It is cheap and it converts case three into something learnable.
- **Impute inside the pipeline.** A median computed over the full frame is
  leakage of kind 2.
- **Tree ensembles handle missing natively** in most current implementations,
  which is often better than imputing. Check the specific library rather than
  assuming.
- **Never impute the target.** A row with no label is not a training example.
- **Check whether missingness differs between training and production.** A column
  that is 2 percent missing in the warehouse and 60 percent missing in the
  request payload is a skew bug, not a data quality issue.

## Outliers and scaling

Scaling matters for distance-based and gradient-based models (linear models,
SVMs, k-nearest neighbors, neural networks, k-means, PCA) and is irrelevant to
trees. Fit the scaler on training rows only, inside the pipeline. Prefer robust
scaling when the distribution has heavy tails.

Do not remove outliers reflexively. An outlier is either an error (fix or drop
it), a rare but real case (keep it, it is often the case that matters), or
evidence that the feature needs a transformation. In fraud and failure
prediction, the outliers are the target.

## Feature engineering that survives serving

A feature is only worth building if it can be recomputed identically at
prediction time. Before building one, answer three questions: where does the
input come from at serve time, how fresh is it, and who owns it.

Reliable and cheap:

- **Ratios and differences** between existing columns, which encode a
  relationship a tree would need many splits to approximate.
- **Time-since features** measured from the prediction moment, never from today.
- **Rolling aggregates over a fixed window ending at the prediction moment**, per
  entity, with the window and the as-of date stated.
- **Domain flags** that encode a rule an expert already uses.
- **Cyclical encodings** for hour and day of week, so 23:00 and 01:00 are close.

Expensive or dangerous:

- **Aggregates without an as-of date**, which are time travel.
- **Features derived from the target**, in any form, including "the average
  target for this customer's segment" computed over all time.
- **Features that depend on the batch**, such as a rank or a z-score computed
  within the request batch. These change with the batch and cannot be reproduced
  for a single online request.
- **Automated feature generation over hundreds of columns**, which multiplies the
  leakage surface faster than any review can check it.

More features is not better. Every feature is something that can break, drift,
or arrive late in production, and a feature that adds a thousandth of AUC is a
liability.

## Point-in-time correctness

The discipline that prevents most temporal leakage, borrowed from finance:
**every value used for a row must be reconstructed as of that row's prediction
moment.**

In practice this means the source tables need history, not current state. A
customer dimension that overwrites the segment on change cannot answer "what was
their segment last March", and any feature built from it is contaminated. Where
the source keeps history (a type 2 dimension, an event log, an append-only
table), the join is an as-of join on the effective dates rather than a join on
the key.

Two tests that catch most violations:

1. **Rebuild one row's features from a snapshot of the data as it existed at the
   prediction moment** and compare. If they differ, something is time-traveling.
2. **Score the model on the oldest slice of data and the newest.** A large gap in
   favor of the older slice often means an aggregate leaked.

## The construction checklist

Before training anything:

- The split matches the data's structure, and the reason is written down.
- Nothing is fitted before the split; all transformations live in a pipeline.
- No feature fails the prediction-moment test.
- Duplicates and repeated entities are handled explicitly.
- The base rate is known, and the test set retains it.
- Categorical encoding handles unseen categories without raising.
- Missingness is modeled, not silently imputed away.
- Every aggregate has an as-of date.
- The seed, the data version and the code version are recorded together.
