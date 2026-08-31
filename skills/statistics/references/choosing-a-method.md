# Choosing a method

The method follows from the shape of the question and the shape of the data, and
almost every wrong answer starts by skipping straight to a familiar test. This
file goes question first, names the default, and names what disqualifies it.

## Contents

1. [Answer these four before choosing anything](#1-answer-these-four-before-choosing-anything)
2. [The question-shape table](#2-the-question-shape-table)
3. [Independence is the assumption that fails silently](#3-independence-is-the-assumption-that-fails-silently)
4. [What `auto` should pick](#4-what-auto-should-pick)
5. [Small samples](#5-small-samples)
6. [Time order changes the answer](#6-time-order-changes-the-answer)
7. [When nothing fits](#7-when-nothing-fits)
8. [The question behind the question](#8-the-question-behind-the-question)

## 1. Answer these four before choosing anything

**What is being measured, and in what units?** Continuous, ordinal, binary,
count, or a ratio of two counts. A method that assumes a scale cannot be run on
a category code, and an ordinal scale (1 to 5, "low/medium/high") averaged as if
it were continuous produces a number with no defensible unit.

**How many groups, and are they paired?** One sample against a reference, two
independent groups, two measurements on the same units, or many groups. Paired
data analyzed as independent throws away the pairing and loses most of the
power; independent data analyzed as paired invents a correspondence that is not
there.

**Are the observations independent?** See section 3. This is the assumption
that most often fails and the one least often checked.

**Was the hypothesis fixed before the data was seen?** If the comparison was
chosen after looking - this subgroup, this cutoff, this window - the nominal
error rate is wrong and section 6 of `inference.md` applies before anything
else.

## 2. The question-shape table

| The question | Default method | Disqualified when |
|---|---|---|
| Is this difference between two groups real? | Permutation test on the difference, plus a bootstrap interval on the difference | Observations are clustered or repeated; groups were defined after seeing the outcome |
| How big is the difference? | Effect size with a bootstrap interval | Nothing disqualifies this - it is the better question in every case |
| Is this proportion different from that one? | Difference of proportions with an interval; permutation or an exact test at small counts | Denominators measure different populations; any cell count below about 5 rules out the normal approximation |
| Is this one number different from a known reference? | One-sample interval on the estimate; check whether the reference is itself an estimate | The reference came from the same data |
| Are these two variables related? | Correlation with a bootstrap interval, after looking at the scatter | Relationship is not monotone; a few points dominate; the range was restricted by selection |
| Does X explain or predict Y? | Regression, with diagnostics - see `regression.md` | Predictors were chosen by searching over many candidates without saying so |
| Is this value unusual? | Robust z against a baseline - see `robust-and-outliers.md` | Over half the values are identical, which leaves no scale |
| Is this streak or run meaningful? | Permute the sequence and compare the observed longest run to the permutation distribution | The streak's start and end were chosen after seeing it |
| How large a sample do I need? | Power analysis from the smallest effect worth detecting | No minimum effect has been stated - then this is unanswerable, not hard |
| Which of these many options is best? | Report the count of options tried and correct for it before naming a winner | Only the winner survives into the writeup |
| Did the change cause the improvement? | Only a randomized assignment or an explicit identification design supports that word | Assignment was observational - describe association and name the confounder |
| Has this drifted from its usual behavior? | Compare against a baseline window - see `data-quality.md` | The baseline window contains the event being tested |

## 3. Independence is the assumption that fails silently

Nearly every standard interval and test assumes the observations are
independent draws. Real data violates this constantly and the violation does not
announce itself: the estimate stays reasonable while the interval becomes far
too narrow, so the result looks more certain than it is.

The common violations, in the order they show up:

- **Repeated measures.** Several rows per subject, per account, per device, per
  session. Ten rows from one unit is not ten observations. Aggregate to one row
  per unit first, or use a method that models the grouping.
- **Time order.** Consecutive observations resemble each other. See section 6.
- **Clustering.** Units share a location, a team, an operator, a batch. The
  effective sample size is closer to the number of clusters than the number of
  rows.
- **Selection into the sample.** Whoever responded, whoever survived long enough
  to be in the table, whoever the query's join happened to keep. This biases the
  estimate as well as the interval, and no test fixes it.

When independence is doubtful, the honest move is to say so with the result and,
where possible, quantify it - resample whole clusters instead of rows, and the
interval widens to something believable.

## 4. What `auto` should pick

`stats.py test --method auto` resolves to a resampling method in every case
where one exists, because those need no distributional assumption:

| Situation | Resolves to |
|---|---|
| Two independent groups, continuous | Permutation test on the difference of means, with a bootstrap interval on that difference |
| Two independent groups, binary | Permutation test on the difference of proportions |
| Paired measurements | Permutation on the sign of the paired differences |
| More than two groups | Permutation on a variance-ratio statistic, followed by pairwise comparisons with a multiplicity correction |
| One sample against a reference | Bootstrap interval on the estimate, checked against the reference |

Pass an explicit `--method` to override, and state in the writeup why the
parametric alternative was chosen. Legitimate reasons exist - a very small
sample where the permutation distribution is coarse, a design whose parametric
form is standard in the field, a need for a power calculation that matches the
test. "It is what I know" is not one.

## 5. Small samples

Sample size does not change the logic, it changes what can be concluded.

- **n below about 5 per group.** Describe. Report every value if there are few
  enough to print. A test on four observations answers a question nobody should
  be asking of four observations.
- **n between 5 and 20.** Permutation tests are exact here and are the right
  tool - with n small enough, enumerate all rearrangements instead of sampling
  them. Intervals will be wide, and reporting the width honestly is the whole
  contribution.
- **Bootstrap needs enough distinct values to resample.** With n under about 10
  the percentile interval's coverage degrades, and with heavy ties it can
  collapse to a point. Report the number of distinct values alongside n when
  that is a risk.
- **A large n does not rescue a biased sample.** Precision around the wrong
  center converges on being confidently wrong.

## 6. Time order changes the answer

If rows have an order in time, treat that as a property of the data, not a
column to ignore.

- Consecutive values are usually correlated, which breaks the independence
  assumption and inflates apparent significance.
- The mean and variance may not be stable over the window, in which case a
  single summary describes no period in particular.
- Comparing a "before" period to an "after" period picks up every other thing
  that changed at the same time. A comparison group that experienced the change
  in timing but not the intervention is worth more than a bigger sample.
- Any split for evaluation must respect the order: fit on earlier, test on
  later, never shuffle.

Diagnostics for correlation across time and for stability of the mean and
variance are in `market-and-forecasting.md`, which is where they matter most,
but the checks themselves are general.

## 7. When nothing fits

Some questions cannot be answered with the data in hand, and saying which is
more useful than producing a number anyway. The pattern to follow:

1. Describe what is there - n, center, spread, the extremes, the missingness.
2. Name what the question needs that the data lacks: a control group, a
   pre-period, an independent sample, a randomized assignment, a stated minimum
   effect, more units rather than more rows per unit.
3. Say what could be concluded if that were obtained, and roughly how much of
   it would be needed.

This is a real answer. A test run on data that cannot support it is not.

## 8. The question behind the question

"Is it significant?" is almost never the underlying question. It is usually a
proxy for one of these, and answering the real one avoids a whole class of
error:

| What was asked | What is usually wanted | What to produce |
|---|---|---|
| Is it significant? | Is the difference big enough to act on? | Effect size with an interval, next to the smallest difference that would change the decision |
| Is it random? | Could chance alone produce this? | The distribution under chance, and where the observation sits in it |
| What is the probability it is real? | A statement about the hypothesis | Say plainly that a p-value is not that probability, then give the interval |
| Can we predict it? | Does it predict out of sample? | An out-of-sample estimate with an interval, against a trivial baseline |
