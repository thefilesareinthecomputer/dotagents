# Decision theory: criteria, information, policies

- [Three registers](#three-registers)
- [Decision vs policy](#decision-vs-policy)
- [Uncertainty classes and their legal criteria](#uncertainty-classes-and-their-legal-criteria)
- [Value of information](#value-of-information)
- [Satisficing and aspiration levels](#satisficing-and-aspiration-levels)
- [Runtime to design time](#runtime-to-design-time)
- [Sources](#sources)

## Three registers

Decision theory speaks in three registers, and confusing them causes most
arguments about rationality:

- **Normative** - how an ideal agent should decide (expected utility, the
  axioms, the criteria below).
- **Descriptive** - how humans actually decide (prospect theory, the biases; see
  `bets-and-behavior.md`).
- **Prescriptive** - how a real bounded human decides better, given the gap
  between the first two.

A decision session is a prescriptive instrument: normative theory sets the
standard, descriptive theory predicts the deviations, and the gap between them is
the working target.

## Decision vs policy

A **decision** is a single choice at a moment. A **policy** is a precomputed
function from states to actions: an if-then, a threshold, a standing rule, a
checklist, an environment arranged so the right move is the default. These are
one object in different substrates - language, space, software, habit.

Decision quality is highest when calm, informed, and unhurried. Decision urgency
is highest when none of those hold. The arbitrage: decide where quality is high,
execute where stakes are high. Precommitment goes one step further: it binds
the future self against predicted deviations.

Any decision made three times the same way is a design defect, not diligence:
convert it to a policy. A jammed deliberation over a recurring situation is a
cache miss; the fix is to install the cache entry, not to deliberate better.

## Uncertainty classes and their legal criteria

The class of uncertainty determines which decision criteria are legitimate. Most
stuck decisions are stuck because the criterion does not match what is actually
known.

**Risk (probabilities known or estimable).** Expected value and expected utility
reasoning are legitimate. Use base rates; beware small samples.

**Uncertainty (outcomes enumerable, probabilities unknown).** Expected value has
nothing to stand on; use robustness criteria (Wald, Savage, Hurwicz):

- **Maximin (Wald):** choose the act whose worst case is least bad. Correct when
  any downside is ruin - ruin must be floored, not priced. As a general
  worldview it is paranoia: nature rolls dice, it does not scheme.
- **Minimax regret (Savage):** for each act, compute the worst realistic gap
  between what you got and what the best alternative would have given; choose
  the act that bounds that gap. Naming the worst realistic regret usually
  shrinks it - imagined regret runs larger than computed regret.
- **Optimism weighting (Hurwicz):** an explicit blend of best and worst case.
  Its value is honesty: it forces the optimism parameter into the open instead
  of leaving it implicit in the framing.

**Ignorance (the states themselves cannot be enumerated).** Stop computing.
Criteria need a state space; without one, the rational moves are optionality
(positions that pay off across many futures), small reversible probes that make
the state space visible, and satisficing.

## Value of information

Information is worth exactly the improvement it makes to the decision, no more
(Raiffa-Schlaifer). Operational form, the anti-rumination theorem:

**"What finding would change your choice?"**

- No answer: the decision is already made; further research is avoidance.
- An answer: price it. Is obtaining the finding cheaper than the stakes it
  swings? A timeboxed spike, benchmark, or prototype is purchased information;
  size the timebox by what the finding is worth. When the price exceeds the
  swing, decide with what you have.

Research past the point where no finding would change the choice is not
diligence; it is deferral wearing diligence's clothes.

## Satisficing and aspiration levels

Optimization requires knowing all options and their values; bounded agents
rarely do (Simon). Satisficing: set an aspiration level - "good enough" - BEFORE
comparing options, then take the first option that clears it. Set the bar first,
or the comparison process itself will move it.

The tell that this is missing: the option set keeps growing while nothing ships.
Fast-and-frugal heuristics are not defective shortcuts; in many environments
simple rules beat complex models because they generalize (Gigerenzer). The
sophistication is in matching the rule to the environment, not in the rule's
complexity.

## Runtime to design time

The unifying prescription. Runtime - the moment of execution - is where stakes
are high, time is short, and the operator may be degraded. Design time - calm,
informed, unhurried - is where decision quality lives. Move every decision you
can from runtime to design time:

- Recurring choices become policies (if-then rules, thresholds, standing rules).
- Predictable temptations get precommitment devices set while calm.
- Predictable emergencies get pre-made decisions (runbooks, escalation rules,
  kill criteria) authored before the alarm.
- Environments get designed so the default path is the desired one.

What remains at runtime is the genuinely novel part, handled with full attention
because everything routine was already decided.

## Sources

- Simon, "A Behavioral Model of Rational Choice" (1955); "Rational Choice and
  the Structure of the Environment" (1956).
- Wald, "Statistical Decision Functions" (1950).
- Savage, "The Theory of Statistical Decision" (1951); "The Foundations of
  Statistics" (1954).
- Hurwicz, "Optimality Criteria for Decision Making under Ignorance" (1951).
- Raiffa and Schlaifer, "Applied Statistical Decision Theory" (1961).
- Gigerenzer, Todd, and the ABC Research Group, "Simple Heuristics That Make Us
  Smart" (1999).
