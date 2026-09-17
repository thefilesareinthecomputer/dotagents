# The audit catalog

One entry per code emitted by `scripts/ml_check.py`: what it means, why it
matters, the exact rule that decides it, what clears it, and where the rule is
blind. The checker reads structure with `ast` and never imports or runs the file,
so every rule below is decided from statements, call arguments and literals -
never from data.

Read this when a finding needs judging, when a rule seems wrong, or before
changing one.

## Contents

- [How the checker decides anything](#how-the-checker-decides-anything)
- [FIT_BEFORE_SPLIT](#fit_before_split)
- [TEMPORAL_SPLIT_MISSING](#temporal_split_missing)
- [TEST_USED_IN_TUNING](#test_used_in_tuning)
- [NO_RANDOM_STATE](#no_random_state)
- [TARGET_IN_FEATURES](#target_in_features)
- [NO_BASELINE](#no_baseline)
- [RESAMPLE_BEFORE_SPLIT](#resample_before_split)
- [METRIC_MISMATCH](#metric_mismatch)
- [GROUP_LEAK](#group_leak)
- [PARSE_ERROR](#parse_error)
- [NOTEBOOK_ORDER](#notebook_order)
- [Judging a finding](#judging-a-finding)
- [What no static checker can find](#what-no-static-checker-can-find)

## How the checker decides anything

Three primitives underpin every rule.

**Statement order.** The line number of one call compared with the line number of
another. This is sound for a module executed top to bottom and unsound for a
notebook, which is why notebooks get a note and a downgrade.

**Constructor tracking.** `scaler = StandardScaler()` records that `scaler` is a
preprocessor, so `scaler.fit_transform(...)` later is recognized wherever it
appears. Chained calls (`StandardScaler().fit_transform(X)`) are recognized
directly, and a small set of conventional receiver names (`scaler`, `encoder`,
`imputer`, `vectorizer`, `preprocessor`, `transformer`) is accepted as a fallback
when the constructor is not visible in the file.

**Literals and keywords.** String constants become evidence: a literal matching a
date pattern is a temporal signal, one matching an id pattern is a grouping
signal. Keyword arguments are read by name, so `random_state=`, `stratify=`,
`class_weight=`, `groups=` and `eval_set=` each carry meaning. Docstrings are
excluded from literal scanning, because prose describing a script is not evidence
about the script.

The scope is one file. A split in one module and a fit in another read as
unrelated, and the checker reports nothing rather than guessing.

## FIT_BEFORE_SPLIT

**Severity: error.** With `TEMPORAL_SPLIT_MISSING`, one of the two defects that
most reliably produces a model that looks excellent and fails in production.

**What it is.** A transformer that learns from data - a scaler, an encoder, an
imputer, a feature selector, a dimensionality reduction - is fitted on the full
frame before the train/test split. Its learned statistics contain the test rows.

**Why it matters.** The test score is optimistic by an amount nobody can measure
after the fact. The size of the effect depends on the transformer and the data:
small for a standard scaler on a large sample, large for target encoding, for
imputation, and for any feature selection that consulted the target. Worse, it is
invisible - the numbers look reasonable, just better.

**Detection rule.** A `.fit(...)` or `.fit_transform(...)` call whose receiver is
a known preprocessor (tracked by constructor, chained call, or conventional
receiver name) at a line number below the first split event in the file. Split
events are `train_test_split`, any cross-validation splitter constructor, any
`.split(...)` call, and an assignment to a train- or test-named variable that
contains a date comparison.

**What clears it.** Splitting before fitting; putting the transformer in a
`Pipeline` (a pipeline's `.fit` is not a preprocessor fit, and inside
cross-validation it refits per fold); a file with no split at all, where the rule
stays silent because it cannot distinguish training code from inference code.

**Where it is blind.** A transformer imported under an unfamiliar name and
assigned to an unconventional variable is not tracked. A fit inside a function
called before the split is judged by the line of the `def`, not the call. A
custom transformer class is unknown to the rule.

**The fix.** Split first and fit on the training rows only, or express the
preprocessing as a pipeline so it refits inside every fold. See
`data-construction.md`.

## TEMPORAL_SPLIT_MISSING

**Severity: error.**

**What it is.** The data carries time and the split is random, so rows from after
the test period sit in training. The model is scored on interpolating between
periods it has seen, which is not the task production gives it.

**Why it matters.** This is the defect behind most "it worked in the notebook"
stories. Anything with a trend, a seasonality or a regime change scores far
better under a random split than it can possibly achieve predicting forward.

**Detection rule.** All three of: a temporal signal (a string literal matching
`date`, `time`, `timestamp`, `datetime`, `dt`, `ts` as a whole word, or ending in
`_at`; a `to_datetime` or `date_range` call; a `parse_dates=` keyword), a random
split (`train_test_split` without `shuffle=False`, or a shuffling
cross-validation splitter), and no time-aware split anywhere (`TimeSeriesSplit`,
`PredefinedSplit`, or a train/test assignment built from a date comparison).

**What clears it.** A time-aware splitter; `shuffle=False`; a manual cutoff of
the form `train = frame[frame["event_date"] < cutoff]`; the absence of any
temporal column.

**Where it is blind.** A date column named without any of those tokens
(`period`, `cohort`, `vintage`) is not seen. It cannot tell a genuinely
exchangeable dataset that happens to carry a `created_at` column from one where
time matters, so it will fire on the first - which is deliberate, since the
answer is one comment justifying the random split.

**The fix.** Split on a cutoff, or use forward-chaining folds, and hold out the
most recent period. If the rows really are exchangeable, say so in a comment
beside the split.

## TEST_USED_IN_TUNING

**Severity: warning.**

**What it is.** The test split reaches a fit, a hyperparameter search, or an
early-stopping callback.

**Why it matters.** Once the test set has influenced a choice, it is a second
validation set, and its score is no longer an estimate of unseen performance. The
early-stopping case is the most common and the most innocent-looking: the number
of rounds is a hyperparameter, and choosing it on the test set is tuning on the
test set.

**Detection rule.** A call to `fit`, `fit_transform`, `partial_fit`,
`fit_predict`, or one of the search and cross-validation entry points, receiving
a positional argument that mentions a variable whose name contains `test`,
`holdout` or `heldout` as an underscore-delimited part; or a data-carrying
keyword (`eval_set`, `validation_data`, `eval_data`) whose value mentions such a
variable. One finding per call, not per argument.

**What clears it.** Fitting and tuning on training and validation names only.
Scoring the test split is not tuning on it - `.score(...)`, `predict` and metric
functions are not flagged.

**Where it is blind.** A test split held in a variable that does not say so
(`X2`, `b`, `holdout_frame` is caught, `final` is not). Data passed through a
function boundary. A validation split that was itself carved out of the test set.

**The fix.** Carve a validation split out of the training data for tuning and
early stopping, and touch the test split once, at the end.

## NO_RANDOM_STATE

**Severity: warning.**

**What it is.** A split, a shuffle or a stochastic estimator with no seed.

**Why it matters.** The result cannot be reproduced, so two experiments cannot be
compared and a reported number cannot be defended. On small data the spread
across seeds is often larger than the difference being claimed between two
models, which means an unseeded comparison can be pure noise.

**Detection rule.** A call to a known stochastic constructor or function -
`train_test_split`, shuffling splitters, tree ensembles, boosting libraries,
neural network estimators, k-means, resamplers, randomized search - with no
`random_state`, `seed`, `random_seed`, `rng` or `generator` keyword. Also
`.sample(...)`, `.shuffle(...)` and `.permutation(...)` method calls without a
seed. `KFold`, `StratifiedKFold`, `GroupKFold` and `StratifiedGroupKFold` are
flagged only when `shuffle=True` is passed, because they are deterministic
otherwise.

**What clears it.** Passing the seed. One module-level constant passed everywhere
is the intended shape.

**Where it is blind.** Estimators whose randomness depends on a solver choice
(`LogisticRegression` with `saga`, for instance) are deliberately not flagged,
because flagging every one of them is noise. A seed set globally with
`numpy.random.seed` is not recognized, and should not be - it does not reach
every library, and it is not a per-object guarantee.

**The fix.** One seed constant at the top of the module, passed to every
stochastic call, and recorded with the data version and the code version.

## TARGET_IN_FEATURES

**Severity: warning.**

**What it is.** The target column, or a trivially derived copy, remains in the
feature matrix.

**Why it matters.** The model reads the answer off a column. The score is near
perfect and the model is worthless. It survives review more often than it should
because the code looks ordinary.

**Detection rule.** First the target is identified: an assignment to `y`,
`target`, `label` or `labels` from a single-literal subscript of a frame
(`y = frame["churned"]`) or from a `.pop(...)` call. Then the feature matrix is
examined: an assignment to `X`, `features`, `feature_matrix` or `feats` that is
the same frame with no drop, or a `.drop(...)` whose column list does not include
the target literal, or a column selection whose list does include it. A `.pop`
target clears the rule outright, since `pop` removes the column.

**What clears it.** Dropping the target explicitly, or extracting it with `pop`.

**Where it is blind.** Derived copies. `churned_flag`, `days_since_churn` and
`churn_reason` are the same information under other names, and no static rule can
recognize them. It also only sees the conventional variable names above.

**The fix.** Drop the target explicitly, then look for its derivatives: any
column that could only be populated after the outcome is the same defect wearing
a different name.

## NO_BASELINE

**Severity: warning.**

**What it is.** A model is scored with nothing to compare it against.

**Why it matters.** A metric alone is not evidence. Predicting the majority class
or last week's value frequently lands within a point of a tuned model, and that
is the finding that changes a decision. A score without a baseline cannot be
argued with, which is precisely why it should not be reported.

**Detection rule.** The file calls a scoring function or a `.score(...)` method,
and nothing in it references a baseline: no `DummyClassifier` or `DummyRegressor`,
and no identifier or non-docstring string containing `baseline`, `naive`,
`majority`, `most_frequent` or `prior_rate`.

**What clears it.** A dummy estimator, or any naming that says a baseline exists.
The naming test is deliberately generous - the rule is a reminder, and its cost
of being wrong should be low.

**Where it is blind.** A baseline computed in a different file or a previous
notebook. A baseline present in name only, scored on a different split or a
different metric, which is worse than none because it looks like a comparison.

**The fix.** Fit a dummy estimator or the existing business rule, score it on the
same split with the same metric, and report both numbers in the same table. The
baseline ladder is in `framing.md`.

## RESAMPLE_BEFORE_SPLIT

**Severity: warning.**

**What it is.** SMOTE or a similar sampler is applied before the split.

**Why it matters.** Synthetic minority rows are interpolated between real
neighbors that then land on opposite sides of the split, so near-duplicates of
training rows sit in the test set. Recall and precision on the minority class
look dramatically better than they are. Undersampling before the split is milder
but still changes the test set's base rate, which makes every metric computed on
it a fiction.

**Detection rule.** A `.fit_resample(...)` or `.fit_sample(...)` call, or a fit
on a variable constructed from a known sampler, at a line below the first split
event.

**What clears it.** Resampling after the split, on the training rows only, or
placing the sampler inside an imbalanced-learn pipeline so it applies per fold.

**Where it is blind.** Manual resampling written by hand - concatenating a
duplicated minority slice, or sampling the majority with pandas - is not
recognized as resampling.

**The fix.** Split first and resample the training fold only. Better, try class
weights and a threshold change before resampling at all; see the imbalance
section of `data-construction.md`.

## METRIC_MISMATCH

**Severity: warning.** The most approximate rule in the catalog, and the one to
read before trusting.

**What it is.** Accuracy is reported on a problem whose class balance is far from
even.

**Why it matters.** At a 2 percent positive rate, predicting the majority class
scores 98 percent accuracy and finds nothing. Accuracy on an imbalanced problem
is not a weak metric, it is an actively misleading one, and it is the default
people reach for.

**Detection rule, and its approximation.** Class balance is a property of data,
and this checker never reads data. The proxy is: `accuracy_score` is called (or
`scoring="accuracy"` is passed), **and** no other metric appears anywhere in the
file, **and** nothing acknowledges imbalance - no `class_weight`,
`sample_weight`, `scale_pos_weight`, `stratify` or `is_unbalance` keyword, no
`"balanced"` literal, no resampler. All three conditions must hold.

The rule therefore fires on code that reports accuracy and shows no sign of
having considered the class distribution, and stays quiet on code that has. It
will miss an imbalanced problem whose author stratified the split and then
reported accuracy anyway, and it will fire on a genuinely balanced problem whose
author had no reason to mention balance. The first is a false negative accepted
to keep the rule quiet; the second is a false positive resolved by one line
stating the base rate.

**What clears it.** Any second metric, or any imbalance handling.

**The fix.** Report precision, recall and average precision against the positive
class, or state the class balance and why accuracy is the right metric for this
decision. Choosing the metric for a decision is a measurement question, and this
skill does not answer it.

## GROUP_LEAK

**Severity: warning.** The second approximate rule.

**What it is.** Repeated entity ids span the train and test splits with no
group-aware split.

**Why it matters.** With several rows per customer, patient, device or user, a
row-wise split puts the same entity on both sides. The model recognizes the
entity rather than the pattern, and the score describes performance on entities
it has already seen - which no production request will be. The inflation is
large, routinely tens of points on the metric.

**Detection rule, and its approximation.** Whether ids actually repeat is a
property of data. The proxy is: a string literal that looks like an entity id
(`id`, `uuid`, `guid`, optionally prefixed, as a whole literal - `customer_id`,
`patient_id`, `session_uuid`), **and** that literal never appears in a `.drop`
column list, **and** a random split exists, **and** nothing is group-aware - no
`GroupKFold`, `GroupShuffleSplit`, `StratifiedGroupKFold`, `LeaveOneGroupOut` or
`LeavePGroupsOut`, and no `groups=` keyword passed anywhere.

**What clears it.** Dropping the id column, a group-aware splitter, or a `groups=`
argument.

**Where it is blind.** An id column that is unique per row is a false positive -
one row per customer means there is nothing to leak, and the checker cannot tell.
A grouping column with no id in its name (`household`, `account_number`,
`series`) is a false negative.

**The fix.** Use a group-aware split with `groups=` set to the entity column, or
aggregate to one row per entity before splitting. If ids are unique per row, drop
the column, which both silences the rule and removes a useless feature.

## PARSE_ERROR

**Severity: error.** Not a defect in the code being audited - a statement that
the file was not audited at all.

Emitted when a file cannot be read as UTF-8, exceeds the size limit, is not valid
notebook JSON, or cannot be parsed by the running interpreter. The message names
the running Python version, because the most common benign cause is a file using
syntax newer than the interpreter running the checker.

It is an error deliberately: **an unparsed file is not a clean file.** A checker
that skips what it cannot read and prints "clean" has told a lie that is worse
than a crash.

## NOTEBOOK_ORDER

**Severity: note.** Notes never affect the exit code.

Emitted once for every notebook with at least one code cell. Notebook cells are
read in cell order, and a notebook's execution order is not its cell order - a
cell can be run, edited, and run again, out of sequence, and the `.ipynb` file
records only the last state. Any rule that compares line numbers is therefore
unverifiable on a notebook.

The consequence: `FIT_BEFORE_SPLIT` and `RESAMPLE_BEFORE_SPLIT` are downgraded
from error to warning inside a notebook. The other rules do not depend on
ordering and keep their severity. Findings name the cell index, counting every
cell in the file including markdown.

To get the error-severity guarantee back, move the training code into a module,
or restart the kernel and run all cells so that execution order and cell order
agree.

## Judging a finding

Every finding needs one of three verdicts, and recording which keeps the checker
trustworthy.

1. **True and worth fixing.** Fix it.
2. **True and deliberate.** Leave a comment beside the line saying why. The
   random split of exchangeable dated rows is the usual case.
3. **False.** Note the pattern. A rule producing several false positives across
   real files is a rule to narrow, because a checker that fires on correct code
   gets muted, and a muted checker protects nothing.

Promoting a rule from warning to error is an ask-first decision, since it changes
the exit code and therefore anything that gates on it.

## What no static checker can find

The list matters as much as the catalog, because the codes above are the cheap
half of a review and reading them as the whole of it is the real risk.

- **Whether the target is the right target.** Horizon, population, proxy bias,
  and labels defined by the system being replaced.
- **Target leakage through a derived column.** `cancellation_reason` is a normal
  column name and a perfect predictor.
- **Whether the split's assumption is true.** Whether entities repeat, whether
  time matters, whether the test set is a different population.
- **The actual class balance**, or any other property of the data.
- **Point-in-time correctness.** An aggregate computed over all time looks
  identical in code to one computed as of the prediction moment.
- **Train/serve skew.** It lives in the difference between two files, in two
  repositories, often in two languages.
- **Whether the improvement is real.** The difference between two scores is an
  inference question and this skill does not answer it.
- **Whether the model should exist**, and whether its errors fall unevenly on
  people who cannot appeal them.

The checker is a tripwire for the mechanical half. The judgment pass is the
review.
