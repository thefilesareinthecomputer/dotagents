# Market data and forecasting

An application of the core to price and return series. Two things make this
domain different: the data violates the independence and stability assumptions
that most methods need, and the incentive to search until something works is
enormous. Most of what follows addresses the second.

**Everything here is a computation. Nothing here recommends a trade, a position
size or an allocation** - see the closing section for why that line is real
rather than a disclaimer.

## Contents

1. [Work in returns](#1-work-in-returns)
2. [What return data actually looks like](#2-what-return-data-actually-looks-like)
3. [Volatility](#3-volatility)
4. [Drawdown](#4-drawdown)
5. [Value at risk](#5-value-at-risk)
6. [Expected shortfall](#6-expected-shortfall)
7. [Stationarity and autocorrelation](#7-stationarity-and-autocorrelation)
8. [Why a backtest flatters itself](#8-why-a-backtest-flatters-itself)
9. [The Sharpe ratio needs an interval](#9-the-sharpe-ratio-needs-an-interval)
10. [Running one honestly](#10-running-one-honestly)
11. [Calculation, not advice](#11-calculation-not-advice)

## 1. Work in returns

A price series is non-stationary by construction - its mean wanders and its
variance grows with the level - so every summary computed on prices describes
the period rather than the process. Convert first.

- **Simple return** is the proportional change. It aggregates correctly across
  positions at a point in time.
- **Log return** is the log of the price ratio. It aggregates correctly across
  time, since log returns add. Use logs for time aggregation and simple returns
  for cross-sectional aggregation, and say which is in use, because the two
  diverge visibly once moves get large.
- **Adjust for splits, dividends and corporate actions** before computing
  anything. An unadjusted series contains discontinuities that no statistical
  method will interpret as anything but volatility.
- **State the frequency.** Daily, hourly and monthly returns have different
  distributions, and a result computed on one does not carry to another.

## 2. What return data actually looks like

Four properties, all of which break a normal-distribution assumption, documented
since Mandelbrot (*Journal of Business*, 1963):

- **Fat tails.** Large moves are far more frequent than a normal distribution
  implies. A "six-sigma" day under a normal assumption should be essentially
  impossible and happens repeatedly in every long series. This is why parametric
  risk numbers understate risk, and why the resampling default matters here more
  than anywhere else.
- **Volatility clustering.** Large moves follow large moves. Returns themselves
  have near-zero autocorrelation while their absolute or squared values are
  strongly autocorrelated. Any method assuming constant variance is wrong on
  this data.
- **Skew.** Losses and gains are not symmetric, and treating them as symmetric
  misprices the tail that matters.
- **Regime change.** The distribution is not the same across decades, or across
  a crisis boundary. A single estimate over a long window describes no period in
  particular.

The practical consequence: use empirical quantiles and resampling rather than
closed-form normal formulas, and state the window every estimate came from.

## 3. Volatility

- **Realized volatility** is the standard deviation of returns over a window.
  Report the window with it; the number is meaningless without one.
- **Annualization multiplies by the square root of the number of periods** -
  about 252 for daily data. That scaling assumes independent returns with
  constant variance, which section 2 says is false. It is a convention for
  comparability, not an estimate, and it should be labeled as one.
- **The estimate is noisy.** Volatility estimated from 20 observations has a
  wide interval. Bootstrap it and report the interval rather than four decimal
  places.
- **Exponentially weighted estimates** respond faster to a regime change than an
  equally weighted window. The decay parameter is a choice about how much
  history counts, and it should be stated.
- **Volatility is more forecastable than returns.** This is the one genuinely
  encouraging fact in the file, and it is why risk work is on firmer ground than
  direction prediction.

## 4. Drawdown

Maximum drawdown is the largest peak-to-trough decline over a period. It is the
number that describes what holding the position felt like, and it is badly
behaved statistically.

- **It is a sample maximum**, so it can only grow with the length of the window
  and it has an enormous sampling error. Comparing the maximum drawdown of a
  three-year record to a ten-year one compares two different questions.
- **It is path dependent.** The same set of returns in a different order produces
  a different maximum drawdown, which is why a bootstrap over returns
  understates it if the dependence in section 2 is real. Resample blocks, not
  individual returns.
- **Report the distribution, not just the maximum** - the drawdown at several
  quantiles, the time spent below the previous peak, and the recovery time.
  Duration is often what actually matters.

## 5. Value at risk

Value at risk at confidence c over horizon h is the loss threshold that is
exceeded with probability 1-c over that horizon. **It is a quantile, not a worst
case, and it says nothing at all about how bad the exceedances are.** State the
confidence level, the horizon and the estimation window every time; a value at
risk figure without all three is not interpretable.

| Method | How | Weakness |
|---|---|---|
| Historical | The empirical quantile of past returns over the window | Only as good as the window; a quiet window produces a small number right up until it does not |
| Parametric | Mean and standard deviation with a normal quantile | Understates the tail, exactly where the number is supposed to be useful. Fat tails are not an edge case here |
| Monte Carlo | Simulate from a fitted model | Inherits every assumption of the fitted model; state which one it is |
| Filtered historical | Standardize returns by current volatility, resample, rescale | Handles volatility clustering; the default worth reaching for |

**Horizon scaling by the square root of h** assumes independent returns and
constant volatility, both false. It is acceptable for short horizons and
worsens as h grows; say when it has been used.

**Backtest the value at risk number itself.** Count the days the loss exceeded
it. At 95% over 250 days, expect about 12 exceptions; observing 30 means the
model is wrong, and observing 1 means it is uselessly conservative. Kupiec's
proportion-of-failures test (*Journal of Derivatives*, 1995) is the standard
check on that count, and clustering of exceptions matters as much as their
number.

## 6. Expected shortfall

Also called conditional value at risk - the average loss given that the value at
risk threshold was breached. It answers "how bad is it when it goes wrong",
which is the question value at risk cannot.

It is also subadditive - the risk of a combination never exceeds the sum of the
parts - which value at risk is not. Artzner, Delbaen, Eber and Heath, "Coherent
Measures of Risk" (*Mathematical Finance*, 1999) is the source, and the
practical consequence is that value at risk can penalize diversification while
expected shortfall cannot.

Cost: it is estimated from the few observations beyond the threshold, so it is
noisier than value at risk from the same data. Report the count of observations
in the tail alongside it, and an interval.

## 7. Stationarity and autocorrelation

- **Stationarity** means the distribution is stable over the window. Prices are
  not stationary; returns are closer to it, within a regime.
- **Unit-root tests** (Dickey and Fuller, 1979, and its augmented form) have low
  power against a slowly mean-reverting alternative, so failing to reject is
  weak evidence for anything. Use the test alongside a look at the series, not
  instead of one.
- **Autocorrelation of returns** near zero at all lags is the normal result and
  is why simple momentum rules on raw prices rarely survive costs.
  Autocorrelation of squared or absolute returns is strongly positive, which is
  volatility clustering.
- **Ljung-Box** (1978) tests a set of lags jointly rather than one at a time,
  which avoids the multiplicity of scanning an autocorrelation plot for the
  largest bar.
- **Spurious regression.** Two independent non-stationary series regress on each
  other with a high R-squared and a small p-value, routinely. Any regression on
  levels rather than changes is suspect until shown otherwise.

## 8. Why a backtest flatters itself

The catalog. Each of these has produced a strategy that looked excellent and
lost money.

- **Look-ahead.** Using a value that was not published yet - a revised figure, a
  close used for a decision made before the close, a corporate action applied on
  the announcement date rather than the effective one.
- **Survivorship.** A universe assembled from instruments that still exist today
  has removed the failures. This inflates returns and hides the tail.
- **Costs and slippage.** Spread, commission, market impact, borrowing, and
  taxes. A high-turnover strategy with a small edge is entirely a cost question,
  and omitting costs is the most common single reason a backtest is meaningless.
- **Overfitting the parameter grid.** Testing hundreds of parameter combinations
  and reporting the best is the multiplicity problem of `inference.md` section 8
  with the search hidden. The best of many noisy backtests always looks good.
- **Regime dependence.** A period that contained one long trend rewards trend
  following, and the result says more about the period than the strategy.
- **In-sample parameter fitting.** Parameters chosen over the whole history and
  then reported on that same history.
- **Selection of the reported result.** The strategies that failed are not in
  the writeup, and their count is what the reported one should have been
  corrected against.

Two things to demand of any backtest: the number of variants tried, and an
out-of-period result on data that took no part in any decision. Bailey and
Lopez de Prado's deflated Sharpe ratio (*Journal of Portfolio Management*, 2014)
gives the explicit adjustment for the number of trials, and their broader point
is that a backtest reported without a trial count is not evidence.

## 9. The Sharpe ratio needs an interval

The Sharpe ratio is the mean excess return over its standard deviation, usually
annualized. Three limits worth stating with any figure:

- **It is an estimate with substantial sampling error.** Its standard error
  depends on n; three years of monthly data gives a wide interval, and two
  strategies whose intervals overlap heavily have not been distinguished.
- **Annualization by the square root of the frequency assumes independence.**
  Lo (*Financial Analysts Journal*, 2002) gives the correction when returns are
  autocorrelated, and the uncorrected number is biased upward for a smoothed
  series.
- **It treats upside and downside deviation identically** and rewards a strategy
  whose returns are smooth until they are not - the profile of a strategy
  selling tail risk. Report the drawdown profile and the skew beside it.

## 10. Running one honestly

1. Adjust the price data, convert to returns, state the frequency and window.
2. Describe before modeling - n, the tails, the volatility profile, the regime
   boundaries visible in the window.
3. Decide the evaluation period before looking at it, and split by time.
4. Fix the parameters, or count every combination tried and report the count.
5. Include costs. State them explicitly rather than assuming they are small.
6. Compute the risk numbers with the confidence level, horizon and window
   attached; use empirical or filtered historical quantiles rather than normal
   ones.
7. Interval on everything, by block bootstrap so the dependence survives the
   resampling.
8. Backtest the risk model itself against its exception count.
9. State the assumption that would overturn the conclusion. It is almost always
   that the future window resembles the estimation window, and it is almost
   always the weakest part of the analysis.

## 11. Calculation, not advice

Everything above is arithmetic on data, and all of it is available on request:
expected value, edge, volatility, drawdown, value at risk, expected shortfall,
the Kelly fraction. None of it is a recommendation to trade, to size a position,
or to allocate.

The distinction is not a formality. "The historical 95% one-day value at risk on
this series is 2.3%, estimated over 2019 to 2024" is a measurement. "Reduce the
position" is advice, and it depends on the holder's other exposures, horizon,
liquidity needs, tax position and tolerance for loss - none of which is in the
data, and all of which change the answer. When a question asks for the second,
produce the first and name what else the decision would require.
