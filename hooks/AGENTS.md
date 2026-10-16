# Hooks folder rules

Every script here is seeded to every station and runs under that station's tools, not this one's.

- **Regexes stay plain POSIX ERE plus `\b`, and a distinctive multi-word phrase beats a clever construct.**
  The Bash tool's `grep` is ugrep, a script started from it finds BSD grep, and a seeded hook meets BSD or GNU grep on the next machine.
  An unsupported construct fails by not matching, so the hook exits 0 and looks healthy while detecting nothing.
  Check `grep --version` before concluding that a matching bug is in the pattern.
- **A script is seeded only when `manifest.json` names it**, with its bindings; a companion file (a preamble, a word list, an example list) is copied without a binding.
  Scripts that enforce rules about Claude Code itself live in `specs/claude-code/hooks/` under the same rules.
- **Hook input is harness-specific.** A script reads it through `_input.py` or is marked in the manifest as tested for one harness only; it is never wired into a harness it has no test for.
- **An advisory hook returns context, never a permission decision.**
  A PreToolUse `allow` is a verdict the harness acts on, so a hook that only nudges emits `additionalContext` alone.
- **Payload text never passes through a shell string operation.**
  A bash `${var//...}` over the incoming text is quadratic in its size, which is how one hook ran for hours on a large write while the harness's 5-second budget silently skipped it.
  Text goes from `jq` straight into the matching command, or the hook is Python; its suite holds a 300 KB write under 2 seconds.
