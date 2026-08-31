#!/usr/bin/env bash
# Tests for the memory-routing.sh PreToolUse hook.
# Target: ~/.claude/hooks/memory-routing.sh (seeded from SPEC-CLAUDE-CODE.md §8).
# Run: bash tests/station-hooks/test-memory-routing.sh
#
# Contract: NEVER blocks (always allow). Nudges only on a NEW memory-dir file.
# Silent on: existing files, MEMORY.md, non-memory paths, bad input.
set -u

HOOK="${HOOK_UNDER_TEST:-$HOME/.claude/hooks/memory-routing.sh}"
[ -f "$HOOK" ] || { echo "FATAL: hook not found at $HOOK"; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "FATAL: jq required"; exit 2; }

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
memdir="$tmp/projects/slug/memory"; mkdir -p "$memdir"
existing="$memdir/existing.md"; echo x > "$existing"

pass=0; fail=0
# outcome: "nudge" (allow+additionalContext), "silent" (no output), "BLOCK" (contract violation)
outcome() {
  local out dec ctx
  out="$(printf '{"tool_input":{"file_path":"%s"}}' "$1" | bash "$HOOK" 2>/dev/null)"
  [ -z "$out" ] && { echo silent; return; }
  dec="$(printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecision // "?"')"
  ctx="$(printf '%s' "$out" | jq -r '.hookSpecificOutput.additionalContext // empty')"
  [ "$dec" != allow ] && { echo "BLOCK($dec)"; return; }
  [ -n "$ctx" ] && echo nudge || echo silent
}
check() { local got; got="$(outcome "$2")"; if [ "$got" = "$1" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL [$3] want=$1 got=$got"; fi; }

check nudge  "$memdir/new-belief.md"        "new memory file -> route"
check silent "$existing"                     "existing memory -> already routed"
check silent "$memdir/MEMORY.md"             "the index itself -> skip"
check silent "$tmp/projects/slug/notes.md"   "non-memory path in a project -> skip"
check silent "$tmp/random/file.md"           "unrelated path -> skip"

# never blocks, even on a new file
dec="$(printf '{"tool_input":{"file_path":"%s"}}' "$memdir/x.md" | bash "$HOOK" 2>/dev/null | jq -r '.hookSpecificOutput.permissionDecision')"
[ "$dec" = allow ] && pass=$((pass+1)) || { fail=$((fail+1)); echo "FAIL [never-blocks] got=$dec"; }

# fail-open on garbage
out="$(printf 'not json' | bash "$HOOK" 2>/dev/null; echo "rc=$?")"
case "$out" in *rc=0*) pass=$((pass+1)) ;; *) fail=$((fail+1)); echo "FAIL [garbage-fail-open] $out" ;; esac

echo
echo "memory-routing: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
