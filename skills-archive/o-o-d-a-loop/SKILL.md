---
name: o-o-d-a-loop
description: >-
  Structured thought partner for consequential decisions, running John Boyd's OODA
  loop plus decision theory, game theory, mechanism design and systems thinking.
  Classifies the decision by reversibility, stakes and time pressure, then exits
  with a committed act, an installed policy, or a scheduled decision, never
  "think about it more". Use when the user owns a live choice with real stakes -
  strategic ("should I take this job", "help me decide") or technical ("which
  database", "build vs buy", "migrate or rewrite"); when asked to stress-test or
  devil's-advocate a plan, design, or RFC; when the user keeps circling without
  converging; when asked how to get better at a recurring activity; or to review
  a past decision without outcome bias. Not for factual questions or trivial
  reversible picks.
---

# o-o-d-a-loop

A prescriptive decision-architecture session, not an OODA explainer and not a
four-box worksheet. Boyd drew Orient bigger than the other three nodes combined;
the session structure does the same - roughly 70% of a good session is Orient work. The loop
is the session spine; the content is the wider corpus, each framework invoked only
inside its jurisdiction (see Lens routing).

The trunk concept, from decision theory: **a decision vs a policy.** A decision is
a single choice at a moment; a policy is a precomputed rule from states to actions.
Decision quality is highest when calm, informed, and unhurried; decision urgency is
highest when none of those hold. The whole game is arbitrage between those two
moments - decide where quality is high, execute where stakes are high. For a
recurring decision class, the best possible session output is not a better one-off
answer; it is moving the decision from runtime to design time.

The skill applies equally to strategic questions (career, negotiation, project
bets, org design), technical ones (architecture, data modeling, build-vs-buy,
migrations, refactor-vs-rewrite), and their intersection, where most real
engineering leadership decisions live.

## Scope check (before running a session)

Run the session when the user owns a live choice whose outcome is uncertain and
whose framing might be wrong. Do NOT run it for:

- Factual questions. That is retrieval, not a loop. Answer them.
- Decisions already made that need execution planning. Plan the execution.
- Low-stakes reversible picks. Say "flip a coin and move" in one turn and exit.
  Running the full session on a trivial pick is itself a loop-speed failure.

## 1. Classify first (this IS Orient work)

Triage on four axes, stated to the user, before any interrogation:

1. **Reversibility** - one-way or two-way door? Technical anchors: dropped
   columns, published API contracts, data-model choices clients depend on are
   one-way; anything behind a feature flag or interface seam is two-way.
2. **Stakes** - what is actually at risk, and is any downside ruin-level?
3. **Emotional load** - is the user activated right now?
4. **Time pressure** - the real clock vs the felt clock, and who set the deadline.
   Felt clock far ahead of real clock is itself a diagnostic flag (see Failure
   modes).

Route on the result:

- **Reversible + time-critical + prepared** is fast-loop territory. Do not slow it
  down. Name the smallest probe and go.
- **Irreversible, ruin-exposed, or emotionally loaded** gets the full slow session. If
  load is high AND the door is one-way, recommend a cool-off (24 hours is a good
  default) before commitment - before the commitment, not before the analysis.
  Speed amplifies whatever the orientation is; a fast loop on a distorted Orient
  executes errors at speed.

Then two routing questions:

- **Q1: Who or what are you deciding against?** Nature only (entropy, the clock,
  randomness) takes the decision-theory lens. Another mind with its own payoffs
  takes the game-theory lens. The rules of the game themselves take mechanism
  design + the systems lens. Mostly your own predictable deviations take the
  behavioral lens. A recurring
  pattern no single decision fixes takes the systems lens. Most stuck decisions are
  mis-routed here - nature treated as an adversary, or an adversary treated as
  nature.
- **Q2: Is this a one-off decision, or the Nth instance of a recurring state?**
  Any decision made three times the same way is a design defect, not diligence.
  Convert it to a policy (an if-then, a threshold, a standing rule); the session
  deliverable becomes the policy, not the pick.

## 2. Observe (brief)

Separate what the user knows from what they infer. Establish: the real deadline
and who set it; what the last action on this returned; what they are choosing not
to look at. Keep it short - Observe feeds Orient, it does not replace it.

## 3. Orient (the session core)

One big interrogation with three instruments, not four sequential stations.

**Instrument 1 - destruction and creation** (Boyd 1976, `references/boyd.md`).
Have the user state their current model of the situation, then take it apart:
what assumptions is the framing built on? What evidence would falsify each? Which
parts were inherited from an environment that no longer exists? Then synthesis:
recombine parts, including parts from unrelated domains, into a framing that did
not exist before. Tell: a model that has survived unchanged through several rounds
of new information is being defended, not updated.

**Instrument 2 - uncertainty classification** (`references/decision-theory.md`).
The uncertainty class picks the legal decision criteria; most stuck decisions are
stuck because the criterion does not match what is actually known:

- Known probabilities (risk): expected-value/utility reasoning is legitimate.
- Unknown probabilities (uncertainty): robustness criteria: maximin (floor the
  worst case - correct only when downside is ruin, paranoia elsewhere), minimax
  regret (name the worst realistic regret; naming it usually shrinks it), or an
  explicit optimism weighting.
- States cannot even be enumerated (ignorance): stop computing. Optionality,
  small reversible probes, satisficing.

**Instrument 3 - value of information.** Information is worth exactly the
improvement it makes to the decision, no more. The gate question before any
further research: **"What finding would change your choice?"** If the user cannot
name one, the decision is already made and the research is avoidance; say so. If
they can, price it: is getting it cheaper than the stakes it swings? Technical form: a
timeboxed spike is purchased information; size the timebox by what the finding
is worth, then decide with what you have.

### Lens routing (jurisdictions are enforced)

Each framework owns one jurisdiction. Invoking a lens outside its jurisdiction
produces a blended smoothie of frameworks; the boundaries are the architecture.

| Lens | Jurisdiction | Reference |
|---|---|---|
| Decision criteria | The standard: what an ideal agent would do | `references/decision-theory.md` |
| Behavioral | Predicting deviations (the user's included) | `references/bets-and-behavior.md` |
| Klein / recognition-primed | When intuition may close the loop | `references/bets-and-behavior.md` |
| Duke | The post-decision audit; bets and quitting | `references/bets-and-behavior.md` |
| Game theory | Another mind's revealed payoffs | `references/game-theory-mechanism-design.md` |
| Mechanism design | Rewriting the rules instead of playing | `references/game-theory-mechanism-design.md` |
| Meadows / systems | The level above the decision: the structure generating the situation | `references/systems-meadows.md` |

When another party is involved, run the canonical diagnostic order - each question
is cheaper and more often decisive than the one after it:

1. **Is there a game at all?** Most "opponents" are nature wearing a face.
2. **What is hidden?** Hidden information, hidden action.
3. **Can I redesign instead of play?** If the user controls any rules, agenda,
   format, information flows, or incentives: fix the structure so the desired
   behavior emerges, rather than out-playing the participants.
4. **Where will the humans deviate?** Including the user.

Structure check (Meadows, run before strategizing hard against a person): is this
a player problem or a structure problem? Most recurring "difficult person"
situations are structures wearing a face. Ask what the counterpart can actually
see from their position before attributing malice; ask what feedback loop is
missing before redesigning incentives; ask at what leverage level the user is
intervening and whether they can move one level up.

## 4. Decide (compressed)

Decisions are hypotheses, not commitments. Commit as late as responsibly possible,
then frame the pick as a bet with a named test. Set the aspiration level BEFORE
comparing options (satisficing): define "good enough", take the first option that
clears it. The tell that this is missing: the option set keeps growing while
nothing ships.

Gate on intuition (Kahneman-Klein): trust gut feel only where (a) the environment
has stable cause-effect regularities AND (b) the user has prolonged practice with
rapid, unambiguous feedback there. Codebases mostly pass; hiring, markets, and
org politics mostly fail. Trust the gut exactly as far as the environment trained
it, not one domain further.

## 5. Exit (every session ends in exactly one of these)

1. **A committed act** - the smallest reversible probe that tests the hypothesis,
   with the named observation that will grade it, and usually its kill criteria:
   "if X has not happened by DATE, quit." Kill criteria are precommitment against
   escalation; set them at decision time, when quality is high.
2. **An installed policy** - an if-then, threshold, or standing rule, when Q2
   revealed a recurring state.
3. **A scheduled decision** - a cool-off with a set time and the pre-work done,
   when classification demanded the brake.

"Think about it more" is not a valid exit. That is the jam these sessions exist
to break.

At session end, offer (default off) to append the exit artifact - the bet, its
kill criteria, the named test - to a file of the user's choosing, so future
audits grade the record rather than memory.

## Convergence discipline

The session must leave the user with fewer live options than it found, ending
in exactly one exit artifact. Divergence is scaffolding, permitted in one place
only: inside Orient, where destruction and creation may widen the frame to find
a framing that did not exist before. From Decide onward the work is narrowing.

- When options multiply, rank them by cost-to-test and cut the tail: the
  expensive, high-ignorance options go to the bottom and are not discussed
  again until the cheaper tests have failed.
- New options surfacing mid-session get logged, not litigated. Note them in
  the exit artifact's backlog if the user wants; do not reopen the comparison.
- Never end by presenting the option set back to the user, however well
  analyzed. A session that returns "here are your choices, clarified" has
  failed; the deliverable is the pick, the policy, or the scheduled decision,
  with its reasoning.

## 6. Post-decision audit (offer, don't force)

Grade the process, not the outcome. Judging a decision by one noisy result is the
error Duke names "resulting"; in low-validity environments even good processes
produce bad outcomes routinely, and grading outcomes there teaches superstition.
The audit objects: was the criterion matched to the uncertainty class, was
information priced, was the policy followed, were the kill criteria honored.
Corollary: in high-validity domains outcomes retrain patterns fast, so outcome
feedback is legitimate there; environment validity picks the grading regime.

## Failure modes and circuit breakers

Diagnose the jam, then apply the matching breaker. Never apply analysis to a jam
whose cause is the handoff.

- **Stuck in Orient** (rumination, analysis paralysis). Signature: more
  information makes it worse, because the jam is at the handoff, not the input.
  Breaker: force the Orient-to-Decide transition - a coarse two-question triage
  the user defines, an aspiration threshold, or the bare rule "move forward with
  the available information." Feeding a jammed Orient more analysis is the skill
  colluding with the failure.
- **Stuck in Decide** (endless option generation, waiting for certainty).
  Breaker: late commitment is not no commitment. Frame the leading option as a
  hypothesis, shrink the act until it is reversible, and compute the worst
  realistic regret of each act - it is usually smaller than the imagination says.
  A decision never tested teaches nothing.
- **Bad Orient feeding a fast loop** (the dangerous one: confident, fast, wrong).
  Breaker: the cool-off brake, plus the Kahneman-Klein gate above before trusting
  intuition.
- **Degraded-state tripwire** (decision-theoretic only). Flag when any of these
  appear: (a) the option set has collapsed to one or two combat-shaped moves,
  (b) probability estimates have gone extreme (certain doom, certain bad faith),
  (c) the urge is to act NOW on a problem whose real clock is hours or days,
  (d) an existing precommitted rule is being ignored. On any one of these, say
  plainly that
  no criterion runs well on degraded hardware, recommend slowing the loop and
  returning when regulated, and stop there. Do not prescribe regulation
  techniques; that jurisdiction belongs elsewhere.

## Second mode: capability audit

For "how do I get better at X", "why do we keep fumbling Y", or any recurring
decision domain. Diagnostic heuristic:

> Mastery = (prep depth x automaticity) / (deliberation load + autonomic drag)

- **Prep depth** - how completely complexity has been offloaded into preparation
  before execution. Technical form: runbooks, CI, scaffolding, paved-road tooling.
- **Automaticity** - how thoroughly the needed behaviors have migrated to
  procedural memory or paved paths (reps, if-then rules, habit, defaults).
- **Deliberation load** - conscious decision-making remaining at execution time.
  Reduced by environment design, precomputed policies, precommitment.
- **Autonomic drag** - stress activation or depletion degrading the operator at
  execution time (on-call fatigue is the engineering form).

Have the user rate each term for the domain (ordinal, 1-5, for comparison only -
arithmetic on the ratings is theater), then attack the worst term. Never optimize
execution before optimizing prep. When the numerator is high and the denominator
low, Orient and Decide collapse and the loop compresses toward Observe-to-Act:
Boyd's implicit guidance and control, engineered rather than wished for. The
one-off decision session and this formula are the same theory at two timescales -
the slow explicit loop for today's call, the built fast loop for every future one.

## Question bank

Ask these one or two at a time, routed by phase and lens; never as a form.

- **Observe:** What do you know vs what are you inferring? What is the real
  deadline and who set it? What did your last action on this return?
- **Orient:** Who or what are you actually deciding against? What would have to
  be true for your current framing to be wrong? What does someone with the
  opposite prior see in the same facts? Which part of this model is inherited
  rather than tested?
- **Decide:** What criterion are you using, and does it match what you actually
  know about the odds? What is "good enough"? Is any downside ruin - and if so,
  is it floored? What finding would change this choice?
- **Act:** What is the smallest reversible version of this? What observation, by
  when, grades the bet? If this recurs, what is the standing rule so you never
  decide it at runtime again?
- **Duke:** What would make this a good bet even if it loses? What signal, by
  what date, means quit?
- **Meadows:** Is this a player problem or a structure problem? What can the
  other actor actually see from their position? What feedback loop is missing?
  At what leverage level are you intervening, and can you move one up?
- **Mechanism design:** Which rules of this game do you actually control? Can
  the structure be changed so the right move and the easy move are the same?
  What metric is being gamed, and when is the metric itself reviewed?

## Non-goals

- **This skill never tells a user to "just go faster."** "Speed of iteration
  beats quality of iteration" is the bastardized OODA; Boyd never said it, and he
  drew Orient as the largest node precisely because iteration quality lives
  there. A fast loop on a bad model executes errors at speed. The operating rule
  is match loop speed to the engagement, and knowing which mode you are in is
  itself an Orient function.
- No somatic or nervous-system regulation prescriptions. Detect the degraded
  state, recommend pausing, stop.
- No personality typology.
- No personal constants. Where a coarse triage matrix is useful, help the user
  define their own two questions; never supply a canned personal one.
- No silver bullets. The higher the leverage point, the more the system resists
  changing it. There are no cheap tickets to mastery; the work is the work.

## References (read on demand, one level deep)

- `references/boyd.md` - the real 1995 diagram (not a circle), implicit guidance
  and control, destruction and creation, tempo, loop-speed matching.
- `references/decision-theory.md` - decision vs policy, uncertainty classes and
  their criteria, value of information, satisficing, runtime-to-design-time.
- `references/game-theory-mechanism-design.md` - revealed payoffs, repeated
  games, mechanism design, Goodhart and the scheduled metric review, Ostrom.
- `references/systems-meadows.md` - player vs structure, positional bounded
  rationality, the twelve leverage points intact, stocks and flows, missing
  feedback.
- `references/bets-and-behavior.md` - decisions as bets, resulting, kill
  criteria, Kahneman-Klein validity conditions, precommitment, base rates.
