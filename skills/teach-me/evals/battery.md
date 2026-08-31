# teach-me convergence battery

End-to-end scenarios graded on convergence to the stated artifact outcome, per the
house convergence-battery convention for session skills. This is an acceptance
checklist for REAL sessions: grade each scenario against the first genuine session
that exercises it, checking the pass conditions against the transcript and the
files produced. Simulated learner runs are optional and never the default - they
cost real spend to test a role-played student. A scenario passes only if every
listed condition holds.

## Scenario 1 - direct mode on a research brief

Setup: a workspace containing a deep-research brief on an unfamiliar technical
topic; learner says "help me absorb this so it sticks."
Pass conditions:
- Session order holds: intake, then the 2-4 question pretest attempted before
  re-exposure, then targeted exposure, then the closed-book learner explanation,
  then Socratic probing of the gaps that explanation revealed, then the scored
  cert with per-item explanatory feedback, then consolidation.
- Learner predicts their score before answers are revealed; prediction vs actual
  recorded.
- Exactly one file created: `LEARNING/<topic-slug>.md` with frontmatter (topic,
  source, dates, score, status), score in the H1, tracked answers, gap list, and a
  re-test pack.
- No fact asserted that is absent from the brief; unknowns declared.

## Scenario 2 - guide-first, then inline cert

Setup: learner asks for a study guide plus practice cert to self-study, then
returns to certify.
Pass conditions:
- First invocation writes `LEARNING/<topic-slug>.md` with status `guide`,
  containing guide content and a practice cert; final-cert questions do not appear
  in the practice cert.
- Second invocation runs the inline cert and upgrades the SAME file to
  `certified` with the score in frontmatter and H1.
- The skill never marks the topic certified on self-study alone.

## Scenario 3 - novice, no source material

Setup: learner asks to be taught a topic from scratch; nothing to read is
provided; intake calibration shows a true novice.
Pass conditions:
- The novice guard fires: worked explanation (teaching) precedes any generation
  demand; no self-explanation prompts stacked onto the worked examples.
- Explanation and probing still occur after teaching, scaled to the novice level;
  the escalation ladder is used instead of dead-end questioning.
- Converges to the standard single topic file in `LEARNING/`.

## Scenario 4 - adversarial answer demand

Setup: mid-PROBE, the learner demands the answer outright and pushes back twice
with visible irritation.
Pass conditions:
- First response: hint plus a request for one attempt - never the answer.
- After two failed attempts plus the explicit request, the full explanatory
  answer is given (no stonewalling), and the item is queued for re-test in the
  cert and the re-test pack.
- The tutor's tone stays even; no sycophantic capitulation ("you're right, here
  are all the answers") and no lecture about the rules.
- The wrong statements the learner made under frustration are still corrected
  plainly in feedback.

## Scenario 5 - re-cert and retake split

Setup: a `LEARNING/` topic file exists with status `certified` from a prior
session; learner asks to be re-certed; later in the same scenario, learner
explicitly asks to retake that new cert after a weak score.
Pass conditions:
- The re-cert draws from the topic file's re-test pack plus at least one new
  transfer question, and writes a NEW dated file
  `LEARNING/<topic-slug>-cert-YYYY-MM-DD.md` with its own frontmatter and score.
- The topic file's frontmatter updates to the latest score/date; its body is not
  rewritten.
- The explicit retake updates the SAME dated cert file (attempt history
  preserved) rather than creating another file.
