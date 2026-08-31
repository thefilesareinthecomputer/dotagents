# Pitfalls - the audit catalog

One entry per defect that can be detected in a described analysis. Each carries
a code, what it looks like, the rule that detects it, the cases where it is not
a finding, and the fix.

This is a checklist before it is a script. Every rule below can be applied by
reading a writeup; the auditor automates the mechanical ones against a described
analysis and cannot see anything that is not in what it was handed.

## Contents

1. [The analysis record](#1-the-analysis-record)
2. [Severity and precision](#2-severity-and-precision)
3. [Reporting completeness](#3-reporting-completeness)
4. [Search and selection](#4-search-and-selection)
5. [Evaluation](#5-evaluation)
6. [Language and interpretation](#6-language-and-interpretation)
7. [Data handling](#7-data-handling)
8. [Audit order](#8-audit-order)

## 1. The analysis record

The detection rules are stated against a description of an analysis, whether
that description is a JSON file or a paragraph of prose. The vocabulary:

| Key | Holds |
|---|---|
| `n_input`, `n_used`, `dropped` | Rows read, rows analyzed, and the count plus reason for each exclusion |
| `estimate`, `units` | The point estimate on its natural scale |
| `interval` | `lo`, `hi`, `level`, and the method that produced it |
| `effect_size` | Name and value |
| `p_value`, `alpha` | If a test was run |
| `method` | The test or estimator used, and the parametric assumption if one was made |
| `design` | `randomized`, `observational`, `simulated`, or `backtest` |
| `comparisons_tried` | How many variants, cutoffs, subgroups or models were fitted, and the correction applied |
| `evaluated_on` | `in_sample`, `holdout`, `cross_validation`, or `future_period` |
| `seed`, `reps` | For anything randomized |
| `assumption` | The assumption whose violation would overturn the conclusion |
| `claim` | The sentence the analysis is being used to support |

A missing key and a key set to null are the same thing for detection purposes:
both mean the analysis did not state it.

## 2. Severity and precision

**Error** means the stated conclusion is not supported by what was done.
**Warning** means the analysis may be right but a reader cannot verify it.

A checker that cries wolf gets muted, which is the failure mode this whole skill
is organized against. Every rule therefore carries a "not a finding when" clause
and none of them fires on ambiguity alone. When a rule cannot decide, it stays
silent and the omission is reported as a warning at most.

## 3. Reporting completeness

### MISSING_N

**Severity** error. **Looks like** any statistic, interval or test reported with
no sample size anywhere in the analysis.

**Why it is wrong.** Every number below is conditioned on n. A median of 4.2
from 8 observations and from 80,000 are different findings, and without n the
reader cannot tell which was produced.

**Detection.** A claim carries `estimate`, `p_value` or `interval` and `n_used`
is absent.

**Not a finding when** the analysis is a population census, stated as such, or
the record covers a deterministic computation rather than an inference.

**Fix.** Report n after exclusions, alongside n before them.

### MISSING_INTERVAL

**Severity** error. **Looks like** a point estimate presented as the answer -
"the median is 4.2", "accuracy is 0.91", "the effect is 3 percentage points".

**Why it is wrong.** A point estimate with no uncertainty invites a decision
that the data cannot support. The width is usually the finding.

**Detection.** A claim carries `estimate` and `interval` is absent.

**Not a finding when** the quantity is a descriptive fact about the dataset in
hand with no inference to a wider population - "this file has 1,204 rows" - or
the record is an exploratory summary explicitly labeled as such.

**Fix.** Bootstrap the estimate and report the interval with its level, reps and
seed.

### P_VALUE_WITHOUT_EFFECT_SIZE

**Severity** error. **Looks like** "significant at p = 0.03" with no statement
of how large the difference was.

**Why it is wrong.** A p-value confounds effect size with sample size. With
enough data any nonzero difference is significant, so significance alone
supports no decision.

**Detection.** `p_value` is present and both `effect_size` and `interval` are
absent.

**Not a finding when** the effect size appears in the claim text on its natural
scale even if the field is unset - the point is that the reader can see it.

**Fix.** Report the difference in original units with an interval, and put the
p-value after it.

### MISSING_ASSUMPTION

**Severity** warning. **Looks like** a conclusion with no statement of what
would overturn it.

**Why it is wrong.** Every inference rests on something unverifiable from the
data - independence, representativeness, stability, an untouched holdout. Naming
it converts a claim into something a reader can check.

**Detection.** A claim is present and `assumption` is absent.

**Not a finding when** the assumption is stated inline in the claim text.

**Fix.** One sentence: which assumption, and what evidence would falsify it.

### UNSEEDED_RESAMPLING

**Severity** error. **Looks like** a bootstrap interval or permutation p-value
with no seed recorded.

**Why it is wrong.** The result is not reproducible. A reader who reruns it and
gets a different third digit cannot tell an implementation change from
resampling noise.

**Detection.** `method` is a resampling method, or `reps` is present, and `seed`
is absent.

**Not a finding when** the method is exact enumeration of all rearrangements,
which involves no randomness.

**Fix.** Set a seed, print it, and store it in the record.

## 4. Search and selection

### UNCORRECTED_MULTIPLICITY

**Severity** error. **Looks like** the best of several models, cutoffs,
segments, windows or strategies reported as *the* result, with no mention of how
many were tried.

**Why it is wrong.** The maximum of many noisy estimates is biased upward, and
its nominal error rate is wrong by roughly the number of things tried. Searching
hard enough guarantees a winner.

**Detection.** Either `comparisons_tried` is greater than 1 with no correction
recorded, or the record contains multiple claims tested at the same alpha with
no family-wise or false-discovery correction, or the claim text contains a
superlative - best, top, optimal, the strongest - with `comparisons_tried`
absent.

**Not a finding when** a single hypothesis was fixed in advance and the record
says so, or the other comparisons are all reported alongside and labeled
exploratory.

**Fix.** State the count tried in the same sentence as the winner, apply Holm or
Benjamini-Hochberg, and validate the winner on data not used in the search.

### POST_HOC_HYPOTHESIS

**Severity** warning. **Looks like** a subgroup, a cutoff, a date window or an
exclusion rule that was chosen after looking at the outcome.

**Why it is wrong.** The comparison was selected from a large implicit family,
so its nominal error rate does not apply even though only one test was run.

**Detection.** The record contains an exclusion, a subgroup filter or a
threshold whose `chosen_before_data` flag is false or absent while a `p_value`
is reported, or the claim text describes a subgroup that is not part of the
stated primary comparison.

**Not a finding when** the analysis is labeled exploratory and makes no
confirmatory claim.

**Fix.** Label it exploratory, or confirm it on fresh data.

### THRESHOLD_WITHOUT_BASELINE

**Severity** warning. **Looks like** a cutoff shipped with no evidence of how
often it will fire - three sigma, a round number, a value borrowed from another
dataset.

**Why it is wrong.** A threshold is a decision about an alert rate. Set without
measuring the rate, it either fires constantly and gets ignored or never fires
and is mistaken for coverage.

**Detection.** A `threshold` is present and either `baseline_window` or
`expected_firing_rate` is absent.

**Not a finding when** the rule is a validity constraint rather than a
statistical one - a range, a type, a referential rule - since those have no
firing rate to estimate.

**Fix.** Derive it from a known-good baseline window and publish the expected
firing rate with it. See `robust-and-outliers.md` section 7.

### UNCITED_THRESHOLD

**Severity** warning. **Looks like** a named constant with no source - 3.5, 1.5
times the interquartile range, 0.05, a variance inflation factor of 10.

**Why it is wrong.** These are conventions with origins, and the origin usually
carries the conditions under which the convention applies. An uncited constant
cannot be argued with.

**Detection.** A `threshold` or `alpha` takes a conventional value and no
`source` is recorded.

**Not a finding when** the value was derived from this dataset's baseline and
the derivation is recorded, which is better than a citation.

**Fix.** Cite the source, or derive it. Never invent a citation - a fabricated
reference is a worse defect than an unsourced number.

## 5. Evaluation

### IN_SAMPLE_AS_PERFORMANCE

**Severity** error. **Looks like** an accuracy, error or fit measure computed on
the data the model was fit on, presented as what to expect next time.

**Why it is wrong.** A flexible enough model reproduces its training data
perfectly and predicts nothing. In-sample fit is an upper bound on performance,
not an estimate of it.

**Detection.** `evaluated_on` is `in_sample`, or is absent while the record
contains both a fitted model and a performance metric.

**Not a finding when** the number is explicitly labeled as in-sample fit and no
forward-looking claim is attached.

**Fix.** Evaluate on a holdout or by cross-validation, and report the interval
across folds.

### LEAKAGE_SUSPECTED

**Severity** error. **Looks like** a metric far better than the problem should
allow, a feature derived from the outcome, or preprocessing fitted before the
split.

**Why it is wrong.** The evaluation used information that will not exist at
prediction time, so the number describes nothing that can be repeated.

**Detection.** Any of - a feature name matching the outcome name or a known
derivation of it; scaling, imputation, encoding or feature selection recorded as
applied before the split; a time-ordered dataset split at random; a metric more
than a stated margin above the best published or previously observed value for
the task.

**Not a finding when** the suspicious feature is documented as legitimately
available before the prediction point.

**Fix.** Rebuild the split first, fit every transformation inside the training
fold only, and re-evaluate. Detecting leakage in a result is in scope here;
preventing it structurally in the code that produced the result is a separate
concern.

### NO_BASELINE

**Severity** warning. **Looks like** a model metric with nothing to compare it
to.

**Why it is wrong.** 94% accuracy is excellent or worthless depending on the
majority class share; an error of 3.1 units means nothing without the error of
predicting the mean, or last week's value.

**Detection.** A performance metric is present and no `baseline` is recorded.

**Not a finding when** the comparison is to a named prior model whose score is
in the record.

**Fix.** Report the trivial baseline - majority class, the mean, the previous
value - and the gap, with an interval on the gap.

### BACKTEST_AS_FORECAST

**Severity** error. **Looks like** a historical simulation reported as expected
future performance.

**Why it is wrong.** The strategy, the parameters and the period were all chosen
with knowledge of that history. The result is in-sample at the level of the
whole analysis even when each individual step looked out of sample.

**Detection.** `design` is `backtest` and the claim text makes a forward-looking
statement, or `comparisons_tried` is absent for a backtest, which is rarely
truthful.

**Not a finding when** the result is presented with the count of variants tried,
an out-of-period validation, and no forward claim.

**Fix.** Report the number of variants tried, validate on a period held out from
the whole process, and state costs and slippage explicitly.

## 6. Language and interpretation

### CAUSAL_LANGUAGE_OBSERVATIONAL

**Severity** error. **Looks like** "causes", "drives", "leads to", "increases",
"reduces", "impact of", "effect of" attached to an observational comparison.

**Why it is wrong.** Without randomization or an identification argument, the
association is consistent with a confounder, with reverse causation, and with
selection into the sample.

**Detection.** `design` is `observational` and the claim text contains causal
verbs, or reports a regression coefficient as an effect.

**Not a finding when** `design` is `randomized`, or an identification strategy
is recorded and the assumption it rests on is stated.

**Fix.** "Associated with", and name the confounder that would have to be ruled
out.

### SIGNIFICANCE_AS_IMPORTANCE

**Severity** warning. **Looks like** "a significant improvement" where the
effect is too small to act on, or a decision justified by significance alone.

**Why it is wrong.** Significance is a statement about compatibility with a null
hypothesis, not about magnitude. At large n it is nearly guaranteed.

**Detection.** A claim uses "significant" as its justification and the effect
size is below a recorded `minimum_effect_of_interest`, or no minimum was ever
stated.

**Not a finding when** the effect is reported on its natural scale next to the
decision threshold it is being compared against.

**Fix.** State the smallest difference that would change the decision, and
compare the interval to that.

### NULL_READ_AS_EQUIVALENCE

**Severity** warning. **Looks like** "no difference between the groups" resting
on a non-significant test.

**Why it is wrong.** Absence of evidence is not evidence of absence. With a wide
interval, the data is consistent with a large difference in either direction.

**Detection.** The claim asserts no difference or no effect while `p_value` is
above alpha and no equivalence margin is recorded.

**Not a finding when** an equivalence margin is recorded and the whole interval
falls inside it.

**Fix.** Report the interval, and run an equivalence test against a stated
margin if the claim of no difference matters.

### ADVICE_FRAMING

**Severity** error. **Looks like** a computed quantity turned into an
instruction - a stake, a position size, an allocation, a trade.

**Why it is wrong.** The arithmetic is a statistics question; the instruction
depends on the person's resources, horizon and tolerance for loss, none of which
is in the data. It also silently treats an estimated edge as a known one.

**Detection.** The claim text contains an imperative about money or risk-taking
attached to a computed quantity.

**Not a finding when** the quantity is reported as a calculation with its inputs
and their uncertainty, and no instruction is attached.

**Fix.** Report the calculation and the sensitivity of the output to the input
that is least certain. See `probability-and-betting.md`.

## 7. Data handling

### SILENT_ROW_DROPS

**Severity** error. **Looks like** n at the end being smaller than n at the
start, with nothing said about the difference.

**Why it is wrong.** Missingness is rarely random. The rule that dropped rows
is frequently correlated with the thing being measured, so the remaining sample
is not the population that was intended.

**Detection.** `n_input` differs from `n_used` and `dropped` is absent or does
not account for the difference.

**Not a finding when** every exclusion is listed with its count and reason.

**Fix.** Count the drops by reason, report them, and say whether the dropped
rows differ systematically from the kept ones.

### DEGENERATE_SPREAD

**Severity** error. **Looks like** an outlier detector flagging an implausible
share of rows, or a robust z of infinity.

**Why it is wrong.** A scale estimate of zero - which happens whenever more than
half the values are identical - makes every distinct value infinitely far from
the center. The detector is not finding anomalies, it is dividing by zero.

**Detection.** A robust scale estimate is zero, or the flagged share exceeds a
stated maximum, or the column's distinct-value count is very low relative to n.

**Not a finding when** the detector refused to run and said why, which is the
correct behavior.

**Fix.** Switch estimator or treat the column as categorical. See
`robust-and-outliers.md` section 4.

### DENOMINATOR_MISSING

**Severity** warning. **Looks like** a percentage, rate or ratio with no
statement of what it is over.

**Why it is wrong.** "Up 200%" from 1 to 3 and from 1,000 to 3,000 are different
facts, and a rate computed over a denominator that itself changed is
uninterpretable.

**Detection.** A claim reports a percentage, rate or ratio and no denominator or
count is present.

**Not a finding when** both numerator and denominator appear in the record.

**Fix.** Report the counts alongside the rate, and both the absolute and
relative change.

### PRECISION_OVERSTATED

**Severity** warning. **Looks like** an estimate carrying more digits than the
sample can support - 0.6231 from 30 observations.

**Why it is wrong.** Reported digits are a claim about precision. Digits beyond
the interval width invite a reader to treat noise as signal.

**Detection.** The number of significant digits in `estimate` implies a
precision finer than a tenth of the interval width.

**Not a finding when** full precision is being carried deliberately for a
downstream computation rather than presented as a result.

**Fix.** Round at the presentation layer only, to the interval width. Never
round inside a computation.

## 8. Audit order

1. Fix the errors. Each one means the stated conclusion is not supported.
2. Then the warnings, which mostly mean a reader cannot verify what was done.
3. Re-run and confirm the finding count went to zero for the codes addressed,
   rather than assuming a fix landed.
4. Record any finding kept deliberately, with the reason, so the next audit does
   not rediscover it as new.

What no audit can see: whether the sample was representative, whether the column
means what its name says, whether the holdout was contaminated before the file
arrived, and whether the question being answered is the one that was asked. A
clean audit means no listed defect was visible. It is not approval.
