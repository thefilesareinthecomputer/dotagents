# Regression

Fitting a line or a surface, reading the diagnostics, and knowing the several
ways a good-looking fit can be wrong. Ordinary least squares is easy to run and
easy to over-read, and most of the damage comes from the second.

## Contents

1. [What it answers, and what it does not](#1-what-it-answers-and-what-it-does-not)
2. [The order to do it in](#2-the-order-to-do-it-in)
3. [The assumptions and their symptoms](#3-the-assumptions-and-their-symptoms)
4. [Diagnostics worth running every time](#4-diagnostics-worth-running-every-time)
5. [Reading a coefficient](#5-reading-a-coefficient)
6. [R-squared](#6-r-squared)
7. [Collinearity](#7-collinearity)
8. [Extrapolation](#8-extrapolation)
9. [Choosing variables is a search](#9-choosing-variables-is-a-search)
10. [The ways a fit lies](#10-the-ways-a-fit-lies)
11. [When least squares is the wrong model](#11-when-least-squares-is-the-wrong-model)
12. [Reporting](#12-reporting)

## 1. What it answers, and what it does not

Regression estimates how the average of an outcome differs across values of the
predictors, in the data it was given. That sentence contains all three limits:
it is an average, it is a difference rather than an effect of intervening, and
it holds over the range that was observed.

It does answer: how much does the outcome differ, per unit of this predictor,
among observations that match on the others; what is the interval on that; how
much of the variation is accounted for; what does the model predict here.

It does not answer: what would happen if the predictor were changed. That is a
causal question, and it needs a design - randomization, or an argument about
what else could explain the association - not a better fit.

## 2. The order to do it in

1. **Plot the outcome against each predictor** before fitting anything. Anscombe
   (1973) put four datasets with identical regression output and completely
   different shapes into one figure precisely to make this unskippable.
2. **State what the model is for** - description, prediction, or a causal claim.
   Prediction is judged out of sample, description is judged on the interval,
   and a causal claim needs a design.
3. Fit, with all rows accounted for. Count the rows dropped for missing values
   and report the count.
4. Run the diagnostics in section 4 before reading any coefficient.
5. Read coefficients with intervals, on their natural scale.
6. State the assumption whose failure would change the conclusion.

## 3. The assumptions and their symptoms

| Assumption | What breaks it | Symptom | Consequence |
|---|---|---|---|
| The relationship is linear in the parameters | A curved or saturating relationship | Curvature in residuals against fitted values | Coefficients describe a line through a curve; predictions are biased in a pattern |
| Errors are independent | Time order, repeated measures, clustering | Residuals correlated with their neighbors in sequence | Intervals far too narrow; a p-value that means nothing |
| Constant error variance | Spread grows with level, common for amounts and counts | Residual fan against fitted values | Coefficients are still unbiased, intervals are wrong |
| Predictors measured without error | Proxies, self-reports, coarse rounding | Not directly visible | Coefficients biased toward zero; other coefficients pick up the difference |
| No perfect collinearity, and not too much | Duplicated or near-duplicated predictors | Enormous standard errors, unstable signs | Coefficients uninterpretable individually while the fit stays fine |
| Residuals approximately normal | Heavy tails | A long-tailed residual distribution | Only affects small-sample intervals; least important of the six and the one most fussed over |

Independence and non-constant variance are the two that most often invalidate a
conclusion. Normality of residuals is the one that gets checked most and matters
least.

## 4. Diagnostics worth running every time

- **Residuals against fitted values.** The single most informative plot.
  Structure means the model is missing something - curvature, an interaction, a
  group difference.
- **Residuals against each predictor**, and against row order or time when one
  exists.
- **Leverage.** How unusual a point's predictor values are. High leverage plus a
  large residual is a point that is single-handedly setting the slope.
- **Cook's distance** (Cook 1977) combines the two into one influence measure.
  Refit without the top few points and see whether the conclusion holds; if it
  does not, that is a finding, not a nuisance.
- **Variance inflation factors** for collinearity - section 7.
- **The fit without the outliers, alongside the fit with them.** Report both
  whenever they disagree.

Heteroskedasticity has two standard responses: robust standard errors of the
Huber-White type (White 1980), or a bootstrap over rows, which does the same job
with no formula and is the default here.

## 5. Reading a coefficient

A coefficient is the difference in the average outcome per unit of that
predictor, among observations that match on the others in the model. Three
things follow:

- **"Holding others constant" only covers what is in the model.** Anything
  omitted and correlated with the predictor is inside the coefficient. See
  section 10.
- **Units decide readability.** "Each additional unit of area adds 143" is
  useless without knowing the units of both. Report the coefficient with units
  and, where the scale is awkward, per a meaningful increment.
- **A categorical predictor's coefficients are differences from a baseline
  category.** Say which category that is, or every number is unreadable.

Interactions and nonlinear terms change the reading entirely. With an
interaction, no single coefficient describes the predictor's relationship - it
depends on the other variable, so report the difference at concrete values. With
a squared term or a log, the coefficient is not a constant per-unit difference,
so state the interpretation explicitly or give predicted values at several
points instead.

Statistical significance of a coefficient is a weak fact. The interval is the
result; a predictor can be significant and negligible with enough data, or
substantively large and imprecisely estimated with a little.

## 6. R-squared

The share of outcome variance accounted for by the model, in the data it was fit
on. Three habitual misreadings:

- **It is not accuracy, and it is not a measure of correctness.** A model can
  have a high R-squared and predict badly out of sample; a model with a low one
  can still capture a real and useful relationship.
- **It only rises when predictors are added.** Adjusted R-squared penalizes
  that, mildly. Neither is a model-selection criterion worth trusting on its
  own, and neither says anything about out-of-sample behavior.
- **What counts as high is entirely domain-dependent.** Across noisy individual
  behavior 0.1 can be substantive; on an engineered physical relationship 0.95
  can indicate a mistake, usually a predictor that is a transformation of the
  outcome.

For prediction, report an out-of-sample error measure on the outcome's own
scale, with an interval. See `ml-evaluation.md`.

## 7. Collinearity

When predictors carry overlapping information, the fit stays stable and the
individual coefficients do not. The symptoms are a coefficient with an
implausible sign, an enormous standard error, and estimates that move sharply
when a variable is added or a few rows are dropped.

- **Variance inflation factors** quantify it. The conventional flag is above 10,
  with above 5 worth a look; both are conventions, not thresholds with a
  derivation behind them.
- **Prediction is not harmed** by collinearity. Interpretation of individual
  coefficients is.
- **Fixes, in order:** drop one of the pair when they measure the same thing;
  combine them into one measure; center the components of an interaction term,
  which removes the artificial collinearity an interaction introduces; or keep
  them and stop interpreting them separately, saying so.

## 8. Extrapolation

The fit describes the range of predictor values that were observed. Outside it,
the model is an assumption in the shape of a line.

State the observed range of every predictor with the model. For predictions,
check whether the requested point sits inside that range - and note that with
several predictors a point can be inside each variable's individual range while
being a combination never observed, which is exactly the leverage question from
section 4 pointed at new data.

## 9. Choosing variables is a search

Fitting many specifications and reporting the best one is the multiplicity
problem of `inference.md` section 8, wearing different clothes. Stepwise
selection, all-subsets search, and the informal version - trying predictors
until the result looks right - all invalidate the reported intervals and
p-values, because those assume the model was fixed in advance.

What to do instead: choose the specification from subject knowledge and fix it
before fitting; if a search is genuinely needed, say how many specifications
were fitted, and validate the winner on data not used in the search. Report the
search either way. A model presented as if it were the only one tried, when it
was the best of thirty, is the most common quiet dishonesty in applied
regression.

Related and separate: **regression to the mean.** Selecting units because they
were extreme on one measurement guarantees they will look less extreme on the
next, with no intervention involved. Any before-and-after comparison on a group
selected for being extreme has this effect built in, and it is routinely
reported as improvement.

## 10. The ways a fit lies

- **Omitted variable.** A variable outside the model that drives both the
  predictor and the outcome puts its whole association into the coefficient.
  This is the standard reason an observational coefficient is not an effect, and
  it can flip a sign, not merely inflate a number.
- **Simpson's paradox** (Simpson 1951). The relationship within every subgroup
  runs opposite to the relationship in the pooled data, because group membership
  is correlated with both. Look at the relationship within groups before
  believing a pooled one.
- **Reverse causation.** The outcome plausibly drives the predictor. Nothing in
  the fit distinguishes the directions.
- **Selection on the outcome.** If inclusion in the data depends on the outcome,
  the observed relationship is an artifact of the sample. This one is invisible
  in every diagnostic, because the missing rows are missing.
- **Measurement error in a predictor** biases its coefficient toward zero and
  transfers some of its explanatory work to whatever it correlates with.
- **A predictor computed from the outcome.** A near-perfect fit with a
  coefficient close to 1 usually means a variable was derived from the outcome,
  or is a rescaled copy of it.

The habit that catches most of these: before believing a coefficient, name the
variable that could produce it without the relationship being real, then check
whether it is in the data.

## 11. When least squares is the wrong model

| Outcome | Use | Why not least squares |
|---|---|---|
| Binary | Logistic regression | Predictions leave [0, 1]; variance is not constant by construction |
| Count, especially with many zeros | Poisson or negative binomial | Variance grows with the mean; predictions go negative |
| Strongly right-skewed positive amount | Least squares on the log, reported as a multiplicative effect | The fit chases the tail; note that back-transforming gives a median, not a mean |
| Bounded proportion | A model on the log-odds | Same boundary problem as binary |
| Heavy-tailed with real extremes | Robust regression, or quantile regression | Squared loss gives an extreme point unlimited influence |
| The question is about the tail, not the average | Quantile regression | The conditional mean is not what was asked about |
| Time-ordered | A method that models the dependence | Independence is violated; intervals will be far too narrow |

## 12. Reporting

State the specification, n after exclusions and the number excluded, each
coefficient with its interval and units, the fit measure, which diagnostics were
run and what they showed, the observed range of each predictor, how many
specifications were tried, and the assumption whose failure would overturn the
conclusion. Use "associated with" throughout unless the design supports more.
