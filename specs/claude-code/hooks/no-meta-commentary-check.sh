#!/usr/bin/env bash
# PostToolUse(Write|Edit|MultiEdit|NotebookEdit|Update|Create) - advisory only,
# NEVER blocks. The second half of no-meta-commentary.sh.
#
# It fires ONLY for a file the pre-side flagged in this session, and asks one
# question the pre-side cannot: did the phrase survive into the file as saved.
# Every other write is silent and touches no disk, so this is not a second scan
# of the same text - it is the check that the reminder was acted on or knowingly
# declined. The flag is one-shot: cleared on the first check either way, so a
# file cannot nag twice.
#
# Non-blocking agent-visible text goes through PostToolUse `additionalContext`.
# Bare stderr at exit 0 is swallowed by the harness (verified footgun, see
# memory_lint.py) - a hook that only prints there is a hook nobody reads.
#
# Fail-open by construction: missing jq, missing pattern file, unreadable state
# or file, or a garbage payload all resolve to silence.

set -u

command -v jq >/dev/null 2>&1 || exit 0

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || exit 0
patfile="$here/no-meta-commentary.patterns"
[ -f "$patfile" ] || exit 0

IFS=$'\t' read -r session file < <(
  printf '%s' "$(cat)" | jq -r '[.session_id, (.tool_input.file_path // .tool_input.notebook_path // "")] | @tsv' 2>/dev/null
)
[ -n "$file" ] || exit 0

# Was this exact file flagged by the pre-side in this session?
sid="${session//[^A-Za-z0-9._-]/}"
[ -n "$sid" ] || sid="nosession"
[ -n "${XDG_STATE_HOME:-}${HOME:-}" ] || exit 0
state="${XDG_STATE_HOME:-${HOME:-}/.cache}/no-meta-commentary/$sid"
[ -f "$state" ] && [ ! -L "$state" ] || exit 0
read -r flagged 2>/dev/null < "$state" || exit 0
rm -f -- "$state" 2>/dev/null || true          # one-shot: never nag twice
[ "$flagged" = "$file" ] || exit 0

# The write may have been a delete or a rename; and a huge file is not worth
# re-reading for a nudge.
[ -f "$file" ] || exit 0
size="$(stat -f%z -- "$file" 2>/dev/null || stat -c%s -- "$file" 2>/dev/null || echo 0)"
[ "$size" -le 204800 ] 2>/dev/null || exit 0

pats="$(grep -v -e '^#' -e '^[[:space:]]*$' -- "$patfile" 2>/dev/null)" || exit 0
[ -n "$pats" ] || exit 0

# Same stripping as the pre-side: a phrase inside a code span, a fenced block or
# a quotation is being named, not said.
hit="$(sed -e '/^[[:space:]]*```/,/^[[:space:]]*```/d' -e 's/`[^`]*`//g' -e 's/"[^"]*"//g' -- "$file" 2>/dev/null \
       | grep -o -i -m1 -E "$pats" 2>/dev/null)"
[ -n "$hit" ] || exit 0                         # corrected, or never landed: silent

name="${file##*/}"
jq -n --arg msg "\"$hit\" is still in $name as saved. Move it to the reply or drop it, unless it is genuinely part of the document - in which case it stays and this line is noise." \
  '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $msg}}'
exit 0
