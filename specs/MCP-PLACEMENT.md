# MCP placement - where a server goes, and whether it goes anywhere

An MCP server is a tool-execution surface, so registering one is a permission decision rather than an install.
This file carries the position every station spec's MCP row defers to.
The seeding vocabulary itself is in [`SEEDING-SHAPES.md`](SEEDING-SHAPES.md).

## The parties, and where policy can live

The **host** is the application a human runs.
It holds the permissions, decides which servers exist, and is the only party that can enforce anything.
A **client** is a connector inside the host, one per server, created by the host and bonded to that server for its lifetime.
A **server** is a separate program exposing tools, either a local child process or a remote web service.

The model is not one of the three.
The host talks to it over a separate channel and decides which of its tool-call requests become MCP messages, which is why every control in this repo lands in a harness config file and never in a server.

## Scope is the placement decision

A registered server puts its tool names into every session for the life of the registration, so the question is never only whether a server is trustworthy but where it is allowed to exist.

- **Project scope is the default.**
  A server declared in the repository that needs it costs nothing in any other repository.
- **User scope has to be argued for** the same way MCP itself does, and the argument is that essentially every repository needs the capability.
- **Not registered is the third option** and usually the right one, because a CLI in a shell costs nothing until it is invoked.

Deferred schemas are a harness feature, not a protocol guarantee.
Claude Code sends tool names at session start and loads schemas on demand, while the protocol's own `tools/list` returns full schemas for everything.
No spec may assume a server is context-cheap on a harness where that has not been observed.

## When a server beats a CLI

The standing rule is CLI-first, stated in the `ai-engineering` skill's `engineering-principles.md` section 11.
A CLI has no protocol surface, no per-session context cost, composes with everything else in the shell, and runs inside whatever bounds the shell.
Four cases clear that bar, and a candidate that matches none of them is not adopted:

1. **The client has no shell**, such as a desktop or web client.
2. **The capability needs session state across calls.**
   Driving a live browser is the honest example, since page state persists between calls and a CLI would have to reinvent a session protocol.
3. **A thin adapter to a service that already exists**, rather than standing up a second copy of it.
4. **The auth belongs to the user rather than the machine**, which is a real distinction from a CLI reading a key out of the environment.

"It exists", "it is official" and "it would be convenient" are not on the list.

## The failure mode: servers that arrive without a decision

A harness can present servers that no station config declares, and three arrival routes were confirmed by probe 2026-08-29:

| Route | Where it is configured | Whether station config can undo it |
|---|---|---|
| Account-level connectors, bound to the signed-in account rather than the machine | nowhere on disk; they list at runtime | no - removed in the provider's own account settings, once per account |
| Servers written by a desktop application's installer into the CLI's config file | the harness config file, under keys the installer chose | yes, by editing that file |
| Servers built into the CLI itself | not a file; enabled and scoped by invocation flags | no - only the flags bound it |

Two of the three routes are outside the file a spec would name.
The rule this produces: **an MCP surface is not bounded by the harness config a spec knows about**, so an inventory is taken by asking the harness what it has - `claude mcp list`, `codex mcp list`, `cursor-agent mcp list` - and never by reading the config file alone.
Run that inventory before trusting any table here, including this one.

Revoking an OAuth grant and removing a connector are different operations.
A revoked connector holds no token but still occupies context in every session, so only removal reclaims it.

## Where each harness keeps MCP config

Verified by probe 2026-08-29.

| Harness | Location | Management surface |
|---|---|---|
| Claude Code | `~/.claude.json` (`mcpServers`), project `.mcp.json`, plus account connectors that no local file declares | `claude mcp add/remove/list` |
| Codex | `~/.codex/config.toml`, `[mcp_servers.<name>]` tables | `codex mcp` |
| Cursor | `~/.cursor/mcp.json` or project `.cursor/mcp.json`, neither created by default | `cursor-agent mcp`, with `enable`/`disable` against a local approved list |
| Copilot | `~/.copilot/mcp-config.json`, not created by default, plus `--additional-mcp-config` per invocation | flags only |

`cursor-agent --approve-mcps` auto-approves every server and is never seeded, under the rule that widening values move only in the restrictive direction.

## Playwright is the only server this repo standardizes

Its entry, flags, pinning discipline and permission posture are in [`claude-code/SPEC-CLAUDE-CODE.md`](claude-code/SPEC-CLAUDE-CODE.md) section 3.2.
It qualifies under case 2 above and nothing else in the tree currently qualifies at all.

It is seeded to Claude Code only.
The reason is not that the other harnesses cannot run it but that the posture making it safe there does not exist on them: `mcp__playwright__browser_run_code_unsafe` is denied by name in `settings.json`, and no `mcp__playwright__*` entry is ever allowed, so the dangerous half of the default capability set is unreachable while the rest keeps prompting.
Codex has no persistent per-tool allow or deny list, Copilot's grants ride each spawn, and Cursor's CLI permissions have not been probed for MCP tool names.
Seeding a browser-driving server onto a harness that cannot deny its arbitrary-code tool would widen reach in the one direction seeding is never allowed to move.
Those rows stay `N/A` until a probe shows a per-tool deny that actually enforces.
