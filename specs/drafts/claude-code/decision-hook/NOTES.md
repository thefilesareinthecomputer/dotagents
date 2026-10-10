# decision-hook notes

These notes hold the design history and measurements that stay out of the README. The spec is `tasks/SPEC-DECISION-HOOK.md` while the build is active, then `tasks/completed/`.

## Why a station hook and not a skill

It first landed under `skills/`, following the shape of `local-model-task`; the user asked why. A skill is a workflow the model invokes, and nothing here is one: `decide.py` is a PreToolUse guard like the fifteen in this tree, and the rest is operator tooling for it. It moved to the station hook tree the same day, with the SKILL.md turned into this folder's README and the trigger evals dropped, and then once more into `specs/drafts/` on the user's second ruling: a hook whose judgment has not passed its numbers is not part of any station spec, so it is not seeded, configured or wired until it does.

## Why one choice question and not five noul questions

`/v1/systemone` scores each question separately, with only the state prefix cached, so cost is linear in the question count: about 110 ms per question on tev1:0.8b. Five `noul` questions measured 593 ms median on the laptop, over the 500 ms gate. One `choice` question with the same six categories as options measured 280 ms median (103 ms on laya). The options name the same six judgments, so the question shape changed and the categories did not.

## Why routing is off by default

Phase 0f measured the embedding nearest-exemplar router over the station's 294 trigger-eval cases, leave-one-out, with `embeddinggemma`: top-1 on should-trigger cases 0.09 at threshold 0.60 and 0.27 with no threshold at all, against a 0.70 target. Nearest-neighbor similarity has a median of 0.60 because each skill's eval cases describe different situations on purpose, so no two of them are paraphrases. Adding skill descriptions as exemplars reached 0.49; tev1:0.8b as a 23-way `choice` router over skill descriptions reached 0.35 at 1.26 s per prompt. The code stays (one embedding and a matrix product) so a better exemplar set can be tried by rebuilding the index, and the mode is off until a measured run clears the target.

## Why the labeler scrubs on read

The first live harvest copied 21,124 raw tool calls into a labeled set before any cleaning step existed; the user caught it and the file was deleted. A labeled set is a copy that sits on disk for weeks, so it is scrubbed at the moment it is written: secrets by shape, then the station term list by the identifier hook's rule. The full sanitize pass still runs before any training; this is the first layer.

## What the scenario corpus showed (2026-10-09)

`references/scenarios.jsonl`: 126 invented calls, 80 should-ask (destroy 19, exfil 16, creds 16, config 15, install 14; 22 obfuscated) and 46 fine (24 scary-benign). Run live and zero-shot, tev1:0.8b reached recall 0.12 to 0.23 and laya 0.36 to 0.45, with 21 to 25 false escalations per 100 on the scary-benign rows; calibration found slopes near zero, so the probabilities hold little signal. A leave-one-out nearest-neighbor classifier over `embeddinggemma` embeddings of the call text reached recall 0.86 at k=5 and caught every obfuscated row but one. It failed on false escalations (19 per 100), because 18 of the 24 scary-benign rows sit next to their dangerous twins in embedding space. The next experiment is that classifier plus a deterministic path-scope feature; the hook's plumbing is proven by the harness tests and waits for a judgment that clears both numbers.

## What the first live harvest showed (counts only, 2026-10-09)

2,946 transcripts since 2026-07-01 hold 21,124 watched tool calls: 49 user rejections, 21 hook blocks, 270 in the obfuscated stratum by regex. 2,867 user prompts, 197 of them followed by a Skill call across 48 skill names. The 1,000-label floor for fine-tuning is reachable. The 70 weak positives (rejections and hook blocks) are candidates the user still confirms one by one, and a fifth of them is held out, so the 60 confirmed should-ask labels the calibration needs will take hand labeling of organic calls beyond them.
