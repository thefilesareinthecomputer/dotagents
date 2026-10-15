# tests/

This directory is for tests that don't belong to any single skill - station-wide
hooks, cross-cutting behavior, and other infrastructure shared across `~/.agents`.

Tests for an individual skill live inside that skill's own directory
(`skills/<name>/tests/`), next to the code they cover, and travel with it.
Nothing skill-specific belongs here.

Current contents:
- `station-hooks/` - tests for the PreToolUse/SessionStart hooks seeded onto
  each machine per [`SPEC-CLAUDE-CODE.md`](../specs/claude-code/SPEC-CLAUDE-CODE.md) (e.g. `guard-rm.sh`,
  `deny-bash-file-writes.sh`), not owned by any one skill. The cross-harness
  scripts live in the repository's `hooks/`, whose own `tests/` covers the
  shared input reader against captured hook events.

  Each suite runs against the repository copy by default - `hooks/<script>` or
  `specs/claude-code/hooks/<script>`, resolved from the test file's own location -
  so a fresh clone with no station hooks installed passes, and a hook change is
  tested where it is written. To test a station's installed copy instead, set
  `HOOK_UNDER_TEST=~/.claude/hooks/<script>` (`PRE_UNDER_TEST` and
  `POST_UNDER_TEST` for the no-meta-commentary pair). Run every suite with
  `for t in tests/station-hooks/test-*; do case $t in *.sh) bash "$t";; *.py) python3 "$t";; esac; done`.
