# Automated data checks

Setting the numbers inside a recurring check on a dataset - what to compare
against, where the threshold goes, how often it is allowed to fire, and what
should happen when it does. The statistics question here is narrow and it is the
one that decides whether the check survives contact with production: **a
threshold nobody derived from a baseline gets muted within a week, and a muted
check is worse than no check because it looks like coverage.**

## Contents

1. [Validity rules before statistics](#1-validity-rules-before-statistics)
2. [What is worth measuring](#2-what-is-worth-measuring)
3. [Baseline windows](#3-baseline-windows)
4. [Drift, anomaly and breakage](#4-drift-anomaly-and-breakage)
5. [The alert budget](#5-the-alert-budget)
6. [Many columns is a multiplicity problem](#6-many-columns-is-a-multiplicity-problem)
7. [Block, notify, or record](#7-block-notify-or-record)
8. [What a gate definition must state](#8-what-a-gate-definition-must-state)
9. [How checks fail](#9-how-checks-fail)

## 1. Validity rules before statistics

A rule that encodes something known to be true has no false positives and needs
no baseline. Exhaust these first:

- Type, range and sign. A negative quantity, a date in 1970, a percentage above
  100.
- Uniqueness of a key, on every row rather than a sample.
- Referential rules - every child has a parent.
- Arithmetic identities - components sum to their total, a rate equals its
  numerator over its denominator.
- Non-null on columns contractually required to be populated.

Statistical checks exist for what cannot be stated as a rule: "this is more than
usual", "this looks different from last week". They come with a false-positive
rate by construction, and budgeting that rate is the rest of the job.

## 2. What is worth measuring

Ordered by how often each catches a real problem for the effort it costs:

| Signal | Catches | Note |
|---|---|---|
| Freshness - time since the last successful update | Everything stopped | Cheapest and highest yield. An absence of new data reads as success in most systems |
| Row count per batch, against its own history | Partial loads, a filter that changed, a duplicated run | Compare against the same weekday, not against yesterday |
| Null rate per column | An upstream field that stopped being populated | Movement matters more than the level. A column that was 2% null and is now 40% is a change even though neither is alarming alone |
| Distinct-value count | A code list that gained or lost members, a key that changed shape | Use exact counts to decide, approximate ones only to shortlist |
| Distribution of a numeric column - median and a robust spread | A unit change, a currency change, a rescaled source | Robust summaries, not the mean, or one bad batch sets the baseline |
| Category share | A new value appearing, an old one vanishing | Often the earliest visible sign of an upstream schema change |
| Cross-source agreement on a shared measure | Two systems that have diverged | Report the size of the disagreement with an interval, not a pass or fail |

## 3. Baseline windows

Every statistical check compares now against a period of known-good history. The
window choice does more damage than the threshold choice.

- **Long enough to cover the cycles that exist.** If the quantity has a weekly
  pattern, a window that is not a whole number of weeks builds the pattern into
  the baseline as noise. Compare like periods - this Monday against previous
  Mondays.
- **It must not contain the incident.** A baseline that includes the outage, the
  double-load or the migration has learned that behavior as normal and will
  never flag it again. Exclude known incidents explicitly and keep the list of
  what was excluded.
- **Rolling or fixed, chosen deliberately.** A rolling window adapts to genuine
  change and will also absorb a slow degradation without ever firing. A fixed
  reference period catches drift but goes stale and eventually fires on
  legitimate growth. For anything where slow decay is the risk, keep a fixed
  reference alongside the rolling one.
- **Long enough for the statistic being estimated.** A 99.9th percentile fence
  needs thousands of baseline points. With 40 points, only coarse quantiles are
  estimable and the threshold should be stated in those terms.
- **Report the window with the threshold.** "Above 3.5 modified z against the
  trailing 28 days, excluding 3 known incident days" is a check somebody can
  audit. "Above 3.5 modified z" is not.

## 4. Drift, anomaly and breakage

Three signals get conflated into one alert, and they need different responses.

| | What it looks like | Right response |
|---|---|---|
| **Breakage** | A discontinuity - zero rows, all nulls, a new value in every row | Block. This is a defect, not a signal |
| **Anomaly** | One period departs from a stable baseline, then returns | Notify and investigate. Do not adjust the baseline |
| **Drift** | The baseline itself moves over months | Neither block nor ignore. Re-derive thresholds, and confirm the change is legitimate before doing so |

Distinguishing drift from a long anomaly requires time, so a check cannot do it
alone. Practical approach: alert on the point event, and separately review the
baseline's own trend on a schedule. A slow slide is invisible to any check whose
reference window slides with it.

Watch for the trap in the reverse direction: a legitimate change - a new region,
a pricing change, an added source - will trip every distributional check at
once. Simultaneous firing across unrelated columns is evidence of a legitimate
change or a pipeline-wide problem, not evidence of many independent anomalies.

## 5. The alert budget

Set the number of alerts a person will actually read, then derive thresholds to
fit it. The arithmetic is unforgiving and usually skipped.

1. Decide the acceptable alert rate - per day or per week, per person.
2. Count the checks running at that cadence.
3. The per-check false-positive rate that fits the budget is the first number
   over the second. Twenty checks running daily, with a budget of one alert a
   week, allows a per-check false-positive rate of about 0.7%.
4. Set each threshold to hit that rate on the baseline window, empirically. Do
   not assume a distribution - count how many baseline points would have fired.
5. Publish the expected rate with the check, and compare it to the observed rate
   after a month. A check firing ten times its predicted rate is miscalibrated,
   not vigilant.

A check that has never fired is not evidence of health either. Test that each
one can fail by feeding it input that should trip it, once, deliberately.

## 6. Many columns is a multiplicity problem

Running one check per column across a wide table is exactly the situation in
section 8 of `inference.md`, and the arithmetic is the same. Two hundred columns
each with a 1% false-positive rate produce two false alerts on every clean run,
so the dashboard is permanently red and nobody looks.

Options, in order of practicality:

- **Check fewer columns.** Cover the ones that carry decisions, not all of them.
  Coverage counted in columns is a vanity metric.
- **Aggregate to one signal per table** - a count of columns whose distribution
  moved - and alert on that, with the per-column detail available underneath.
- **Tighten per-column thresholds to fit the budget**, as in section 5, which
  is the same as correcting for the number of tests.
- **Two tiers.** A small blocking set with strict thresholds, and a large
  advisory set that is reviewed rather than alerted on.

## 7. Block, notify, or record

The response is a cost comparison, not a severity label. Compare the cost of
stopping the flow against the cost of letting bad data continue and be
corrected later.

**Block when** the check is a validity rule with no false positives; downstream
consumers cannot tell good from bad once it lands; the correction would be
expensive or visible outside the team; or the data feeds something irreversible.

**Notify when** the check is statistical and has a real false-positive rate; the
data is still useful while being investigated; or a person can judge within the
window that matters.

**Record only when** the signal is for trend analysis rather than action, or the
check is new and its firing rate is not yet trusted. Every new statistical check
starts here for at least one baseline period. Shipping a new check straight into
blocking is how a plausible threshold takes down a pipeline at 3am.

Two rules regardless of tier: a check whose empty result is indistinguishable
from a pass is not a check, and anything that blocks needs a documented
override path or it will be removed the first time it is wrong.

## 8. What a gate definition must state

A gate emitted from an analysis carries everything needed to run it and to
argue with it later:

- The dataset and column, and the aggregation - per row, per batch, per day.
- The statistic - median, null rate, row count, modified z against a baseline.
- The baseline window, its length, and which periods were excluded from it.
- The threshold, and the reasoning or citation behind it.
- The expected firing rate on the baseline, with the count of baseline points
  that would have fired.
- The action - block, notify, record - and who receives it.
- The date it was derived and when it should be re-derived.
- The degenerate-case behavior. What the check does when the column is constant,
  when the batch is empty, when the baseline is too short. Each of these must be
  a defined outcome rather than a division by zero or a silent pass.

## 9. How checks fail

The catalog, in rough order of frequency:

- **Threshold picked from tradition.** Three sigma on skewed data. Fires
  constantly, gets muted, stays in the codebase looking like coverage.
- **Baseline contains the incident.** The one event the check exists to catch is
  now part of normal.
- **Constant column.** A robust spread of zero flags every distinct value. See
  the degenerate case in `robust-and-outliers.md`.
- **Empty input reads as a pass.** No rows means no failures. Check that rows
  arrived before checking what is in them.
- **Comparison against the wrong period.** Monday against Sunday, month-end
  against a mid-month day.
- **The check tests the copy, not the source.** Passing on data that was already
  filtered by the same logic that would have caused the problem.
- **A rolling baseline absorbs a slow degradation.** Nothing ever fires, and the
  column has drifted 40% in a year.
- **Alerts to a channel nobody reads.** Mechanically a success, operationally
  identical to having no check.
