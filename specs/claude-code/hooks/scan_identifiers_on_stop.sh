#!/usr/bin/env bash
# Stop hook: sweep the guarded paths for project identifiers at the end of every session.
#
# The PreToolUse hook blocks new writes. It cannot see what was already on disk before it
# was installed, what another tool wrote, or what arrived through a git operation. This is
# the sweep that catches those, and it runs whether or not anyone remembers to ask.
#
# Advisory by design: it reports, it never blocks the session from ending. A Stop hook that
# refuses to stop is worse than the problem it guards.

set -uo pipefail

SCANNER="${IDENTIFIER_SCANNER:-.claude/tools/prepublish_scan.py}"

TARGETS=()
for p in .claude/skills .claude/tools .claude/agents .claude/commands .claude/hooks; do
  [ -d "$p" ] && TARGETS+=("$p")
done
# Nothing here that travels, so there is nothing to sweep and nothing to say.
[ ${#TARGETS[@]} -gt 0 ] || exit 0

# A missing scanner is reported, not passed over. This hook used to exit 0 here,
# which made an uninstalled sweep indistinguishable from a clean one - the guard
# reads as present in settings.json and does nothing. The message is bounded to
# repos that actually hold guarded directories, so it names a real gap rather
# than nagging on every stop.
if [ ! -f "$SCANNER" ]; then
  echo "IDENTIFIER SWEEP DID NOT RUN: no scanner at $SCANNER." >&2
  echo "This repo holds agent tooling that travels (${TARGETS[*]}), and nothing" >&2
  echo "checked it. Install the scanner, point IDENTIFIER_SCANNER at it, or drop" >&2
  echo "the Stop entry from settings.json - an inert guard is worse than none." >&2
  exit 0
fi

OUT="$(python3 "$SCANNER" "${TARGETS[@]}" 2>&1)"
CODE=$?

if [ "$CODE" -eq 1 ]; then
  echo "IDENTIFIER SWEEP: project identifiers are present in agent tooling." >&2
  echo "$OUT" | grep -E '^\s+\.claude' | head -20 >&2
  echo "" >&2
  echo "These files travel. Generalize each at the source, or move the content to" >&2
  echo "PROJECTS/ or tasks/ where identifiers belong." >&2
elif [ "$CODE" -eq 2 ]; then
  echo "IDENTIFIER SWEEP: the scan could not be trusted, so a clean result means nothing." >&2
  echo "$OUT" | tail -6 >&2
fi

exit 0
