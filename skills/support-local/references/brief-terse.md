# Brief for support-local (terse variant)

Goal: {goal}
Corpus: {corpus}
Complete answer: {complete}
Out of scope: {out_of_scope}
Budget: {budget_turns} turns, {budget_calls} local calls.

Use `local-model-task search` (`python3 ~/.agents/skills/local-model-task/scripts/local_model_task.py search --question "..." --pattern <regex> --path {corpus}`) and your own Read to verify. Never call Ollama directly. Every claim needs a `path:line` you re-read, or `verified: false`. If the corpus lacks the answer, return `answerable: false` with a coverage line.

Failures: exit 3 or a denied tool call means stop with `stop_reason: "blocked"`; exit 4 or 5 means one narrower retry (`--max-matches 40 --top 5`), then move on; exit 6 means one plain retry, then move on. Never run a failing call more than twice. With two turns left, return what you have with `stop_reason: "budget"`. Return only this JSON object:

{{"goal": "...", "answer": "...", "answerable": true, "evidence": [{{"claim": "...", "ref": "path:LINE", "verified": true}}], "coverage": "...", "local_calls": 0, "stop_reason": "answered | budget | no progress | blocked"}}
