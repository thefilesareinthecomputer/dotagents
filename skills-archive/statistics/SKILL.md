---
name: statistics
description: Statistical analysis that states its n, its interval, and the assumption that would overturn its conclusion, using the Python standard library alone. Use when the question is whether a difference is real, how large a sample must be, whether a streak means anything, what a correlation actually supports, or whether an outlier is genuinely anomalous; when an analysis needs auditing for a p-value without an effect size, an in-sample result, or a best-of-many comparison reported as if one was tried; and for value at risk on returns, whether a model improvement is real and calibrated, whether a bet is positive expected value, and what threshold a recurring data check should fire at. Not for pipelines or warehouses (data-engineering), model building (machine-learning), or charts (dataviz).
---

# statistics

Statistical work that is correct, not merely computed, in whatever context the
question arrives from. It answers a plain question cold - a spreadsheet someone
sent, a run of wins, two variants that scored differently - and it is also the
inference layer wherever "is this number real" gets asked.

**It is organized around the errors, not around a menu of tests.** Computing a
mean wrong is rare. A confident conclusion the analysis never earned is common:
a p-value read as an effect size, a model scored on the data it was fit on, a
backtest that quietly knew the future, a correlation reported as a cause. Every
reference file here exists because one of those is easy to commit and hard to
notice afterward.

Floor is Python 3.10+ standard library, so nothing needs installing. `numpy`,
`scipy.stats` and `pandas` are used when present and never required; their
absence changes speed and the size of the test menu, not an answer.

## The method

Four things travel with every result. An analysis missing any of them is not
finished, and the auditor exists to say which one is missing.

1. **State `n`.** Every statistic reports the number of observations behind it,
   after exclusions. Rows dropped for being missing or non-numeric are counted
   and reported, never dropped quietly, because the drop rule is frequently
   correlated with the thing being measured.
2. **Quantify uncertainty with an interval.** A point estimate with no interval
   is a number, not a finding. Report the interval beside the estimate and give
   its coverage level; report an effect size beside any p-value.
3. **Name the assumption that would overturn the conclusion.** Independence,
   stationarity, a representative sample, an untouched holdout, a fixed
   hypothesis. Say which one the conclusion is resting on and what would falsify
   it. This is the sentence that turns a number into a claim someone can check.
4. **Record the seed.** Anything randomized prints the seed it used. An
   interval nobody can reproduce is not a result.

**Resampling is the default path.** Bootstrap intervals and permutation tests
need no distributional assumption, are correct on the skewed and fat-tailed data
that real columns contain, and run on the standard library. Parametric tests are
used where they earn it - small samples, a known design, a need for power - and
always alongside the assumption they require. When a parametric test is chosen,
say why it was chosen over resampling.

**Search is the thing that fools everyone.** If several cutoffs, models,
segments or strategies were tried, the reported winner is the maximum of a
sample of noise. Report how many were tried and correct for it, or the number
means nothing. See `references/inference.md` on multiplicity.

## Route by situation

| The situation | Go to |
|---|---|
| Deciding which method the question calls for, and what disqualifies each | `references/choosing-a-method.md` |
| Intervals, tests, effect sizes, power and sample size, multiplicity | `references/inference.md` |
| Outliers, MAD and modified z, trimmed and winsorized statistics, threshold selection, degenerate columns | `references/robust-and-outliers.md` |
| A recurring automated check on a column - baseline windows, drift versus anomaly, alert budgets, what to block on | `references/data-quality.md` |
| Fitting a line or a surface, reading the diagnostics, knowing when the fit lies | `references/regression.md` |
| Auditing an analysis, yours or someone else's, for named defects | `references/pitfalls.md` |
| Splits, cross-validation, leakage, class imbalance, calibration, metric choice, baselines | `references/ml-evaluation.md` |
| Returns, volatility, drawdown, value at risk, stationarity, autocorrelation, why a backtest flatters itself | `references/market-and-forecasting.md` |
| Odds, expected value, edge, variance and ruin, the Kelly fraction, base rates, streaks | `references/probability-and-betting.md` |

### When the sibling skills are present

Routing lives here and only here. No reference file in this skill names another
skill, which is what keeps the core usable by a reader who has none of them.

| That skill owns | This skill owns | Route |
|---|---|---|
| Platform, ingestion, transformation, cost, deployment, and where a quality check runs and what it blocks | **How the threshold is chosen**, and whether a flagged row is genuinely anomalous | `data-engineering` |
| Grain, conformed dimensions, slowly changing dimensions, the bus matrix | Whether two sources' measures actually agree, and by how much | `dimensional-data-modeling` |
| Which agent or model stack to build on | Whether a measured difference between two options is real | `ai-engineering` |
| Framing, features, training, tuning, serving, drift response | Evaluation as inference - is the improvement real, what is the interval on the metric, is the model calibrated | `machine-learning` |
| Charts, plots, and how a result is drawn | The number the chart is drawing | `dataviz` |

The threshold handoff is the sharpest one and the reason this is a separate
skill. Deciding that a pipeline needs a completeness check is a platform
decision. Deciding that the check fires at 3.5 modified z against a 28-day
baseline is a statistics decision, and it is where these checks usually fail: a
three-sigma gate on skewed data fires constantly and gets muted within a week.

**Leakage is the one shared boundary.** This skill defines leakage and detects
it in a *result* - a metric that could only have been achieved by knowing
something the model would not know in production. Preventing it structurally in
*code* belongs to `machine-learning`. Until that skill ships, this one answers
the evaluation half and says plainly that it does not cover the building half:
it will tell you the reported improvement is not real, not how to build a better
model.

