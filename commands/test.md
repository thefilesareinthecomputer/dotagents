---
description: Run the TDD workflow - write failing tests, implement, verify; for bugs use the Prove-It pattern. Defers to agent-skills test-driven-development when that plugin is installed.
---

Write the failing test first, implement to green, then verify. For a bug, write
the test that reproduces it before touching the fix (Prove-It): a fix with no
failing test behind it is a guess that happened to stop the symptom.

Cover the levels that apply: unit for the pure logic and its edge inputs,
integration for the parts that meet something real, end to end through the
actual entry point a user drives. Anything that regenerates a file gets an
idempotence assertion, because skipping that level is how a suite passes while
the command itself is broken.

When a test fails, decide which side encodes the mistake before editing either.
A test asserting the wrong expectation gets fixed in the test; a defect gets
fixed in the code. Say which one it was when reporting.

If the `agent-skills:test-driven-development` skill is installed, invoke it and
follow its fuller procedure. This command stands on its own without it.

$ARGUMENTS
