#!/usr/bin/env bash
# Table-driven tests for the cover-me-nudge PostToolUse hook.
# Target: specs/claude-code/hooks/cover-me-nudge.sh (seeded to
# ~/.claude/hooks/ per SPEC-CLAUDE-CODE.md §8). Override with HOOK_UNDER_TEST.
# Run: bash tests/station-hooks/test-cover-me-nudge.sh
# Exit 0 = all green; nonzero = failures listed.
#
# Contract: ADVISORY ONLY. No path may ever block, deny or ask.
# A "nudge" = additionalContext present; "silent" = no output.
# It must fire on a destructive Bash command, or when the per-session tool-call
# counter reaches the threshold, and stay quiet otherwise.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
HOOK="${HOOK_UNDER_TEST:-$REPO/specs/claude-code/hooks/cover-me-nudge.sh}"
[ -f "$HOOK" ] || { echo "FATAL: hook not found at $HOOK"; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "FATAL: jq required"; exit 2; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
pass=0; fail=0
case_no=0

bash_payload() {
  jq -cn --arg s "${SID:-sess-1}" --arg c "$1" \
    '{session_id:$s,tool_name:"Bash",tool_input:{command:$c}}'
}

# run(): one hook invocation against an isolated state dir. Echoes "nudge",
# "silent", or "BLOCK(...)" if anything ever denies/asks (a contract violation).
run() {
  local payload="$1" out ctx decision
  out="$(printf '%s' "$payload" | XDG_STATE_HOME="$tmp/state-$case_no" \
    COVER_ME_NUDGE_CALLS="${THRESH:-45}" bash "$HOOK" 2>/dev/null)"
  [ -z "$out" ] && { echo "silent"; return; }
  decision="$(printf '%s' "$out" | jq -r \
    '(.decision // .hookSpecificOutput.permissionDecision // "none")' 2>/dev/null)"
  if [ "$decision" != "none" ]; then echo "BLOCK($decision)"; return; fi
  ctx="$(printf '%s' "$out" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null)"
  [ -n "$ctx" ] && echo "nudge" || echo "silent"
}

check() {
  local expected="$1" label="$2" payload="$3"
  case_no=$((case_no+1))
  local got; got="$(run "$payload")"
  if [ "$got" = "$expected" ]; then pass=$((pass+1));
  else fail=$((fail+1)); echo "FAIL [$label] expected=$expected got=$got"; fi
}

# check_seq(): fire N innocuous calls into one state dir, then assert the
# outcome of the next call. Exercises the counter, which check() cannot.
check_seq() {
  local expected="$1" label="$2" n="$3" final="$4" i got
  case_no=$((case_no+1))
  for ((i=0; i<n; i++)); do run "$(bash_payload "echo $i")" >/dev/null; done
  got="$(run "$final")"
  if [ "$got" = "$expected" ]; then pass=$((pass+1));
  else fail=$((fail+1)); echo "FAIL [$label] expected=$expected got=$got"; fi
}

# ---- must NUDGE: destructive Bash commands ----------------------------------
check nudge  "rm-rf"          "$(bash_payload 'rm -rf build/')"
check nudge  "rm-fr"          "$(bash_payload 'rm -fr /tmp/x')"
check nudge  "rm-rf-piped"    "$(bash_payload 'make clean && rm -rf dist')"
check nudge  "push-force"     "$(bash_payload 'git push --force origin main')"
check nudge  "push-force-lease" "$(bash_payload 'git push --force-with-lease')"
check nudge  "drop-table"     "$(bash_payload 'psql -c "DROP TABLE users"')"
check nudge  "drop-database"  "$(bash_payload 'mysql -e "drop database staging"')"
check nudge  "migrations-path" "$(bash_payload 'python manage.py migrate migrations/0007_add.py')"

# ---- must stay SILENT -------------------------------------------------------
check silent "plain-ls"       "$(bash_payload 'ls -la')"
check silent "plain-rm"       "$(bash_payload 'rm stale.lock')"
check silent "plain-push"     "$(bash_payload 'git push origin main')"
check silent "alarm-word"     "$(bash_payload 'grep -rn alarm src/')"
check silent "migrations-dir" "$(bash_payload 'ls migrations/')"
check silent "non-bash-tool"  '{"session_id":"s","tool_name":"Read","tool_input":{"file_path":"/x/migrations/1.sql"}}'
check silent "empty-command"  '{"session_id":"s","tool_name":"Bash","tool_input":{}}'
check silent "garbage-payload" 'not even json'
check silent "empty-payload"  ''

# ---- counter trigger --------------------------------------------------------
THRESH=5 check_seq nudge  "counter-reaches-threshold" 4 "$(bash_payload 'echo hi')"
THRESH=5 check_seq silent "counter-below-threshold"   2 "$(bash_payload 'echo hi')"
THRESH=99 check_seq silent "counter-high-threshold"   40 "$(bash_payload 'echo hi')"

# ---- counter resets after a fire (no repeat on the very next call) ----------
case_no=$((case_no+1))
for i in 1 2 3 4; do run "$(bash_payload "echo $i")" >/dev/null; done
first="$(THRESH=5 run "$(bash_payload 'echo fire')")"
second="$(THRESH=5 run "$(bash_payload 'echo again')")"
if [ "$first" = "nudge" ] && [ "$second" = "silent" ]; then pass=$((pass+1));
else fail=$((fail+1)); echo "FAIL [counter-resets] first=$first second=$second"; fi

# ---- destructive nudge is rate-limited, not repeated on every call ----------
case_no=$((case_no+1))
one="$(run "$(bash_payload 'rm -rf a')")"
two="$(run "$(bash_payload 'rm -rf b')")"
if [ "$one" = "nudge" ] && [ "$two" = "silent" ]; then pass=$((pass+1));
else fail=$((fail+1)); echo "FAIL [destructive-rate-limit] one=$one two=$two"; fi

# ---- sessions do not share a counter ----------------------------------------
# Same state dir, different session ids: four calls on A must not arm B.
case_no=$((case_no+1))
for i in 1 2 3 4; do
  payload_a="$(SID=sess-a; bash_payload "echo $i")"
  THRESH=5 run "$payload_a" >/dev/null
done
payload_a="$(SID=sess-a; bash_payload 'echo fifth')"
payload_b="$(SID=sess-b; bash_payload 'echo hi')"
# B first: a shared counter would already stand at 4 and fire on B's call.
b="$(THRESH=5 run "$payload_b")"
a="$(THRESH=5 run "$payload_a")"
if [ "$a" = "nudge" ] && [ "$b" = "silent" ]; then pass=$((pass+1));
else fail=$((fail+1)); echo "FAIL [session-isolation] a=$a b=$b"; fi

# ---- structural: no model call, no network, and it is O(1) ------------------
case_no=$((case_no+1))
if grep -qE '\b(curl|wget|claude|llm|openai|anthropic)\b' "$HOOK"; then
  fail=$((fail+1)); echo "FAIL [no-model-calls] hook references a network/model command"
else pass=$((pass+1)); fi

case_no=$((case_no+1))
start=$(date +%s)
for i in 1 2 3 4 5 6 7 8 9 10; do run "$(bash_payload 'ls')" >/dev/null; done
elapsed=$(( $(date +%s) - start ))
if [ "$elapsed" -le 3 ]; then pass=$((pass+1));
else fail=$((fail+1)); echo "FAIL [speed] 10 invocations took ${elapsed}s"; fi

echo
echo "cover-me-nudge: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