**Dataframe tooling is not this skill's.** pandas, Polars, PySpark, DuckDB and
SQL belong to `data-engineering`. CSV is read here through the standard library
precisely so that nothing has to be installed first.

## Commands

`scripts/stats.py` is the calculator. **EXECUTE it; do not read it as
documentation.** Every subcommand takes `--json`; every randomized subcommand
takes `--seed` and records the seed in its output.

```bash
python3 scripts/stats.py describe   data.csv --col price
python3 scripts/stats.py test       data.csv --col a --by group --method auto
python3 scripts/stats.py boot       data.csv --col a --stat median --reps 10000 --seed 7
python3 scripts/stats.py robust     data.csv --col amount            # MAD, modified z, trimmed mean
python3 scripts/stats.py outliers   data.csv --col amount --method mad --threshold 3.5
python3 scripts/stats.py outliers   data.csv --col amount --baseline ref_window.csv --emit-gate
python3 scripts/stats.py regress    data.csv --y price --x sqft,beds --diagnostics
python3 scripts/stats.py evaluate   preds.csv --truth y --score p --task binary
python3 scripts/stats.py risk       returns.csv --col ret --var 0.95 --horizon 10
python3 scripts/stats.py power      --effect 0.3 --alpha 0.05 --power 0.8
python3 scripts/stats.py ev         --odds 2.10 --p 0.52 --stake 100   # edge, EV, variance, ruin
python3 scripts/stats.py series     prices.csv --col close --acf 20 --stationarity
```

Each command prints which backend it used, because a result computed through
`scipy` and one computed through the standard library should be distinguishable
in a transcript.

`scripts/stats_check.py` is the auditor. **EXECUTE it too.** It reads an
analysis described as JSON and reports named defects.

```bash
python3 scripts/stats_check.py analysis.json
python3 scripts/stats_check.py analysis.json --json --warnings-as-errors
```

Tests:

```bash
python3 -m unittest discover -s tests
```

**What the auditor cannot see.** It reads the description of an analysis, not
the data and not the code that produced it. It cannot tell you the sample was
biased, the column meant something other than its name, or the holdout was
contaminated upstream of the file it was handed. A clean run means no listed
defect was visible in what it was given. Silence is not approval.

Read `references/pitfalls.md` for what each finding means and how to fix it. The
same catalog works by hand on an analysis that has no manifest - it is a
checklist before it is a script.

## Boundaries

**Always**

- Report `n` with every statistic.
- Report an effect size and an interval beside any p-value.
- Name the assumption whose violation would overturn the conclusion.
- Prefer resampling; state when a parametric test was chosen and why.
- Record and print the seed for anything randomized.
- Say "associated with", not "causes", for observational data.

**Ask first**

- Adding any third-party dependency, including making an optional one required.
- Changing a default - alpha, bootstrap reps, value-at-risk confidence.
- Anything that writes to or modifies the user's source data files.

**Never**

- Recommend a trade, a stake, a position size, or an allocation.
- Present an in-sample fit or a backtest as expected future performance.
- Report the best of several strategies, models or cutoffs without saying how
  many were tried and correcting for it. Searching hard enough guarantees a
  winner, and this is the single most common way prediction work fools itself.
- Report a p-value alone, or describe a result as "significant" without the
  effect size beside it.
- Drop missing or non-numeric rows silently. Count them, report them, then act.
- Evaluate a model on data it was fit on and present the number as performance.
- Fabricate a citation for a method or a threshold.

### Calculation, not advice

This skill computes and describes. Expected value, edge, variance, risk of ruin,
value at risk and the Kelly fraction are arithmetic, and it will do all of them.
It does not recommend a trade, a stake, a position size or an allocation, and it
says so when a question drifts that way.

The distinction is real rather than a disclaimer. "Your edge is 4% and the full
Kelly fraction is 0.08" is a calculation. "Bet 8%" is advice, and it requires
knowing the person's bankroll, their tolerance for a 50% drawdown, their tax
position and whether the 4% edge estimate is itself trustworthy - none of which
is a statistics question. When a request is for the second thing, compute the
first and name what is missing.

## Files

| File | Covers |
|---|---|
| `references/choosing-a-method.md` | question shape to method, the disqualifiers, what to do when nothing fits |
| `references/inference.md` | intervals, bootstrap and permutation, parametric tests and their assumptions, effect sizes, power and sample size, multiplicity |
| `references/robust-and-outliers.md` | MAD and modified z, trimmed and winsorized statistics, threshold selection by firing rate, degenerate columns |
| `references/data-quality.md` | baseline windows, drift versus anomaly, alert budgets, what a check should block on |
| `references/regression.md` | ordinary least squares assumptions, diagnostics, collinearity, extrapolation, when the fit lies |
| `references/pitfalls.md` | the audit catalog - one entry per detectable defect, each with its detection rule |
| `references/ml-evaluation.md` | splits, cross-validation, leakage, imbalance, calibration, metric choice, baselines |
| `references/market-and-forecasting.md` | returns and volatility, drawdown, value at risk and conditional value at risk, stationarity, autocorrelation, backtest honesty |
| `references/probability-and-betting.md` | odds formats, expected value and edge, variance and ruin, Kelly as arithmetic, base rates, streaks |
| `scripts/stats.py` | the calculator (execute) |
| `scripts/stats_check.py` | the auditor (execute) |

The first six are the core. They carry the general method, name no other skill,
and read correctly to someone with no context from this repo. The last three are
applications - each maps one field's questions onto the core, and each is
skippable.
