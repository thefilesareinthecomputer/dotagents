# Socratic question taxonomy and probe patterns

The six question types (Foundation for Critical Thinking taxonomy, attributed
1997), each with stems adapted to tutoring a technical topic, plus the mapping
from the kind of gap a learner's explanation revealed to the probe that opens
it. Quality over quantity: one well-aimed question beats five generic ones
[question-quality].

## The six types

1. **Clarification** - "What do you mean by X?" · "Can you give me a concrete
   example of that?" · "How would you say that to someone who has never seen
   the term?" · "Which part of that is the core idea and which is detail?"
2. **Probing assumptions** - "What are you taking for granted there?" · "Does
   that hold when [boundary condition]?" · "What would have to be true for
   that to work?"
3. **Probing reasons and evidence** - "How do you know that?" · "What's the
   evidence for that step?" · "Why would that be true?" (elaborative
   interrogation) · "Is that a definition, an observation, or a conclusion?"
4. **Viewpoints and perspectives** - "How would [alternative school/system/
   design] handle this?" · "What's the strongest argument against doing it
   this way?" · "Who pays the cost of that tradeoff?"
5. **Implications and consequences** - "If that's true, what follows?" ·
   "What breaks if X is removed?" · "Where would this fail at scale/in the
   edge case?"
6. **Questions about the question** - "Why does this question matter for the
   topic?" · "What question should we be asking instead?" · "What would you
   need to know to answer that yourself?"

## Gap kind to probe

| Revealed gap | Lead probe type | Pattern |
|---|---|---|
| Vague hand-wave ("it just handles it") | Clarification | Ask for the mechanism in their words, then an example |
| Memorized phrase without grounding | Reasons/evidence | "Why would that be true?" then ask them to derive one step |
| Wrong claim stated confidently | Assumptions, then evidence | Surface the premise it rests on; test it against a case they accept (elenchus - let the contradiction do the work) |
| Missing boundary/edge behavior | Implications | "What happens when [edge]?" |
| One-sided view of a tradeoff | Viewpoints | Steelman the alternative, ask them to attack their own choice |
| Confusion about why the topic matters | About the question | Reconnect to the goal that brought them here |

## Escalation ladder (stuck point)

Guided, never unassisted [guided-not-unassisted]. On a stuck point, descend one
rung at a time; re-ascend as soon as the learner moves:

1. Reframe the same question from a different angle.
2. Narrow it - split off the smallest answerable piece.
3. Hint - point at the relevant fact or section without stating the conclusion.
4. Teach - a worked explanation of just that point [novice-guard], then
   re-elicit: the learner restates it in their own words before moving on.

Never skip straight to rung 4 while rungs 1-3 are untried, and never stay on
rungs 1-3 after they have failed twice - that is stonewalling, not teaching.
