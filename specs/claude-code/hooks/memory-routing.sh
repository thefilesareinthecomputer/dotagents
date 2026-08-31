#!/usr/bin/env bash
# PreToolUse(Write|Edit|Create|Update) - memory-write ROUTING nudge. Advisory
# only, NEVER blocks. Fires when a NEW file is about to be created under a
# memory dir (~/.claude/projects/<slug>/memory/*.md) and asks the routing
# question before the belief is written - the category that a yes/no "are you
# sure" prompt failed to surface.
#
# Only new files: an edit to an existing memory is already categorized, so
# nudging there would be noise. Every path allows the write (advisory).
# Non-blocking agent-visible text uses permissionDecision:allow + additionalContext
# (the verified channel) rather than bare stderr.
#
# Fail-open: missing jq / bad payload / non-memory path → silent allow.

set -u
command -v jq >/dev/null 2>&1 || exit 0

file="$(cat | jq -r '.tool_input.file_path // empty' 2>/dev/null)"

# Memory files only: .../projects/<slug>/memory/<name>.md
case "$file" in
  */projects/*/memory/*.md) ;;
  *) exit 0 ;;
esac
# MEMORY.md is the index, not a belief; and an existing file is already routed.
case "${file##*/}" in MEMORY.md) exit 0 ;; esac
[ -e "$file" ] && exit 0

read -r -d '' msg <<'EOF'
MEMORY WRITE - route it before you write it. Is this belief:
  (a) specific to THIS repo (its skills, tools, conventions, lifecycles)
        -> memory is correct. Proceed.
  (b) a UNIVERSAL working principle that applies in any repo
        -> belongs in global ~/.claude/CLAUDE.md, NOT repo memory.
  (c) an INVARIANT that must be ENFORCED rather than remembered
        -> belongs in a hook. Prose does not enforce; hooks do.
  (d) a REUSABLE PROCEDURE
        -> belongs in a skill.
  (e) a CLIENT / PROJECT FACT
        -> belongs in that project's own docs (vault, tasks/todo.md).
           NEVER memory: a copy here has no staleness detection and will
           silently contradict the canonical source.
Only (a) proceeds. Name the category before writing.
EOF

jq -n --arg m "$msg" '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "allow", additionalContext: $m}}'
