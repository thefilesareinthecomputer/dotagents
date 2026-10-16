#!/usr/bin/env bash
# PreToolUse(Write|Edit|MultiEdit|NotebookEdit|Update|Create) - advisory only,
# NEVER blocks. GLOBAL (fires in every project).
#
# The rule is "chat is for chat, not files": commentary about the work, notes
# addressed to the user, and narration of what just happened belong in the reply,
# not in an authored file. The file gets the instruction, the path, the criterion.
#
# This hook does not decide that - no pattern list can. It scans only the text
# ABOUT to be written for a short list of high-precision chat-register shapes
# (no-meta-commentary.patterns) and, on a hit, injects one line naming the phrase.
# The write proceeds either way. A hit is a prompt to look, not a verdict.
#
# Scoped by measurement, not by document class: an earlier version of this rule
# was filed under "deliverables" and so fired on deliverables and nowhere else.
# The paths excluded below are the sites that legitimately QUOTE these phrases
# (the slop catalog, the hooks that carry the list, test fixtures) and the files
# written in first person by design (memory, agent mail).
#
# Fail-open by construction: missing jq, a missing pattern file, an unwritable
# state dir or a garbage payload all resolve to a silent allow, never a block.
# Cheap by construction: one jq pass and one grep over the incoming text only -
# never the whole file - because this runs on every write in every session.

set -u

command -v jq >/dev/null 2>&1 || exit 0

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || exit 0
patfile="$here/no-meta-commentary.patterns"
[ -f "$patfile" ] || exit 0

# Comment and blank lines out; the remainder is one ERE per line, which grep -E
# treats as alternatives when passed as a single newline-joined operand.
pats="$(grep -v -e '^#' -e '^[[:space:]]*$' -- "$patfile" 2>/dev/null)" || exit 0
[ -n "$pats" ] || exit 0

# The payload is read once; jq pulls each field raw. The text goes straight
# from jq into the matching pipeline below and never into a bash variable: a
# bash substitution over a large string is quadratic, and an earlier version
# that unescaped a @tsv field that way ran past its 5-second budget on every
# write above a few tens of kilobytes.
payload="$(cat)"
[ -n "$payload" ] || exit 0
session="$(printf '%s' "$payload" | jq -r '.session_id // ""' 2>/dev/null)" || exit 0
file="$(printf '%s' "$payload" | jq -r '.tool_input.file_path // .tool_input.notebook_path // ""' 2>/dev/null)" || exit 0

[ -n "$file" ] || exit 0

# Sites that legitimately hold these phrases: the catalog that documents them,
# the hooks carrying the list (this script matches itself otherwise), test
# fixtures, and the two file classes written in first person by design.
case "$file" in
  */hooks/*|*/skills/ai-slop-magic-eraser/*|*/tests/*|*/fixtures/*) exit 0 ;;
  */projects/*/memory/*|*/inbox/*|*/processed/*) exit 0 ;;
esac

name="${file##*/}"
msg=""

# A phrase inside a code span, a fenced block or a quotation is being NAMED, not
# said - documentation about the rule quotes its own patterns, which is how this
# hook fires on the file that documents it. Strip those before matching.
strip() { sed -e '/^[[:space:]]*```/,/^[[:space:]]*```/d' -e 's/`[^`]*`//g' -e 's/"[^"]*"//g' 2>/dev/null; }

# Only the INCOMING text: Write (.content), Edit (.new_string) and MultiEdit
# (.edits[].new_string), so an edit that REMOVES a flagged phrase stays silent.
# LC_ALL=C keeps the case-insensitive grep byte-wise; under a UTF-8 locale the
# same alternation runs an order of magnitude slower.
hit="$(printf '%s' "$payload" | jq -r '
    (.tool_input.content // "") + "\n" + (.tool_input.new_string // "")
      + "\n" + ([.tool_input.edits[]?.new_string // empty] | join("\n"))' 2>/dev/null \
  | strip | LC_ALL=C grep -o -i -m1 -E "$pats" 2>/dev/null)"
if [ -n "$hit" ]; then
  msg="\"$hit\" in $name reads as chat rather than content. If it is about the work, addressed to the user, or narrating what just happened, say it in the reply instead - the file gets the instruction, the path, the criterion. Keep it only if it is genuinely part of the document."
fi

# Path-only signal: the session-report habit that content patterns miss. A new
# REPORT/SUMMARY/FINDINGS/analysis file outside tasks/ is usually a reply that
# went into a file. Existing files are silent - they are already established.
if [ -z "$msg" ] && [ ! -e "$file" ]; then
  case "$file" in
    */tasks/*) ;;
    *REPORT*.md|*SUMMARY*.md|*FINDINGS*.md|*-analysis.md|*-report.md|*-summary.md)
      msg="$name looks like a session report. A finding usually belongs in the reply rather than in a new file - write the file only if the user asked for it." ;;
  esac
fi

[ -n "$msg" ] || exit 0

# Flag this file for the post-side, which checks whether the correction landed.
# Written only when something fired, so the quiet path touches no disk at all.
sid="${session//[^A-Za-z0-9._-]/}"
[ -n "$sid" ] || sid="nosession"
if [ -n "${XDG_STATE_HOME:-}${HOME:-}" ]; then
  dir="${XDG_STATE_HOME:-${HOME:-}/.cache}/no-meta-commentary"
  if [ ! -L "$dir" ] && mkdir -p -m 700 "$dir" 2>/dev/null && [ ! -L "$dir/$sid" ]; then
    printf '%s\n' "$file" 2>/dev/null > "$dir/$sid" || true
  fi
fi

# Context only, no permissionDecision: an "allow" from an advisory hook would
# be a permission verdict, and this hook has no standing to give one.
jq -n --arg msg "$msg" \
  '{hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: $msg}}'
exit 0
