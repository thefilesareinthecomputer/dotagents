# Inference

Turning a sample into a claim about something larger, with the uncertainty
attached. Intervals first, tests second, effect sizes always, and a hard look at
how many comparisons were made before the winner was picked.

## Contents

1. [Intervals, and what they do not mean](#1-intervals-and-what-they-do-not-mean)
2. [The bootstrap](#2-the-bootstrap)
3. [Permutation tests](#3-permutation-tests)
4. [Parametric tests and what each one assumes](#4-parametric-tests-and-what-each-one-assumes)
5. [p-values, stated correctly](#5-p-values-stated-correctly)
6. [Effect sizes](#6-effect-sizes)
7. [Power and sample size](#7-power-and-sample-size)
8. [Multiplicity](#8-multiplicity)
9. [Showing there is no difference](#9-showing-there-is-no-difference)
10. [A reporting template](#10-a-reporting-template)

## 1. Intervals, and what they do not mean

A 95% confidence interval is a statement about the procedure - across repeated
samples from the same process, intervals built this way contain the true value
95% of the time. It is not a 95% probability that this particular interval
contains the value, and treating it as one is harmless in casual use and
misleading in a decision.

What matters in practice:

- **The width is the finding.** An interval from -2% to +14% and one from +5% to
  +7% can share a point estimate and support entirely different decisions. Lead
  with the interval, not the center.
- **An interval that includes zero does not establish no effect.** It says the
  data is consistent with a range that happens to include zero. See section 9.
- **Coverage is only as good as the assumptions.** Dependence between
  observations is the usual cause of an interval that is too narrow, and no
  amount of data fixes it.
- **State the level.** "95%" is a convention, not a default of nature. If a
  different level was used, say which and why.

For a proportion, the textbook normal approximation misbehaves near 0 and 1 and
at small n. Use the Wilson score interval (Wilson 1927), which stays inside
[0, 1] and holds its coverage far better at the extremes.

## 2. The bootstrap

Resample the observed data with replacement, recompute the statistic each time,
and read the interval off the distribution of those recomputations. It needs no
formula for the statistic's sampling distribution, which is why it is the
default here - medians, trimmed means, ratios, differences in percentiles and
metric scores all get intervals the same way. Reference: Efron and Tibshirani,
*An Introduction to the Bootstrap* (1993).

Defaults that matter:

- **Reps.** 10,000 for a reported interval. 1,000 is enough while exploring and
  visibly jittery at the tails.
- **Seed.** Always set and always printed. Two runs of an unseeded bootstrap
  disagree in the third digit, and a reader cannot tell that from a real change.
- **Percentile, not BCa, by default.** The bias-corrected accelerated interval
  needs an extra jackknife pass, and its accuracy gain does not survive the
  small samples this is mostly used on. Choosing the simpler one deliberately is
  different from not knowing about the other.

Where the bootstrap fails, and these are not rare:

- **Extremes.** The maximum, the minimum, or a quantile out past the data. The
  resample can never exceed the observed maximum, so the interval is wrong in a
  way that looks fine.
- **Very small n.** Below about 10 the resampling distribution is too coarse;
  below 5 it is a rearrangement of a handful of values.
- **Dependent observations.** Resampling rows destroys the dependence structure
  and produces an interval that is too narrow. Resample blocks or clusters
  instead, and say that is what was done.
- **Heavy ties.** A column with three distinct values gives a bootstrap
  distribution with three spikes. The interval is technically computed and
  practically meaningless.

## 3. Permutation tests

Under the hypothesis that a label carries no information, the labels can be
shuffled. Shuffle them many times, recompute the statistic, and see how often
chance alone produces something as extreme as what was observed. That count is
the p-value, and it required no distributional assumption at all.

- Works for any statistic - difference of means, of medians, of proportions, of
  trimmed means, a correlation, a metric gap between two models.
- Exact when the number of distinct rearrangements is small enough to enumerate.
  Sample them otherwise, with a seed.
- The exchangeability requirement is real: shuffling has to be meaningless under
  the null. With paired data, permute within pairs. With time order or
  clustering, plain shuffling destroys structure the null does not claim is
  absent, and the test becomes anti-conservative.

## 4. Parametric tests and what each one assumes

Parametric tests earn their place at small n, in standard designs, and when a
matching power calculation is needed. Each one is listed here with the
assumption whose violation would overturn its conclusion.

| Test | Answers | Assumption that breaks it |
|---|---|---|
| One-sample t | Is the mean different from a reference | Independence; approximate normality of the *mean*, which is usually fine by n around 30 unless the data is heavily skewed or has extreme values |
| Welch two-sample t | Do two groups differ in mean | Independence; skew or outliers pulling the means. Prefer Welch over the equal-variance form always - it costs nothing when variances are equal |
| Paired t | Do paired measurements differ | The pairing is genuine; the *differences* are approximately symmetric |
| Mann-Whitney U | Does one group tend to exceed the other | Independence. Note it tests stochastic dominance, not medians, unless the distributions have the same shape |
| Wilcoxon signed-rank | Do paired differences center on zero | The differences are symmetric about their center |
| Chi-square of independence | Are two categorical variables associated | Expected count of about 5 per cell; independent observations. Use an exact test when counts are small |
| One-way analysis of variance | Do several group means differ | Independence, similar variances, approximate normality. A significant result says "not all equal" and nothing about which |
| F test of variances | Do two spreads differ | Extremely sensitive to non-normality. Prefer Levene or a bootstrap on the ratio of spreads |

The equal-variance t test, the F test on variances, and the chi-square at low
counts are the three where the assumption is violated most often in practice.

## 5. p-values, stated correctly

A p-value is the probability of data at least this extreme *if the null
hypothesis were true and the analysis was fixed in advance*. It is not the
probability the null is true, not the probability the finding replicates, and
not a measure of effect size. The American Statistical Association's statement
(Wasserstein and Lazar 2016) says exactly this, and it is worth citing when a
reader wants the number to mean more than it does.

Consequences worth acting on:

- **A p-value alone is not a result.** Effect size and interval beside it, or do
  not report it.
- **0.05 is a convention.** It came from convenience and became a ritual. Say
  what threshold was used and why that one.
- **"Not significant" is not "no effect".** With small n, almost nothing is
  significant. See section 9.
- **A p-value from a comparison chosen after seeing the data is not a p-value.**
  Section 8.
- **Two p-values on either side of the threshold are not different from each
  other.** The comparison of significance is not the significance of the
  comparison; test the difference directly.

## 6. Effect sizes

The effect size answers the question that was actually being asked. Report it
first, on the natural scale, then a standardized version if one helps
comparison.

| Situation | Report | Notes |
|---|---|---|
| Two group means | Difference in the original units, with an interval | Always lead with this. "4.2 minutes slower (95% CI 1.1 to 7.3)" needs no translation |
| Two groups, standardized | Cohen's d | Conventions 0.2 small, 0.5 medium, 0.8 large come from Cohen (1988) and are conventions, not laws; they are wrong in fields where a 0.05 shift matters |
| Two groups, skewed or ordinal | Difference in medians, or Cliff's delta (Cliff 1993) | Robust to the outliers that inflate or deflate d |
| Two proportions | Difference in percentage points, and the ratio | Give both - a rise from 0.1% to 0.2% is +0.1 points and a doubling, and one of those framings is misleading depending on the audience |
| Association between two continuous variables | Correlation, plus r-squared as the share of variance | r of 0.3 means about 9% of variance, which is usually less impressive than the correlation sounded |
| A count outcome | Rate difference and rate ratio, with the denominators | A ratio with no denominator is not interpretable |

Two habits that catch most errors: state the smallest difference that would
change the decision before looking at the estimate, and compare the interval to
that number rather than to zero.

## 7. Power and sample size

Power is the probability of detecting an effect of a stated size if it is
really there. The calculation needs four quantities and gives the fifth: effect
size, alpha, power, sample size, and the variability of the measure.

- **The input nobody wants to supply is the minimum effect worth detecting.**
  Without it the question has no answer. Getting it stated is most of the work,
  and it is a decision question, not a statistical one - what change would be
  large enough to act on?
- **Rules of thumb are for orientation only.** For a two-group comparison of
  means at alpha 0.05 and 80% power, required n per group is roughly 16 divided
  by d squared - so about 64 per group for d = 0.5, 400 for d = 0.2. Use it to
  find out whether the study is off by a factor of ten, then compute it for the
  design in hand.
- **Post-hoc power computed from the observed effect is uninformative.** It is a
  deterministic function of the p-value and adds nothing (Hoenig and Heisey,
  "The Abuse of Power", *The American Statistician*, 2001). When a
  non-significant result needs interpreting, report the interval, or run an
  equivalence test - see section 9.
- **Power for a resampling test.** Simulate. Generate data with the effect you
  care about, run the actual test, count the rejections. Slower than a formula
  and correct for the test you are really using.
- **Attrition, clustering and multiplicity all raise the requirement.** Inflate
  for expected missingness, use the number of clusters rather than rows when
  units are grouped, and account for a corrected alpha when several outcomes
  will be tested.

## 8. Multiplicity

Test twenty independent nulls at alpha 0.05 and one significant result is the
expected outcome of pure chance. Every analysis that searches - across
variables, cutoffs, subgroups, windows, model configurations - has this problem,
and the searching is usually invisible in the writeup.

**The detection question is always "how many were tried?"** Not how many were
reported. Every fitted variant, every discarded cutoff, every subgroup looked at
and set aside counts.

| Correction | Controls | Use when |
|---|---|---|
| Bonferroni - multiply each p by the number of tests | Family-wise error rate | Few tests, and a false positive is expensive. Conservative, especially when tests are correlated |
| Holm (1979) - step-down sequential | Family-wise error rate | Almost always preferable to Bonferroni; uniformly more powerful with the same guarantee |
| Benjamini-Hochberg (1995) | False discovery rate | Many tests, screening for candidates, where a proportion of false leads is acceptable |
| Pre-registration of one primary outcome | The problem itself | The comparison that matters is decided before the data is seen; everything else is labeled exploratory |

The subtler version has no test count to correct at all: the analysis choices
themselves - which rows to exclude, which transform, where to cut a continuous
variable - were made after seeing the data, so a single reported test was
selected from a large implicit family. Gelman and Loken called this the garden
of forking paths (2013; *American Scientist*, 2014). The defense is to fix the
analysis before looking, or to label the result exploratory and hold it to a
confirmation on fresh data.

Practical rule: when reporting the best of several things, report the count of
things tried in the same sentence. "The best of 40 configurations scored 0.91"
is honest; "the model scored 0.91" from the same run is not.

## 9. Showing there is no difference

A non-significant test does not support "no difference". To claim that, decide
in advance what counts as equivalent and test for it.

- **Equivalence testing.** Set a margin - the largest difference that would be
  practically irrelevant - and show the whole interval falls inside it. The
  two-one-sided-tests procedure is the standard form, and the bootstrap does the
  same job by checking whether the interval fits within the margin.
- **The interval carries the answer either way.** An interval of -0.5 to +0.4
  percentage points against a margin of 2 points supports equivalence. An
  interval of -15 to +18 supports nothing, whatever its p-value.
- **Say which one you have.** "No evidence of a difference" and "evidence of no
  difference" are different findings and the first is often reported as the
  second.

## 10. A reporting template

A result stated this way is auditable, and everything the auditor looks for is
present:

> Group B was 4.2 minutes slower than group A (95% bootstrap CI 1.1 to 7.3,
> 10,000 reps, seed 7; n = 118 and 122 after dropping 6 rows with a missing
> timestamp; permutation p = 0.004 over 10,000 shuffles). This was the primary
> comparison, fixed before the data was pulled; two secondary comparisons were
> also run and are reported below with a Holm correction. The conclusion rests
> on the two groups being independent samples from the same period - the rows
> are one per session and sessions from the same account are not independent, so
> the interval is likely optimistic.

Length is not the point. Every clause in it is something a reader would
otherwise have to assume.
