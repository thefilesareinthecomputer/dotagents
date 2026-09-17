# Probability, odds and betting arithmetic

An application of the core to wagers and repeated gambles. Everything here is a
calculation. **Nothing here is a recommendation to bet, or to bet an amount** -
the last section says why that boundary is real rather than a formality.

The recurring theme: the arithmetic is easy and almost never the binding
constraint. The probability estimate that goes into it is the whole game, and
the number of trials needed to tell a real edge from luck is far larger than
anyone expects.

## Contents

1. [Odds formats](#1-odds-formats)
2. [The margin in a price](#2-the-margin-in-a-price)
3. [Expected value and edge](#3-expected-value-and-edge)
4. [Where the probability comes from](#4-where-the-probability-comes-from)
5. [Variance hides an edge for a long time](#5-variance-hides-an-edge-for-a-long-time)
6. [Risk of ruin](#6-risk-of-ruin)
7. [Kelly as arithmetic](#7-kelly-as-arithmetic)
8. [Base rates and conditional probability](#8-base-rates-and-conditional-probability)
9. [Streaks](#9-streaks)
10. [Regression to the mean](#10-regression-to-the-mean)
11. [Combining bets](#11-combining-bets)
12. [Calculation, not advice](#12-calculation-not-advice)

## 1. Odds formats

| Format | Example | Implied probability | Returns on a 1 stake |
|---|---|---|---|
| Decimal | 2.10 | 1 / 2.10 = 0.476 | 2.10 total, 1.10 profit |
| Fractional | 11/10 | denominator / (numerator + denominator) = 0.476 | 1.10 profit |
| American positive | +110 | 100 / (110 + 100) = 0.476 | 1.10 profit |
| American negative | -110 | 110 / (110 + 100) = 0.524 | 0.909 profit |

Decimal is the format to compute in - expected value, edge and the Kelly
fraction are all cleaner in it. Convert on input and output, and state which
format a quoted price is in, since 110 means opposite things with and without
its sign.

## 2. The margin in a price

Implied probabilities across the outcomes of one event sum to more than 1. The
excess is the margin, also called the overround or the vig. Two outcomes priced
at 1.91 each imply 0.524 + 0.524 = 1.048, a 4.8% margin.

**The margin is the hurdle.** A bettor with no edge loses at approximately the
margin rate per bet. Any comparison of an estimated probability against a quoted
price must be against a margin-removed price, or the edge is overstated by
roughly the margin.

Removing it:

- **Proportional** - divide each implied probability by their sum. Simple, and
  it assumes the margin is spread evenly across outcomes.
- **Power or odds-ratio methods** - fit a single parameter so the adjusted
  probabilities sum to 1 while distributing the margin unevenly.

Empirically the margin is not spread evenly: longshots carry more of it than
favorites, so proportional removal tends to overstate longshot probabilities.
State which method was used, because the choice changes the edge on exactly the
prices where an edge is being claimed.

## 3. Expected value and edge

For a decimal price `d`, an estimated win probability `p`, and a stake `s`:

- Profit if it wins is `s * (d - 1)`; loss if it does not is `s`.
- Expected value is `s * (p * (d - 1) - (1 - p))`, which simplifies to
  `s * (p * d - 1)`.
- **Edge** is `p * d - 1`, the expected return per unit staked. Positive edge
  means the estimated probability exceeds the price's margin-removed implied
  probability.

A worked example: `d = 2.10`, `p = 0.52`. Edge is `0.52 * 2.10 - 1 = 0.092`, so
9.2% expected return per unit staked, and expected value on a stake of 100 is
9.2. That is the arithmetic in full, and it is entirely contingent on the 0.52.

## 4. Where the probability comes from

Every number in section 3 inherits the uncertainty of `p`, and this is where
the analysis actually lives.

- **Put an interval on `p`.** If `p` is estimated from 200 historical events,
  its standard error is around 0.035, so a 0.52 estimate is consistent with
  anything from 0.45 to 0.59. The edge computed from the lower end is
  substantially negative.
- **Propagate it.** Report the edge at the low, central and high ends of the
  interval on `p`. An edge that survives only at the point estimate is not an
  edge, it is a rounding artifact.
- **The market price is itself an estimate**, and usually an informed one. A
  claimed edge is a claim to know better than the aggregate of everyone pricing
  it, which is possible but is a strong claim that should be stated as one.
- **Beware fitting `p` on the same history used to evaluate the strategy.** That
  is the in-sample problem of `ml-evaluation.md`, and it produces a confident
  edge that vanishes on new events.
- **Count the markets searched.** Scanning a thousand prices for the biggest
  discrepancy is the multiplicity problem of `inference.md` section 8; the
  largest apparent edge across many markets is mostly estimation error, and it
  concentrates in exactly the markets where the estimate is worst.

## 5. Variance hides an edge for a long time

The number of trials needed to distinguish a real edge from zero is a power
calculation, and the answer is routinely in the thousands.

With per-bet return standard deviation `sigma` and edge `e`, the standard error
of the mean return after `n` bets is `sigma / sqrt(n)`. To have the observed
mean stand clear of zero, `n` must be on the order of `(sigma / e)^2` multiplied
by a factor for the confidence wanted - roughly 8 for a two-sided test at 95%
with reasonable power.

For an even-money bet with a 2% edge, `sigma` is close to 1, so distinguishing
that edge from zero takes on the order of 20,000 bets. Consequences worth
stating plainly:

- **A losing run of hundreds is entirely compatible with a real edge**, and a
  winning run of hundreds is entirely compatible with no edge at all.
- **A season, a month, or a few hundred bets is not a sample that can settle
  anything.** Report the interval on realized return and it will usually contain
  both zero and twice the claimed edge.
- **Track the estimate with its interval over time**, rather than the running
  total, which invites reading noise as a trend.

## 6. Risk of ruin

Ruin is reaching a bankroll level at which betting cannot continue. It depends
on the edge, the variance, and the stake as a fraction of bankroll - and the
third dominates.

- With a fixed fractional stake and a positive edge, the probability of ruin
  falls sharply as the fraction falls, and rises to certainty as the fraction
  approaches and exceeds the growth-optimal one.
- **Simulate rather than derive.** For any realistic case - varying prices,
  varying stakes, correlated outcomes - a seeded simulation of many bankroll
  paths gives the ruin probability, the distribution of drawdowns and the time
  to recovery directly. Report the seed and the number of paths.
- **Report drawdown, not only ruin.** A strategy that survives with a 70% peak
  loss has technically avoided ruin and would be abandoned by anyone living
  through it.

## 7. Kelly as arithmetic

The Kelly fraction maximizes the expected logarithm of bankroll, which
maximizes the long-run growth rate. For a bet at decimal odds `d` with win
probability `p`, writing `b = d - 1` and `q = 1 - p`:

```
f* = (b * p - q) / b     which is the same as     f* = edge / b
```

With `d = 2.10` and `p = 0.52`: `b = 1.10`, edge = 0.092, so `f* = 0.084`.

What the formula assumes, all of which matters more than the formula:

- **`p` is known exactly.** It is not. Kelly computed from an overestimated `p`
  overbets, and the growth penalty for overbetting is asymmetric and severe -
  betting twice the Kelly fraction gives a growth rate of zero, and more than
  twice is negative growth with a positive edge.
- **Repeated identical independent bets**, with the full bankroll available and
  divisible each time.
- **Log utility is the objective**, which implies tolerating drawdowns that most
  people will not. Full Kelly produces a 50% drawdown with high probability over
  a long sequence.

For those reasons practitioners use a fraction of Kelly - a half or a quarter -
which gives most of the growth with far less variance. The sources are Kelly,
"A New Interpretation of Information Rate" (*Bell System Technical Journal*,
1956) and Thorp's treatment of its application (2006).

Report `f*`, the fractional-Kelly values, and the sensitivity of `f*` to the
interval on `p`. That is the calculation. What fraction anyone should use is a
question about their circumstances and is section 12.

## 8. Base rates and conditional probability

The most common probability error outside of gambling, and it is inside it too.

Bayes' rule: the probability of the hypothesis given the evidence depends on the
base rate of the hypothesis, not only on how diagnostic the evidence is. The
standard illustration: a test with 99% sensitivity and 99% specificity applied
to a condition present in 1 in 10,000 gives, on a positive result, a probability
of about 1% that the condition is present - because false positives from the
enormous negative population swamp the true positives. Tversky and Kahneman
(*Science*, 1974) documented how reliably this is ignored.

Applications here:

- **A model that flags rare events** is mostly flagging false positives, no
  matter how accurate it sounds.
- **The prosecutor's fallacy** is the same error - the probability of the
  evidence given innocence is not the probability of innocence given the
  evidence.
- **An unlikely coincidence is likely somewhere.** The probability that some
  team, some player or some market shows a remarkable pattern this season is
  high even when the probability for any particular one is tiny. Ask how many
  opportunities there were for the coincidence to occur.

## 9. Streaks

Runs of consecutive successes occur in random sequences far more often than
intuition allows. Twenty coin flips contain a run of four or more about half the
time.

To assess whether a streak means anything:

1. **Fix the question before looking.** "Does this player shoot better after
   makes than after misses" is answerable. "Is this particular streak, which I
   noticed because it was long, meaningful" is not - the streak was selected for
   being extreme.
2. **Permute.** Shuffle the sequence of outcomes many times and compare the
   observed longest run, or the observed post-success rate, to the permutation
   distribution. Seeded, and reported with the number of shuffles.
3. **Correct for how many sequences were examined.** Scanning a league for the
   longest streak is a search over hundreds of players.

The hot hand is the worth-knowing case. Gilovich, Vallone and Tversky
(*Cognitive Psychology*, 1985) found no evidence for it and the finding held as
conventional wisdom for decades. Miller and Sanjurjo (*Econometrica*, 2018)
showed that the standard analysis carries a subtle selection bias: conditioning
on "after a make" in a finite sequence biases the estimated conditional rate
downward, so the original method understated any real effect. Both papers are
worth citing together, because the story is a good reminder that the analysis
method is itself a thing that can be wrong.

## 10. Regression to the mean

Anything selected for being extreme will, on the next measurement, be less
extreme, with no cause required. A team that overperformed, a fund in the top
decile, a sales region that spiked - all tend to move toward the average next
period, and the movement gets attributed to whatever was done in between.

The tell: any before-and-after comparison on units chosen for being extreme.
The defense: select the units before observing the outcome they will be judged
on, or compare against a control group selected the same way.

The size of the effect depends on how much of the original measurement was
noise. A measure with low reliability regresses almost all the way to the mean.

## 11. Combining bets

- **Independent outcomes multiply.** A combination of three independent legs at
  0.5 wins 12.5% of the time, and the margin compounds across the legs, which is
  why combination bets carry a much larger effective margin than their parts.
- **Correlated legs are the common case and the common error.** Outcomes within
  the same event are usually correlated, sometimes strongly, and the product
  rule is then simply wrong - in either direction. Estimating the correlation is
  harder than estimating either probability.
- **Multiple simultaneous positions do not diversify if they share a driver.**
  Ten bets on the same underlying condition is one bet at ten times the stake,
  and the risk-of-ruin simulation must use the joint outcomes rather than
  independent draws.

## 12. Calculation, not advice

Everything above computes: implied probability, margin, edge, expected value,
variance, ruin probability, the Kelly fraction and its fractional variants. All
of it is available on request, with intervals and sensitivity to the inputs.

None of it is a recommendation to place a bet or to stake an amount. "Your
estimated edge is 9.2% and the full Kelly fraction is 0.084, falling to 0.02 at
the low end of the interval on `p`" is a calculation. "Stake 8%" is advice, and
it requires knowing the bankroll, what the money is otherwise for, the tolerance
for a long losing run, and how much to trust the probability estimate - none of
which is in the data. When the question asks for the second, produce the first
and name what else the decision would require.
