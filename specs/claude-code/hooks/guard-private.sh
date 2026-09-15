#!/usr/bin/env bash
# PreToolUse hook on Bash: refuse any shell command that names ~/.claude/private.
#
# The folder holds the station's identifier term list. The file tools are denied
# on it in settings.json; this closes the shell path (cat, sed, python -c, cp).
# It matches the literal path fragment only, so a command that reaches the folder
# through a variable or a symlink is not caught - this is the honest-case guard,
# not a sandbox. Exit 2 blocks the call. A missing jq denies the call instead
# of letting it run; see _require.sh.

set -uo pipefail
. "$(dirname "$0")/_require.sh" 2>/dev/null || { printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"hook preamble missing: _require.sh. This guard cannot evaluate the call, so it refuses."}}\n'; exit 0; }
require_deps jq

CMD="$(jq -r '.tool_input.command // empty' 2>/dev/null)" || exit 0
[ -n "$CMD" ] || exit 0

case "$CMD" in
  *".claude/private"*)
    echo "blocked: the command names ~/.claude/private, which holds the station's private term list. Its contents are not the model's to read or write; the reject_identifiers hook reads it on its own." >&2
    exit 2
    ;;
  *".claude/state"*)
    # The gate ack files live here. Touching one eases the memory gate or
    # the daemon-storm block for an hour, which is the user's call from a
    # real shell, never an agent's or a seat's.
    echo "blocked: the command names ~/.claude/state, which holds the gate ack files. Easing a gate is the user's decision from their own shell." >&2
    exit 2
    ;;
esac
exit 0
