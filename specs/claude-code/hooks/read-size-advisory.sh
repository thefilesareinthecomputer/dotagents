#!/usr/bin/env bash
# PreToolUse(Read) - advisory only, NEVER blocks.
#
# On a whole-file Read of a large file, injects a one-line nudge suggesting a
# targeted read or a structural outline. The read still proceeds; this only
# informs the agent. Deliberately the opposite of claude-mem's old blocking
# Read hook (SPEC-CLAUDE §3.1): it never substitutes or withholds content.
#
# Fail-open by construction: every code path allows the tool. A missing jq, an
# unreadable file, or a parse error results in a silent allow, never a block.
# Cheap by construction: size comes from `stat` (O(1)), never `wc -c` (reads
# the whole file) - this runs on every Read.
#
# Tunable: READ_ADVISORY_BYTES (default 204800 = 200KB). Set high on purpose -
# a nudge that fires on ordinary files becomes noise and gets ignored.

set -u
threshold="${READ_ADVISORY_BYTES:-204800}"

# No jq → silent allow (exit 0 with no output is 'allow' to Claude Code).
command -v jq >/dev/null 2>&1 || exit 0

# One jq pass (this runs on every Read): tab-join the three fields.
IFS=$'\t' read -r file offset limit < <(
  printf '%s' "$(cat)" | jq -r '[.tool_input.file_path, .tool_input.offset, .tool_input.limit] | @tsv' 2>/dev/null
)

# Targeted read (offset/limit present) = the agent already knows what it wants.
# Missing/empty path or not-a-regular-file = nothing to weigh in on. Silent allow.
[ -n "$offset" ] && exit 0
[ -n "$limit" ] && exit 0
[ -n "$file" ] && [ -f "$file" ] || exit 0

# O(1) byte size, portable across macOS (stat -f%z) and Linux (stat -c%s).
# `--` so a file literally named `-c` is not parsed as an option.
size="$(stat -f%z -- "$file" 2>/dev/null || stat -c%s -- "$file" 2>/dev/null || echo 0)"
[ "$size" -gt "$threshold" ] 2>/dev/null || exit 0

kb=$(( size / 1024 ))
name="${file##*/}"
jq -n --arg msg "$name is ${kb}KB - this reads it whole. Need only part? Re-Read with offset/limit, or smart_outline(\"$file\") for structure first." \
  '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "allow", additionalContext: $msg}}'
