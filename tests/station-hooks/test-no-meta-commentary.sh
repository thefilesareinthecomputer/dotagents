#!/usr/bin/env bash
# Tests for the no-meta-commentary pair: no-meta-commentary.sh (PreToolUse) and
# no-meta-commentary-check.sh (PostToolUse).
# Target: ~/.claude/hooks/ (seeded from specs/claude-code/hooks/).
# Run: bash tests/station-hooks/test-no-meta-commentary.sh
#
# Contract: NEITHER side ever blocks. The pre-side nudges only on incoming text
# carrying a listed shape, or on a new report-shaped filename. The post-side is
# silent unless the pre-side flagged that exact file in that session, and its
# flag is one-shot.
#
# The pattern list is validated against REAL files elsewhere (SPEC §8): a green
# run here proves the mechanism, not that the list is right.
set -u

PRE="${PRE_UNDER_TEST:-$HOME/.claude/hooks/no-meta-commentary.sh}"
POST="${POST_UNDER_TEST:-$HOME/.claude/hooks/no-meta-commentary-check.sh}"
for h in "$PRE" "$POST"; do [ -f "$h" ] || { echo "FATAL: hook not found at $h"; exit 2; }; done
command -v jq >/dev/null 2>&1 || { echo "FATAL: jq required"; exit 2; }

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
# Isolate the state dir so a test run cannot touch the real one.
export XDG_STATE_HOME="$tmp/state"

pass=0; fail=0
sid=0

# pre <file> <content> -> "nudge" | "silent" | "BLOCK(x)"
pre() {
  local out dec ctx
  out="$(jq -n --arg f "$1" --arg c "$2" --arg s "$3" \
        '{session_id:$s, tool_input:{file_path:$f, content:$c}}' | bash "$PRE" 2>/dev/null)"
  [ -z "$out" ] && { echo silent; return; }
  dec="$(printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecision // "?"')"
  ctx="$(printf '%s' "$out" | jq -r '.hookSpecificOutput.additionalContext // empty')"
  [ "$dec" != allow ] && { echo "BLOCK($dec)"; return; }
  [ -n "$ctx" ] && echo nudge || echo silent
}
post() {
  local out
  out="$(jq -n --arg f "$1" --arg s "$2" '{session_id:$s, tool_input:{file_path:$f}}' | bash "$POST" 2>/dev/null)"
  [ -z "$out" ] && { echo silent; return; }
  printf '%s' "$out" | jq -e '.hookSpecificOutput.additionalContext' >/dev/null 2>&1 && echo nudge || echo silent
}
check() { local got="$1" want="$2"; if [ "$got" = "$want" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL [$3] want=$want got=$got"; fi; }

# ---- pre-side: content signals -----------------------------------------------
check "$(pre "$tmp/a.md" "I have created the parser." s1)"        nudge  "first-person narration"
check "$(pre "$tmp/a.md" "## Summary of Changes"      s1)"        nudge  "session-report heading"
check "$(pre "$tmp/a.md" "Let me know if you want more." s1)"     nudge  "addressed to the reader"
check "$(pre "$tmp/a.md" "The parser handles CSV. Run make test." s1)" silent "ordinary content"
check "$(pre "$tmp/a.md" "Note that it is idempotent." s1)"       silent "prefix is not a match"
check "$(pre "$tmp/a.md" ""                            s1)"      silent "empty content"

# A phrase being NAMED rather than said: documentation about this rule quotes
# its own patterns, and any file documenting the hook trips it otherwise.
check "$(pre "$tmp/a.md" 'without them `note that I` matches inside it' s1)"  silent "inline code span"
check "$(pre "$tmp/a.md" 'the banned shape is "let me know"'            s1)"  silent "quoted string"
check "$(pre "$tmp/a.md" '```
I have created the parser.
```'                                                                   s1)"  silent "fenced block"
check "$(pre "$tmp/a.md" 'Note that I left the parser alone.'           s1)"  nudge  "same phrase as prose"

# ---- pre-side: path scoping --------------------------------------------------
check "$(pre "/x/hooks/thing.sh" "I have created it"   s1)"       silent "hooks dir carries the list"
check "$(pre "/x/skills/ai-slop-magic-eraser/S.md" "hope this helps" s1)" silent "the catalog quotes them"
check "$(pre "/x/tests/f.md" "I have created it"       s1)"       silent "test fixtures"
check "$(pre "/x/projects/p/memory/m.md" "I have created it" s1)" silent "memory is first person by design"
check "$(pre "/x/.claude/inbox/m.md" "I have created it" s1)"     silent "agent mail is correspondence"

# ---- pre-side: report-filename signal ----------------------------------------
check "$(pre "$tmp/AUDIT-REPORT.md" "Findings."        s1)"       nudge  "new report file"
check "$(pre "$tmp/tasks/AUDIT-REPORT.md" "Findings."  s1)"       silent "tasks/ is where records live"
printf 'x\n' > "$tmp/EXISTING-REPORT.md"
check "$(pre "$tmp/EXISTING-REPORT.md" "Findings."     s1)"       silent "existing file is established"

# ---- never blocks ------------------------------------------------------------
dec="$(jq -n --arg f "$tmp/a.md" '{session_id:"s9", tool_input:{file_path:$f, content:"I have created it"}}' \
      | bash "$PRE" 2>/dev/null | jq -r '.hookSpecificOutput.permissionDecision')"
check "$dec" allow "never-blocks contract"

# ---- fail-open ---------------------------------------------------------------
out="$(printf 'not json' | bash "$PRE" 2>/dev/null; echo "rc=$?")"
case "$out" in *rc=0*) pass=$((pass+1)) ;; *) fail=$((fail+1)); echo "FAIL [pre-garbage-fail-open] $out" ;; esac
out="$(printf 'not json' | bash "$POST" 2>/dev/null; echo "rc=$?")"
case "$out" in *rc=0*) pass=$((pass+1)) ;; *) fail=$((fail+1)); echo "FAIL [post-garbage-fail-open] $out" ;; esac

# ---- post-side: only after a flag, one-shot ----------------------------------
dirty="$tmp/dirty.md"; printf '# T\n\nI have created the parser.\n' > "$dirty"
clean="$tmp/clean.md";  printf '# T\n\nThe parser handles CSV.\n'    > "$clean"

check "$(post "$dirty" s2)"                                       silent "no flag -> silent"
pre "$dirty" "I have created the parser." s3 >/dev/null
check "$(post "$dirty" s3)"                                       nudge  "flagged and it survived"
check "$(post "$dirty" s3)"                                       silent "flag is one-shot"
pre "$clean" "I have created the parser." s4 >/dev/null
check "$(post "$clean" s4)"                                       silent "flagged but corrected"
pre "$dirty" "I have created the parser." s5 >/dev/null
check "$(post "$clean" s5)"                                       silent "different file -> silent"
pre "$dirty" "I have created the parser." s6 >/dev/null
check "$(post "$dirty" s7)"                                       silent "different session -> silent"
pre "$dirty" "I have created the parser." s8 >/dev/null
rm -f "$dirty"
check "$(post "$dirty" s8)"                                       silent "file gone -> silent"

echo
echo "no-meta-commentary: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
