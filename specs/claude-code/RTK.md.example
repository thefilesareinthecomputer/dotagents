# RTK - Rust Token Killer

**Usage**: Token-optimized CLI proxy (60-90% savings on dev operations)

## Meta Commands (always use rtk directly)

```bash
rtk gain              # Show token savings analytics
rtk gain --history    # Show command usage history with savings
rtk discover          # Analyze Claude Code history for missed opportunities
rtk proxy <cmd>       # Execute raw command without filtering (for debugging)
```

## Installation Verification

```bash
rtk --version         # Should show: rtk X.Y.Z
rtk gain              # Should work (not "command not found")
which rtk             # Verify correct binary
```

⚠️ **Name collision**: If `rtk gain` fails, you may have reachingforthejack/rtk (Rust Type Kit) installed instead.

## Hook-Based Usage

All other commands are automatically rewritten by the Claude Code hook -
except `grep`, which is hook-excluded in rtk's `config.toml` (its filter can
drop the actual match lines).
Example: `git status` → `rtk git status` (transparent, 0 tokens overhead)

## Commands Worth Naming Directly

The hook handles the common case. Reach for these by name when output is noisy;
`rtk --help` is the authoritative list (~65 subcommands as of 0.43.0).

```bash
rtk err <cmd>         # run anything, print only errors and warnings
rtk test <cmd>        # run tests, print only failures
rtk summary <cmd>     # heuristic summary of a long-running command
rtk json <file>       # compact JSON; --keys-only collapses to shape
rtk diff              # only changed lines
rtk log               # filtered, deduplicated log output
rtk deps              # dependency summary
rtk find -name '*.py' # compact search (takes native find flags)
rtk cc-economics      # Claude Code spend vs rtk savings
```

`rtk err` and `rtk test` carry the largest savings, because they discard the
passing output entirely.

Dedicated filters also exist per family: VCS and cloud (git gh glab aws psql),
build (cargo npm npx pnpm dotnet go gradlew mvn pip), test runners
(jest vitest pytest rspec playwright), lint and types
(lint format prettier ruff rubocop mypy tsc golangci-lint), containers
(docker kubectl oc).

**Not for file content.** Reading a file goes through the Read tool, never
`rtk read` - the harness tools carry diff review, permission guards, file-state
tracking and checkpointing that a shell read bypasses.