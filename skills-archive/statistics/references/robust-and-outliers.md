# Robust statistics and outliers

Summarizing a column that contains a few values unlike the rest, and deciding
which of them deserve attention. The failure here is not usually a wrong
formula - it is a detector that fires on everything, gets ignored within a week,
and is still switched on months later while nobody reads it.

## Contents

1. [Decide what the outlier is for, first](#1-decide-what-the-outlier-is-for-first)
2. [Why the mean and standard deviation fail](#2-why-the-mean-and-standard-deviation-fail)
3. [MAD and the modified z-score](#3-mad-and-the-modified-z-score)
4. [The degenerate case](#4-the-degenerate-case)
5. [Trimmed and winsorized statistics](#5-trimmed-and-winsorized-statistics)
6. [Skewed data needs an asymmetric rule](#6-skewed-data-needs-an-asymmetric-rule)
7. [Choosing the threshold by firing rate](#7-choosing-the-threshold-by-firing-rate)
8. [The detector menu](#8-the-detector-menu)
9. [What to do with a flagged value](#9-what-to-do-with-a-flagged-value)
10. [More than one variable at a time](#10-more-than-one-variable-at-a-time)

## 1. Decide what the outlier is for, first

Three different jobs get the same name, and they call for different rules:

- **Protect a summary.** The mean and standard deviation are being distorted by
  a few values, and the goal is a number that describes the bulk. Use a robust
  estimator and stop; nothing needs flagging.
- **Find a defect.** A value is impossible or was recorded wrong - a negative
  duration, a duplicated batch, a unit that changed. The rule should be a
  validity rule wherever one exists, because "impossible" beats "unusual" every
  time.
- **Find something interesting.** The extreme value is the signal. Then the
  detector's false-positive rate is a budget, and section 7 applies.

Deciding which one is in play stops the most common mistake, which is deleting
the values that were the reason for looking.

## 2. Why the mean and standard deviation fail

Breakdown point is the fraction of the data that has to be corrupted before an
estimator can be moved arbitrarily far. The mean and standard deviation have a
breakdown point of 0 - one value large enough moves either of them anywhere. The
median and the median absolute deviation have a breakdown point of 50%.

That has a direct consequence for detection: an outlier inflates the very
standard deviation it is being compared against. A classical z-score of a single
large value in a small sample can never exceed (n-1)/sqrt(n), so with n = 10 no
point can score above about 2.85 no matter how extreme it is, and a rule of
"flag above 3" flags nothing at all. This is why detection uses a robust scale
rather than the standard deviation.

## 3. MAD and the modified z-score

The median absolute deviation is the median of the absolute deviations from the
median. On normal data it estimates the standard deviation once multiplied by
the consistency factor 1.4826, which is what makes MAD-based thresholds
comparable to sigma-based ones.

The modified z-score is `0.6745 * (x - median) / MAD`, where 0.6745 is the same
constant expressed the other way round. **The conventional cutoff is 3.5**,
from Iglewicz and Hoaglin, *How to Detect and Handle Outliers* (ASQC, 1993).
Treat 3.5 as a starting point with a citation, not as a law - section 7 is how
it gets set for real data.

Why it is the default detector here: it needs only the standard library, it
does not assume normality to be useful, and it does not get dragged around by
the points it is looking for.

## 4. The degenerate case

**MAD is exactly 0 whenever more than half the values are identical.** That is
common rather than exotic: status flags, mostly-zero amounts, a column with a
default that is rarely overridden, a counter that only sometimes increments.

When MAD is 0, every value that differs from the median gets an infinite
modified z and is flagged. A detector in this state reports that 4% of rows are
outliers, every run, forever, and it is the single most likely reason an
automated check is ignored.

Refuse rather than divide. The right response is to say the column has no scale
to measure against and offer the alternatives:

- **Mean absolute deviation about the median** as the scale instead. It has a
  lower breakdown point but is nonzero whenever any value differs.
- **Quantile-based rules**, if enough distinct values exist to define quantiles.
- **Treat the column as categorical** and monitor the frequency of each value
  instead of its distance from a center. For a mostly-constant column this is
  almost always the right answer - what matters is that the rare value appeared,
  not how far it is from the common one.
- **Rules on a derived quantity** - the count of nonzero rows per batch, the
  share of rows taking the default - which has a scale even when the raw column
  does not.

The same trap appears in a weaker form when a column has few distinct values:
MAD is nonzero but coarse, so the modified z takes a handful of possible values
and the threshold either catches all of a value or none of it. Report the
distinct-value count next to any threshold decision.

## 5. Trimmed and winsorized statistics

Two ways to stop extremes from dominating a summary, and they answer different
questions:

- **Trimmed mean.** Discard the lowest and highest k% and average the rest. 10%
  or 20% trimming is standard. The result estimates the center of the bulk and
  is not an estimate of the total.
- **Winsorized mean.** Replace the lowest and highest k% with the nearest
  retained value rather than dropping them. Keeps n intact, which matters when
  the count is part of the reporting.
- **Median.** The limiting case of trimming, maximally robust, and insensitive
  to how far out the extremes are - which is a drawback when their magnitude is
  part of the question.

Choose by what the number is for. If the extremes are real and the total
matters - the sum of amounts, the total time spent - trimming answers the wrong
question, and the honest report is the untrimmed figure plus a note on how much
of it comes from the top few observations. Say which estimator was used and how
much was trimmed; a "mean" that was quietly trimmed is a misreported number.

## 6. Skewed data needs an asymmetric rule

Amounts, durations and counts are usually right-skewed with a hard floor at
zero. A symmetric rule on skewed data flags the long tail continuously while
never flagging anything low, which is exactly wrong when the low side is where
the failure lives.

Options, in order of preference:

1. **Work on a transformed scale.** Take logs of a positive, multiplicatively
   varying quantity, then apply the ordinary rule. A 10x jump is the same
   distance whether it starts at 10 or 10,000, which is usually the intent.
2. **Use quantile-based fences.** Flag below the 0.1st percentile or above the
   99.9th of a baseline window. This makes the firing rate explicit by
   construction - see section 7 - and is the easiest rule to explain.
3. **Use an adjusted rule that accounts for skew.** The adjusted boxplot of
   Hubert and Vandervieren (*Computational Statistics and Data Analysis*, 2008)
   scales the fences by a robust skewness measure.

Whichever is used, check both directions separately. The interesting failure is
often a drop to zero, not a spike.

## 7. Choosing the threshold by firing rate

The threshold is a decision about how many alerts are acceptable, and it should
be set that way round.

1. **Take a baseline window of known-good history.** Long enough to cover the
   normal cycles - weekly and monthly patterns - and containing no incident. If
   it contains an incident, that event is now part of "normal" and the detector
   will never catch its recurrence.
2. **Compute the candidate statistic over that window**, on the same scale and
   with the same aggregation the live check will use.
3. **Read the empirical firing rate at several thresholds.** How many points in
   the baseline would this have flagged - per run, per day, per week.
4. **Pick the threshold from the alert budget**, not from tradition. Someone has
   to look at each alert. One a week that gets read beats one a day that does
   not.
5. **Report the expected rate with the threshold.** A gate shipped without a
   stated expected firing rate is untested, whatever the arithmetic behind it.
6. **Re-derive on a schedule.** Baselines age. A threshold set against last
   year's volume becomes either mute or constant.

Two more things worth stating in the same breath: the estimated false-positive
count over the baseline, and what happens on a flag - see `data-quality.md` for
whether a check should block or notify.

## 8. The detector menu

| Method | Good for | Disqualified when |
|---|---|---|
| Modified z on MAD, cutoff 3.5 | General numeric column, moderate skew, the default | MAD is 0, or the column has few distinct values |
| Tukey fences at 1.5 IQR (Tukey, *Exploratory Data Analysis*, 1977) | Quick visual rule, familiar to everyone | Strong skew - flags the tail permanently; also flags roughly 0.7% of normal data by construction |
| Quantile fences from a baseline window | When the firing rate must be known in advance | Baseline too short to estimate the quantile - a 99.9th percentile needs thousands of points |
| Classical z above 3 | Nothing, in practice | Almost always - it is inflated by the very points it hunts, and it is capped at small n |
| Grubbs test | A single outlier in approximately normal data | More than one outlier - they mask each other; non-normal data |
| Validity rules - range, type, referential | Impossible values | Never disqualified. Do these first; they need no statistics and produce no false positives |

Rousseeuw and Croux (*Journal of the American Statistical Association*, 1993)
give Sn and Qn as more efficient robust scale estimators than MAD when the data
is not symmetric; they matter when MAD's efficiency is the binding constraint,
which is rarely the case for a threshold.

## 9. What to do with a flagged value

Never delete it silently. The order of operations:

1. **Count and report** how many were flagged, out of how many rows.
2. **Look at them.** A handful of flagged values is a readable list, and reading
   it identifies the cause more often than any test does.
3. **Classify.** Impossible value, recording error, a genuine rare event, or a
   change in what the column means.
4. **Act by class.** Impossible values are excluded, with the count reported.
   Genuine rare events stay in, and if they distort the summary the summary
   changes to a robust one rather than the data changing.
5. **Report both ways when it matters.** If the conclusion flips depending on
   whether extreme values are included, that is the finding - state it, do not
   pick the version that reads better.

## 10. More than one variable at a time

A point can be ordinary on every individual axis and impossible in
combination - a small area with many rooms, a short duration with a large total.
Per-column detection cannot see it.

- **Mahalanobis distance** is the standard multivariate measure but uses the
  mean and covariance, so it has the breakdown problem of section 2 in a worse
  form. Robust covariance estimation is the fix and is beyond the standard
  library.
- **Regression residuals** are often the more useful route - fit the expected
  relationship and look at what departs from it. See `regression.md`, including
  the distinction between a large residual and a high-leverage point.
- **A ratio of the two columns** is usually the practical answer and needs no
  new machinery.
