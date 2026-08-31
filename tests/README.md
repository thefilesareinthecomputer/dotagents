# tests/

This directory is for tests that don't belong to any single skill - station-wide
hooks, cross-cutting behavior, and other infrastructure shared across `~/.agents`.

Tests for an individual skill live inside that skill's own directory
(`skills/<name>/tests/`), next to the code they cover, and travel with it.
Nothing skill-specific belongs here.

Current contents:
- `station-hooks/` - tests for the PreToolUse/SessionStart hooks seeded onto
  each machine per [`SPEC-CLAUDE-CODE.md`](../specs/claude-code/SPEC-CLAUDE-CODE.md) (e.g. `guard-rm.sh`,
  `deny-bash-file-writes.sh`), not owned by any one skill.
