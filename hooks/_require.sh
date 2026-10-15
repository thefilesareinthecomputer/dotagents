#!/usr/bin/env bash
# Sourced by the PreToolUse guards that depend on external programs.
# require_deps NAME... denies the tool call when any named program is missing
# from PATH, so a guard fails closed instead of silently allowing. The JSON is
# built with printf because jq may be the missing program. Names come from the
# guard's own argument list, never from tool input, and a name with any
# character outside [A-Za-z0-9_.-] is skipped so the JSON stays well formed.
# A machine missing a station dependency (jq, perl, python3) is refused every
# call the guard covers until the dependency is installed; recovery is a
# package install, not an edit through the agent.
# Usage, first thing after the shebang comment, with a fallback deny in case
# this file itself cannot be sourced:
#   . "$(dirname "$0")/_require.sh" 2>/dev/null || { printf '%s\n' "$PREAMBLE_MISSING"; exit 0; }
#   require_deps jq perl

require_deps() {
  local missing="" dep
  for dep in "$@"; do
    case "$dep" in *[!A-Za-z0-9_.-]*) continue ;; esac
    command -v "$dep" >/dev/null 2>&1 || missing="$missing $dep"
  done
  [ -z "$missing" ] && return 0
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"hook dependency missing:%s. This guard cannot evaluate the call without it, so it refuses. Install the dependency on this machine, or run the command yourself."}}\n' "$missing"
  exit 0
}
