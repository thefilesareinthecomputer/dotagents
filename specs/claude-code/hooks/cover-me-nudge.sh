#!/usr/bin/env bash
# PostToolUse - advisory only, NEVER blocks.
#
# Suggests `/cover-me` (a fresh-context supervisor review) at the two moments
# worth one: just after a hard-to-undo command, and after a long unreviewed
# stretch of tool calls. It only injects a line of context; the tool has already
# run and nothing is withheld.
#
# Deterministic by construction: no model call, no network, no transcript read.
# A hook is the only mid-run injection point the harness has and it must stay
# fast, so the decision is a regex and an integer.
#
# Fail-open by construction: every path exits 0. A missing jq, an unwritable
# state dir, or a parse error results in silence, never a block.
# Cheap by construction: one jq pass, one small state file, no subprocesses in
# the matching path.
#
# Tunable: COVER_ME_NUDGE_CALLS (default 45). Set high on purpose - a nudge that
# fires during ordinary work becomes noise and gets ignored.

set -u
threshold="${COVER_ME_NUDGE_CALLS:-45}"
# Calls that must pass after a nudge before a destructive command may nudge
# again. Stops a run of `migrations/` reads from repeating the same line.
cooldown=5

# No jq -> silent (exit 0 with no output is 'allow' to Claude Code).
command -v jq >/dev/null 2>&1 || exit 0

# One jq pass (this runs on every tool call): tab-join the three fields.
# @tsv escapes embedded tabs/newlines, so the payload stays on one line.
IFS=$'\t' read -r session tool cmd < <(
  printf '%s' "$(cat)" | jq -r '[.session_id, .tool_name, (.tool_input.command // "")] | @tsv' 2>/dev/null
)

# ---- counter state ----------------------------------------------------------
# Keyed by session id so concurrent sessions do not share a counter. The id is
# stripped to a safe charset; anything else cannot reach the path. State lives
# under the user's own home, never shared tmp, and a symlinked state file is
# refused rather than followed - both close a write-through in world-writable
# /tmp when TMPDIR is unset (launchd, cron, ssh non-login).
sid="${session//[^A-Za-z0-9._-]/}"
[ -n "$sid" ] || sid="nosession"
# Both vars can be unset in launchd/cron contexts; with neither there is no
# safe place for state, so stay silent rather than trip set -u and exit 1.
[ -n "${XDG_STATE_HOME:-}${HOME:-}" ] || exit 0
dir="${XDG_STATE_HOME:-${HOME:-}/.cache}/cover-me-nudge"
state="$dir/$sid"
[ -L "$dir" ] && exit 0
mkdir -p -m 700 "$dir" 2>/dev/null || exit 0
[ -L "$state" ] && exit 0

count=0; nudged=0
read -r count nudged 2>/dev/null < "$state" || true
case "$count" in ''|*[!0-9]*) count=0 ;; esac
case "$nudged" in ''|*[!0-9]*) nudged=0 ;; esac
count=$((count + 1))

# ---- triggers ---------------------------------------------------------------
# Literal \n and \t from @tsv become spaces so a multi-line command still has
# word boundaries. Builtin substitution, no subprocess.
cmd="${cmd//\\n/ }"
cmd="${cmd//\\t/ }"

destructive='(^|[^[:alnum:]_.-])rm[[:space:]]+-[a-z]*(rf|fr)|git[[:space:]]+push[^|;&]*--force|drop[[:space:]]+(table|database)|migrations/[^[:space:]]'

msg=""
shopt -s nocasematch 2>/dev/null || true
if [ "$tool" = "Bash" ] && [ -n "$cmd" ] && [[ $cmd =~ $destructive ]] \
   && { [ "$nudged" -eq 0 ] || [ "$count" -ge "$cooldown" ]; }; then
  msg="That command is hard to undo. If this is the mission-critical part, ask the user whether they want a /cover-me review before going further - do not spawn one unprompted."
elif [ "$count" -ge "$threshold" ]; then
  msg="$count tool calls since the last checkpoint. If this stretch is mission-critical or the context is getting long, offer the user a /cover-me review - do not spawn one unprompted."
fi
shopt -u nocasematch 2>/dev/null || true

# ---- persist, then speak at most once ---------------------------------------
if [ -n "$msg" ]; then
  printf '%s %s\n' 0 1 2>/dev/null > "$state" || true
  jq -n --arg msg "$msg" \
    '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $msg}}'
  exit 0
fi

printf '%s %s\n' "$count" "$nudged" 2>/dev/null > "$state" || true
exit 0
