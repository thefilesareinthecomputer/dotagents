#!/usr/bin/env bash
# Table-driven tests for the read-size-advisory PreToolUse hook.
# Target: ~/.claude/hooks/read-size-advisory.sh (per-machine, seeded from
# SPEC-CLAUDE-CODE.md §8). Run: bash tests/station-hooks/test-read-size-advisory.sh
# Exit 0 = all green; nonzero = failures listed.
#
# Contract: ADVISORY ONLY. Every path must resolve to "allow" (never block).
# A "nudge" = allow + additionalContext; "silent" = no output (implicit allow).
# It must fire ONLY on a whole-file Read of a file over the byte threshold.
set -u

HOOK="${HOOK_UNDER_TEST:-$HOME/.claude/hooks/read-size-advisory.sh}"
[ -f "$HOOK" ] || { echo "FATAL: hook not found at $HOOK"; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "FATAL: jq required"; exit 2; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
big="$tmp/big.txt"; small="$tmp/small.txt"
# 120KB and 1KB - content is irrelevant, only size is read (via stat).
head -c 122880 /dev/zero | tr '\0' 'x' > "$big"
head -c 1024 /dev/zero | tr '\0' 'y' > "$small"

pass=0; fail=0

# outcome(): "nudge" if additionalContext present, "silent" if no output,
# "BLOCK" if anything ever denies/asks (a contract violation).
outcome() {
  local payload out decision ctx
  payload="$1"
  out="$(printf '%s' "$payload" | READ_ADVISORY_BYTES="${THRESH:-102400}" bash "$HOOK" 2>/dev/null)"
  [ -z "$out" ] && { echo "silent"; return; }
  decision="$(printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecision // "?"' 2>/dev/null)"
  ctx="$(printf '%s' "$out" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null)"
  if [ "$decision" != "allow" ]; then echo "BLOCK($decision)"; return; fi
  [ -n "$ctx" ] && echo "nudge" || echo "silent"
}

check() {
  local expected="$1" label="$2" payload="$3"
  local got; got="$(outcome "$payload")"
  if [ "$got" = "$expected" ]; then pass=$((pass+1));
  else fail=$((fail+1)); echo "FAIL [$label] expected=$expected got=$got"; fi
}

# ---- must NUDGE: whole-file read of a large file ----------------------------
check nudge  "big-whole"        "$(jq -cn --arg f "$big" '{tool_name:"Read",tool_input:{file_path:$f}}')"

# ---- must stay SILENT -------------------------------------------------------
check silent "big-targeted-both" "$(jq -cn --arg f "$big" '{tool_name:"Read",tool_input:{file_path:$f,offset:10,limit:50}}')"
check silent "big-offset-only"   "$(jq -cn --arg f "$big" '{tool_name:"Read",tool_input:{file_path:$f,offset:10}}')"
check silent "big-limit-only"    "$(jq -cn --arg f "$big" '{tool_name:"Read",tool_input:{file_path:$f,limit:50}}')"
check silent "small-whole"       "$(jq -cn --arg f "$small" '{tool_name:"Read",tool_input:{file_path:$f}}')"
check silent "missing-file"      '{"tool_name":"Read","tool_input":{"file_path":"/no/such/file.md"}}'
check silent "empty-path"        '{"tool_name":"Read","tool_input":{}}'
check silent "garbage-payload"   'not even json'

# ---- fail-open: below threshold silent even when whole-file ------------------
THRESH=999999999 check silent "under-huge-threshold" "$(jq -cn --arg f "$big" '{tool_name:"Read",tool_input:{file_path:$f}}')"

echo
echo "read-size-advisory: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
