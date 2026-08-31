# Tiering the security review

How hard the review works is a function of what the diff can reach.
A change to a hook, a script, a subagent definition or a permission file executes on every future session on every machine; a change to prose is read by whoever opens it.
Pricing both the same is how a docs-only diff gets three adversarial passes while the budget that should have gone to judgment goes to proofreading.

`closeout_lint.py` classifies the changed paths and prints the tier, so the choice is visible rather than silent.

| Tier | What the diff touches | Review |
|---|---|---|
| A | hooks, scripts, subagent or command definitions, harness settings, permission or trust config | every domain of the checklist, then a re-review after fixes |
| B | prose and specs only | one pass on secrets, untrusted input, egress and factual claims; the executable domains cannot be tripped |

## The tier is a floor, not a ceiling

The user can force Tier A.
A Tier B finding that turns out to touch behavior promotes the diff to A for the re-review.
A reviewer that finds the diff contradicts the tier it was handed says so and reviews as Tier A.

## What Tier B still has to do

Tier B is not a lighter standard, it is a narrower surface.
The one defect that shipped from the lowest-risk diff in the review that motivated this work was a **false factual claim** - a sentence that parsed cleanly and was wrong, caught only by reproducing what it asserted.
No linter flags that class, and no reduction in tier excuses it.

Tier B therefore keeps: secrets, untrusted input, egress and persistence, personal constants, and checking the diff's cheap assertions against reality.
It drops only what a prose diff cannot reach - hooks and command execution, network exposure, plugin and MCP trust, permissions and settings.

## Why a linter does not replace the reviewer

The mechanical sweep reads text against itself.
It can prove a variable is unassigned, a list is misnumbered, a count disagrees with what follows it, a link resolves to nothing.
It cannot read a well-formed sentence and tell you it is false, and it cannot tell you a rule you just wrote will misfire on every future session.
The sweep shortens the review by removing the proofreading; the judgment half is the review.
