#!/usr/bin/env bash
# Tests for the memory-routing.sh PreToolUse hook.
# Target: the repo's specs/claude-code/hooks/memory-routing.sh by default; HOOK_UNDER_TEST
# points the run at a station copy such as ~/.claude/hooks/memory-routing.sh (seeded per SPEC-CLAUDE-CODE.md §8).
# Run: bash tests/station-hooks/test-memory-routing.sh
#
# Contract: nudges only on a NEW memory-dir file, with a count tier added at 50
# and 75; denies a new file once the folder would exceed 100 memories.
# Silent on: existing files, MEMORY.md, non-memory paths, bad input.
set -u

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="${HOOK_UNDER_TEST:-$REPO/specs/claude-code/hooks/memory-routing.sh}"
[ -f "$HOOK" ] || { echo "FATAL: hook not found at $HOOK"; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "FATAL: jq required"; exit 2; }

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
memdir="$tmp/projects/slug/memory"; mkdir -p "$memdir"
existing="$memdir/existing.md"; echo x > "$existing"

pass=0; fail=0
# The hook only fires under the harness config dir, so point it at the temp tree.
run() { printf '{"tool_input":{"file_path":"%s"}}' "$1" | CLAUDE_CONFIG_DIR="${ROOT:-$tmp}" bash "$HOOK" 2>/dev/null; }
# outcome: "nudge" (allow+additionalContext), "silent" (no output), "BLOCK(<decision>)"
outcome() {
  local out dec ctx
  out="$(run "$1")"
  [ -z "$out" ] && { echo silent; return; }
  dec="$(printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecision // "?"')"
  ctx="$(printf '%s' "$out" | jq -r '.hookSpecificOutput.additionalContext // empty')"
  [ "$dec" != allow ] && { echo "BLOCK($dec)"; return; }
  [ -n "$ctx" ] && echo nudge || echo silent
}
check() { local got; got="$(outcome "$2")"; if [ "$got" = "$1" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL [$3] want=$1 got=$got"; fi; }
# has/lacks: whether the hook's text (context or deny reason) for a new file contains a phrase
text() { run "$1" | jq -r '.hookSpecificOutput | (.additionalContext // .permissionDecisionReason // "")'; }
has()   { if text "$2" | grep -qF "$1"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL [$3] missing: $1"; fi; }
lacks() { if text "$2" | grep -qF "$1"; then fail=$((fail+1)); echo "FAIL [$3] unexpected: $1"; else pass=$((pass+1)); fi; }
# fill N: make the folder hold exactly N memories (MEMORY.md and existing.md included in the setup)
fill() {
  rm -f "$memdir"/m-*.md
  local i=1
  while [ "$i" -lt "$1" ]; do echo x > "$memdir/m-$i.md"; i=$((i+1)); done
  echo idx > "$memdir/MEMORY.md"
}

check nudge  "$memdir/new-belief.md"        "new memory file -> route"
check silent "$existing"                     "existing memory -> already routed"
check silent "$memdir/MEMORY.md"             "the index itself -> skip"
check silent "$tmp/projects/slug/notes.md"   "non-memory path in a project -> skip"
check silent "$tmp/random/file.md"           "unrelated path -> skip"
check silent "$memdir/archive/old.md"        "nested folder under memory/ -> skip"
check silent "$tmp/projects/a/b/memory/x.md" "deeper slug -> skip"
mkdir -p "$tmp/repo/projects/acme/memory"
check silent "$tmp/repo/projects/acme/memory/new.md" "same layout outside the config dir -> skip"
ROOT="$tmp/" check nudge "$memdir/new-belief.md" "trailing slash on the config dir -> still routes"
ln -s "$tmp" "$tmp/cfg-link"
ROOT="$tmp/cfg-link" check nudge "$memdir/new-belief.md" "symlinked config dir -> still routes"
mkdir -p "$tmp/cfg2" && ln -s "$tmp/projects" "$tmp/cfg2/projects"
ROOT="$tmp/cfg2" check nudge "$tmp/cfg2/projects/slug/memory/new-belief.md" "symlinked projects/ -> still routes"
mkdir -p "$tmp/projects/fresh"
check nudge "$tmp/projects/fresh/memory/first.md" "first memory, memory/ not created yet -> routes"
has "when to open it" "$memdir/new-belief.md" "routing names the index-line rule"

# Tiers, keyed on the count after the write. fill N leaves N memories; MEMORY.md never counts.
fill 48; lacks "MEMORY COUNT" "$memdir/new.md" "49 after -> routing only"
fill 49; has "hygiene check" "$memdir/new.md" "50 after -> hygiene tier"
         has "hard rules"    "$memdir/new.md" "50 after -> rules-in-disguise prompt"
fill 73; lacks "important and unique" "$memdir/new.md" "74 after -> still hygiene tier"
fill 74; has "important and unique" "$memdir/new.md" "75 after -> louder tier"
fill 99; check nudge "$memdir/new.md" "100 after -> allowed at the cap"
fill 100; check "BLOCK(deny)" "$memdir/new.md" "101 after -> denied"
          has "approval before deleting" "$memdir/new.md" "deny reason gates deletion on approval"
          check silent "$existing" "at the cap, editing an existing memory stays allowed"

# fail-open on garbage
out="$(printf 'not json' | bash "$HOOK" 2>/dev/null; echo "rc=$?")"
case "$out" in *rc=0*) pass=$((pass+1)) ;; *) fail=$((fail+1)); echo "FAIL [garbage-fail-open] $out" ;; esac

echo
echo "memory-routing: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
