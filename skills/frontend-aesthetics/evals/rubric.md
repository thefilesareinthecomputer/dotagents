# Behavior eval rubric

Graders score each behavior run with this rubric. The scenarios, prompts, inputs, and per-scenario expectations are in `evals.json`. Keep the rubric and `evals.json` out of any skill copy a builder can read, because the audit expectations are an answer key.

## Scale

Score each applicable dimension 0, 1, or 2.

- **0** misses the requirement.
- **1** is partial or weakly evidenced.
- **2** meets the requirement with specific evidence.

## Dimensions

| Dimension | 0 | 1 | 2 | Scored by |
|---|---|---|---|---|
| Brief fidelity | Required content is missing or invented, or a supplied constraint (tokens, brand colors, dependency limit, read-only) is dropped. | Content and constraints are mostly honored, with a gap such as a missing step, a changed data value, or a constraint bent without a recorded reason. | All supplied content and constraints are honored, departures carry recorded reasons, and nothing is invented: no copy, data, testimonials, or metrics beyond the inputs. | Evidence grader |
| Direction and distinctiveness | No subject-specific idea, or the result is interchangeable with a generic response to a similar brief. | An idea is identifiable but only partly realized, or it lacks rendered evidence. | An idea is identifiable and demonstrably delivered in the rendered result. For a constrained app, task-specific hierarchy within the existing tokens earns 2 without new imagery or motion. | Visual grader |
| Hierarchy and typography | No clear primary element, or text collides, clips, or is illegible at a checked width. | Hierarchy reads, but emphasis competes, a numeric column misaligns, or wrapping breaks at one width. | The primary task or content leads; type roles are distinct and consistent; changing values use tabular figures; real content wraps intentionally at narrow and wide widths. | Visual grader |
| Surface coherence | Radii, borders, shadows, or colors conflict, or elements do not belong to the supplied system. | Mostly consistent, with a few unexplained local exceptions. | One set of color roles, radii, borders, elevation, and icon family, matching the supplied system where there is one; elevation appears only where it explains containment or interaction. | Visual grader |
| Responsive behavior | Content is lost or clipped, or the page scrolls horizontally at a checked width. | Usable at every checked width, with one cramped, wasted, or clipped region. | At 320 and 1440 CSS px, and at any intermediate capture, content order holds, nothing clips, and layout changes where the content needs it; horizontal scrolling appears only in an intentional contained region. | Visual grader |
| Complete states | Only the happy path exists. | Most required states exist; one is missing, unreachable, or indistinct. | Every state the scenario calls for (and the applicable default, hover, focus, active, selected, disabled, empty, loading, error, success, and long-content states) is present, reachable, and distinct with stable geometry; errors say what failed and how to recover without relying on color alone. | Visual grader |
| Interaction continuity | The primary task is blocked by keyboard or under reduced motion, scrolling is hijacked, or feedback reports success before success is known. | The task completes, with a gap such as a weak focus indicator, a missing fallback for an enhancement, or nonessential motion with no reduced path. | The primary task completes by keyboard and pointer with visible focus; feedback is prompt and truthful; input survives failure; reduced motion keeps all information and navigation; enhancements have plain fallbacks. | Evidence grader |
| Evidence honesty | Rendered verification is claimed without evidence, or a measurement has no source. | Claims are mostly backed, but some are unattributed or the list of unchecked items is vague. | Every visual or numeric claim names its capture, probe result, or command output; checked widths, states, and commands are listed; unrun checks are named. A run with no browser earns 2 by clearly listing the specific rendered checks still pending. | Evidence grader |

## Applicability

- Mark a dimension not applicable only with a reason grounded in the scenario, and write the reason on the score sheet.
- Direction and distinctiveness applies to every build or refinement scenario. It is not applicable only to the read-only audit, which must still assess the existing direction; score that assessment under brief fidelity.
- Complete states covers the states the scenario can reach. Static content does not need invented interactive states.
- The audit has no built surface to capture, so the evidence grader scores all of its applicable dimensions from the report. Each dimension is scored on whether the findings in that area are correct, located, and evidenced against the planted-issue expectations in `evals.json`. Flagging a legitimate choice (the black-on-white body text or the repeated card grid) as a defect costs one point in the matching dimension.

## Thresholds and hard fails

A scenario passes only when every applicable dimension scores at least 1 and the run earns at least 80 percent of the applicable points.

| Applicable dimensions | Maximum points | Minimum to pass (80 percent, rounded up) |
|---|---|---|
| 8 | 16 | 13 |
| 7 | 14 | 12 |
| 6 | 12 | 10 |

Any of these fails the scenario regardless of score:

1. **Invented measurement.** A contrast ratio, size, duration, frame rate, or count with no named command, probe result, capture, or source declaration behind it, or a capture the report describes but never took.
2. **Ignoring an explicit brand constraint.** Changing, dropping, or tinting a binding color, font rule, or token set the brief supplies, without the user's approval. Keeping the brand and recording a justified lint exception is the correct behavior.
3. **Hiding task information in reduced motion.** Any step, text, data value, or control that is missing or unusable when `prefers-reduced-motion: reduce` is set.

## Grading split

- **Visual grader (blinded).** Scores direction and distinctiveness, hierarchy and typography, surface coherence, responsive behavior, and complete states. It sees the brief, each run's source, and captures the orchestrator took at 320 and 1440 CSS px (plus any state captures), labeled A and B by a recorded coin flip. It never sees reports, run logs, or which skill version produced which output. For direction, it writes one line per output naming the subject-specific idea it can identify from the captures and source, or `none identifiable`; a 2 requires an idea it can name.
- **Evidence grader (unblinded).** Scores brief fidelity, interaction continuity, and evidence honesty from each run's own report, with that run's source open to check the report's claims. It also checks the hard fails and marks each `evals.json` expectation.
- Both graders are fresh, read-only spawns and never the advisor that reviewed a build slice.
- Scenarios run with only one arm (the audit and the dependency-free page) have no pair to blind; the visual grader sees one output labeled A.
- Expectations worded "With the rewritten skill" are marked not applicable for the current skill. They are pass or fail items on the checklist and do not change rubric points, so both arms are scored on the same dimensions.

## Reporting results

Record each scenario's pass or fail, the dimension scores, the hard-fail checks, and the expectation checklist for each arm. Name regressions and representative improvements with the evidence behind them. One build per arm per scenario supports no statistical claim; do not state averages, percentages of improvement, or significance.

## Score sheet template

```markdown
### <eval name> - arm <A or B> (<current or rewritten>, recorded after grading)

| Dimension | Applicable | Score | Evidence (capture, source line, or report line) |
|---|---|---|---|
| Brief fidelity | yes | | |
| Direction and distinctiveness | yes, or no: <reason> | | |
| Hierarchy and typography | yes | | |
| Surface coherence | yes | | |
| Responsive behavior | yes | | |
| Complete states | yes | | |
| Interaction continuity | yes | | |
| Evidence honesty | yes | | |

Points: <earned> of <applicable maximum>; minimum to pass: <from the threshold table>
Every applicable dimension at least 1: yes or no
Hard fails: invented measurement <no or evidence>; brand constraint ignored <no or evidence>; reduced motion hides task information <no or evidence>
Direction the visual grader identified: <one line, or none identifiable>
Result: PASS or FAIL

| Expectation | Pass, fail, or not applicable | Evidence |
|---|---|---|
| <expectation text from evals.json> | | |
```
