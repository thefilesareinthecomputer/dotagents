# Evidence base

The findings behind every protocol step, distilled from a five-angle research
pass (2026-07-28; all URLs accessed then). Confidence: high on the core design
claims; per-claim caveats noted. Tags in brackets are referenced from SKILL.md.

## Contents

1. [Feynman technique: provenance and mechanisms](#1-feynman-technique-provenance-and-mechanisms)
2. [Socratic method: what works and its limits](#2-socratic-method-what-works-and-its-limits)
3. [Technique utility ratings](#3-technique-utility-ratings)
4. [Sequencing within a session](#4-sequencing-within-a-session)
5. [AI-tutor trial evidence](#5-ai-tutor-trial-evidence)
6. [Calibration and learner defaults](#6-calibration-and-learner-defaults)

## 1. Feynman technique: provenance and mechanisms

- **[provenance]** The named "Feynman Technique" is folklore: no primary source
  shows Feynman prescribing a study method. Scott H. Young coined/popularized
  the packaging (blog, 2011-09-01). Feynman's documented habits: a "Notebook of
  Things I Don't Know About" (via Gleick's *Genius*) and the freshman-lecture
  diagnostic - "I couldn't reduce it to the freshman level. That means we don't
  really understand it" (Goodstein & Goodstein, *Feynman's Lost Lecture*).
  Direct studies of the named technique are few and weak (Reyes et al. 2021,
  *Recoletos Multidisciplinary Research Journal*, small n; Cheng et al. 2026,
  confounded). The technique's authority comes from its mechanisms, below.
- **[self-explanation]** Prompted self-explanation: g = 0.55 [0.45, 0.65], 69
  effects (Bisra et al. 2018, *Educ Psych Review*, doi 10.1007/s10648-018-9434-x).
  Prompted self-explaining beats re-reading (Chi, de Leeuw, Chiu & LaVancher
  1994, *Cognitive Science* 18, 439-477).
- **[teach-to-learn]** Preparing to teach beats preparing for a test, d = .55-.59
  immediate (Fiorella & Mayer 2013, *CEP* 38(4)); the expectation alone helps
  (Nestojko et al. 2014, *Memory & Cognition* 42(7)). Meta: 28 studies
  (Kobayashi 2019, *JPR* 61(3); caveat - its g values are secondary-sourced).
- **[protege]** Learners work harder for someone they are teaching than for
  themselves; the effect is largest for weaker learners (Chase, Chin, Oppezzo &
  Schwartz 2009, *J Sci Educ Tech* 18(4)).
- **[ioed]** People overestimate their understanding specifically of
  explanatory knowledge; the illusion collapses when they try to explain
  (Rozenblit & Keil 2002, *Cognitive Science* 26(5), 12 studies). The
  closed-book explanation step exists to trigger exactly this collapse.

## 2. Socratic method: what works and its limits

- **[elenchus]** Classical structure: elicit a position, cross-examine, surface
  the inconsistency, reach aporia, refine (IEP "Socrates"; SEP "Socrates",
  2005, rev. 2022).
- **[six-types]** The question taxonomy (Foundation for Critical Thinking,
  attributed 1997; primary page member-walled, verified via reproductions):
  clarification · probing assumptions · probing reasons/evidence ·
  viewpoints/perspectives · implications/consequences · questions about the
  question. Details and probe patterns: `question-taxonomy.md`.
- **[prompt-over-tell]** Tutors experimentally suppressed from explaining and
  limited to prompting produced equal learning to tutors who explained -
  attributed to more scaffolding episodes and more student construction (Chi,
  Siler, Jeong, Yamauchi & Hausmann 2001, *Cognitive Science* 25(4)).
- **[question-quality]** Achievement correlates with question quality, not
  question frequency (Graesser & Person 1994, *AERJ* 31(1)).
- **[tutoring-effect]** Human tutoring d = 0.79; intelligent tutoring systems
  d = 0.76 - near parity, and far below the legendary 2-sigma (VanLehn 2011,
  *Educ Psychologist* 46(4)). ITS g = .42 vs classroom instruction and
  statistical parity with human tutors (Ma, Adesope, Nesbit & Liu 2014, *JEP*).
- **[guided-not-unassisted]** Unassisted discovery loses to explicit
  instruction (d = -0.38); enhanced discovery - scaffolding, feedback, worked
  examples, elicited explanation - wins (d = 0.30) (Alfieri, Brooks, Aldrich &
  Tenenbaum 2011, *JEP* 103(1), 164 studies). Minimal guidance fails until
  learners have high prior knowledge (Kirschner, Sweller & Clark 2006, *Educ
  Psychologist* 41(2)). Questioning is a scaffold, not a substitute for
  teaching.

## 3. Technique utility ratings

- **[utility-ratings]** Dunlosky, Rawson, Marsh, Nathan & Willingham 2013
  (*PSPI* 14(1)): high utility = practice testing, distributed practice; low
  utility = summarization, highlighting, keyword mnemonic, imagery-for-text,
  rereading. The remaining reviewed techniques - elaborative interrogation,
  self-explanation, interleaving - form the moderate tier (stated by
  elimination from the abstract's explicit high/low lists).
- **[retrieval]** Testing beats restudy: g = 0.50 [0.42, 0.58] overall, and
  **g = 0.73 with feedback vs 0.39 without**; recall formats beat recognition
  (Rowland 2014, *Psych Bulletin* 140(6)). g = 0.51 vs restudy across 272
  effects (Adesope, Trevisan & Sundararajan 2017, *RER* 87(3)). Repeated study
  wins at 5 minutes and loses at a week - STTT 61% vs SSSS 40% (Roediger &
  Karpicke 2006, *Psych Science* 17(3)).
- **[spacing]** Optimal re-study gaps grow with the retention goal; spacing is
  structurally multi-session (Cepeda et al. 2006, *Psych Bulletin* 132(3)).
  A single session cannot space - hence the re-test pack consumed by later
  on-demand re-certs.
- **[interleaving]** Mixed practice 63% vs blocked 20% on a delayed test
  (Rohrer & Taylor 2007, *Instructional Science* 35(6)). Order cert questions
  across subtopics, not blocked by subtopic.
- **[generative]** Across generative strategies, self-testing (70/76 positive
  experiments), self-explaining (44/54), and teaching (17/19) have the
  strongest records (Fiorella & Mayer 2016, *EPR* 28(4)).
- **[icap]** Engagement modes rank Interactive > Constructive > Active >
  Passive (Chi & Wylie 2014, *Educ Psychologist* 49(4)) - hold it as a
  heuristic, not a law; overt behavior imperfectly indexes mode (Thurn et al.
  2023, *npj Sci Learn*).
- **[desirable-difficulty]** Difficulties help only when the learner can
  succeed at them (Bjork & Bjork 2011). Calibrate demand to demonstrated
  competence.

## 4. Sequencing within a session

- **[pretesting]** Attempting answers before exposure helps the pretested
  material: g = 0.54 (k = 97) on prequestioned items vs g = 0.04 on other
  material (St. Hilaire, Chan & Ahn 2023, *PBR* 31(2), preregistered meta);
  requires studying the correct answers afterwards (Pan & Carpenter 2023,
  *EPR*); errorful generation before study beats read-only (Richland, Kornell
  & Kao 2009; Kornell, Hays & Bjork 2009).
- **[pretest-brevity]** At a 7-day delay, post-testing (d = 0.74) beats
  pre-testing (d = 0.35), and only post-testing transfers to untested items
  (Latimier et al. 2019, *npj Sci Learn*). The pretest is a short primer;
  post-exposure retrieval is the workhorse.
- **[productive-failure]** Problem-attempt before instruction beats
  instruction-first overall (g = 0.36 [0.20, 0.51]; Sinha & Kapur 2021, *RER*
  91(5)) but REVERSES for young/low-prior learners - hence the novice guard.
  Invent-first ties on procedure and wins on deep structure and transfer
  (Schwartz, Chase, Oppezzo & Chin 2011, *JEP*).
- **[novice-guard]** True novices learn better from worked examples/guidance
  first; the advantage reverses as expertise grows (Kalyuga, Chandler,
  Tuovinen & Sweller 2001, *JEP* 93(3); Kalyuga et al. 2003, expertise
  reversal). Worked examples g = 0.48 - and adding self-explanation prompts ON
  TOP of worked examples measured NEGATIVE vs examples alone (Barbieri et al.
  2023, *EPR*): do not stack techniques onto the teaching moment.
- **[explain-after-exposure]** The located dialogue evidence places prompted
  explanation and probing AFTER content exposure (Chi et al. 1994; Chi et al.
  2001). No study directly compares Socratic-before vs Socratic-after a
  Feynman-style explanation; the protocol's order is the evidence-consistent
  composition, not a directly tested sequence.
- **[feedback-timing]** Within-session testing with feedback consolidates;
  feedback amplifies the benefits and repairs errors (Butler & Roediger 2008,
  *Memory & Cognition* 36(3)). The testing effect shrinks as material
  complexity (element interactivity) rises (van Gog & Sweller 2015,
  *EPR*) - for dense material, lean harder on explain-and-probe.

## 5. AI-tutor trial evidence

- **[ai-tutor-wins]** A guardrailed AI tutor beat in-class active learning in a
  randomized crossover (194 students): 0.63 SD conservative, 0.73-1.3 SD by
  quantile regression, in less time, with higher engagement (Kestin et al.,
  *Scientific Reports*, 2025-06-03, doi 10.1038/s41598-025-97652-6). Its design
  principles: active learning, cognitive-load management, growth mindset,
  scaffolding, accuracy, targeted timely feedback, self-pacing; correct
  solutions were pre-embedded to suppress hallucination.
- **[answers-harm]** Unrestricted GPT access lifted practice scores (+48%)
  then cost 17% on the later unassisted exam vs control; a guardrailed tutor
  giving teacher-designed hints instead of answers removed the harm (~1,000
  students; Bastani et al., *PNAS* 122(26), 2025-06-25, doi
  10.1073/pnas.2422633122; a 2025-08-20 correction exists, content unreviewed).
  This is the load-bearing justification for hints-before-answers.
- **[questions-scale]** LLM guidance made human tutors ask more guiding
  questions and give fewer answers, +4 pp mastery overall and +9 pp for
  students of weaker tutors (Tutor CoPilot, Wang et al., arXiv:2410.03017,
  2024-10; preprint only).
- **[llm-meta]** LLM-supported learning meta-analyses: g = 0.577 (JCAL 2025,
  37 studies) and g = 0.683 with human support inside the interaction as the
  dominant moderator - g = 1.426 with vs 0.077 without (JECR 2025). The
  most-cited ChatGPT-learning meta-analysis (g = 0.867) was RETRACTED
  2026-04-22 - do not cite it.
- **[laziness]** AI help can lift task scores while producing no gain in
  knowledge, transfer, or retention - "metacognitive laziness" (Fan et al.,
  *BJET*, 2024-12). Performance during the session is not evidence of
  learning; the closed-book cert is.
- **[no-sycophancy]** Preference-trained assistants systematically favor
  agreeable responses over correct ones (Sharma et al. 2023, arXiv:2310.13548;
  production incident: OpenAI GPT-4o rollback, 2025-04). A tutor that affirms
  a wrong explanation is optimizing approval, not learning.

## 6. Calibration and learner defaults

- **[jol]** Delayed judgments of learning are far more accurate than immediate
  ones (Rhodes & Tauber 2011, *Psych Bulletin* 137(1), 112 effects). Seeing
  the answer inflates confidence - the "illusion of competence" (Koriat &
  Bjork 2005, *JEP:LMC* 31(2)). Hence: predict-your-score before answers are
  revealed, closed-book always.
- **[bad-defaults]** Learners' instincts are miscalibrated: 84% reread (55%
  rank it first) while 11% self-test (1% rank it first) (Karpicke, Butler &
  Roediger 2009, *Memory* 17(4)) - rereading being a low-utility technique
  [utility-ratings]. The skill exists to impose the high-utility defaults the
  learner would not pick alone.
