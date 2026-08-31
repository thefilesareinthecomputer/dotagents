# SPEC-ANTIGRAVITY.md - Antigravity CLI station

Google's terminal agent, invoked as `agy`, and the successor to Gemini CLI. A
single compiled Go binary with no Node dependency, sharing its agent harness with
the Antigravity IDE so one configuration serves both. It resolves the currency
warning in [`SPEC-GEMINI.md`](../gemini/SPEC-GEMINI.md): consumer Gemini CLI was retired on
2026-06-18, and Code Assist Standard and Enterprise are the only tiers that keep
it.

## Skills: this one needs a setup step

Antigravity is **the second harness after Claude Code that does not find this
repo on its own**. It reads `.agents/` as a project directory but not
`~/.agents/` as a global one, so a machine needs one small file before the skills
here are available outside a repository.

Customizations are discovered from two roots:

| Root | Path |
|---|---|
| Global | `~/.gemini/config/` |
| Project | `.agents/` at the workspace root, also accepting `.agent/`, `_agents/`, `_agent/` |

Within either root the elements are the same:

| Element | Location relative to the root |
|---|---|
| Skills | `skills/<skill_name>/` |
| Rules | `rules/*.md`, or a standalone `GEMINI.md` or `AGENTS.md` |
| Plugins | `plugins/<plugin_name>/` |

The supported way to register customizations kept outside those defaults is a
JSON pointer file in the root: `skills.json` for skills, `plugins.json` for
plugins. Both take the same schema, an `entries` array of paths to scan and an
`inherits` array of other configs to pull in, each accepting `include_only` and
`exclude` regex filters. So the whole setup for this station is
`~/.gemini/config/skills.json`:

```json
{
  "entries": [
    { "path": "~/.agents/skills" }
  ]
}
```

That is preferable to symlinking `~/.gemini/config/skills` at this repo, because
it adds a path rather than claiming a directory Antigravity manages, and it
leaves room for device-local skills beside it. It is also the only place in these
specs where a harness offers a first-class way to point at an external tree.

**Partly verified.** `agy` 1.1.11 is installed on this machine and
`~/.gemini/config/` exists with `config.json` and `mcp_config.json`, so the
global root is confirmed; the customization roots, elements and JSON schema above
are quoted from the shipped binary's own documentation strings, read on
**2026-08-08**. The `skills.json` file has not been written and skill discovery
has not been observed. Google's web documentation gives the global skills path as
`~/.gemini/antigravity-cli/skills/` instead, which conflicts with the binary; on
disk that directory holds only `builtin/skills/` with Antigravity's three
built-ins (`agy-customizations`, `permissioned-github`, `antigravity_guide`).
Resolve it with `agy inspect`, which lists loaded config files, available skills,
plugins, hooks and MCP servers, before relying on either path.

## What does not carry over

Subagents are `.agents/agents/<name>/agent.md`, a directory-per-agent shape that
does not match this repo's flat `agents/*.md`, and `/agents` lists them in
session. Commands are not read from `~/.agents/commands/`; Antigravity compiles a
markdown skill into a slash command instead, which is the same portable route the
other specs name.

Both skill forms coexist: a flat `.md` file in a `skills/` directory becomes a
slash command, while a `<name>/SKILL.md` directory is the richer package form
with `scripts/` and references. This repo only uses the directory form, which is
the one that carries assets.

## Station config

Settings live under `~/.gemini/antigravity-cli/`, with MCP servers in
`~/.gemini/config/mcp_config.json`. `agy inspect` is the diagnostic when
something is not loading. A one-shot importer migrates a legacy `~/.gemini/`
Gemini CLI setup, converting extensions into plugins and rewriting `settings.json`
into the new schema.

**The installer edits shell profiles.** `install.sh` appends
`export PATH="$HOME/.local/bin:$PATH"` to every profile it finds rather than only
the active shell's. On this machine on 2026-08-08 it wrote to `~/.zshrc`,
`~/.zprofile`, `~/.bash_profile`, `~/.profile` and `~/.config/fish/config.fish`,
each marked `# Added by Antigravity CLI installer`. The `--dir` flag is the only
documented option and does not suppress this. Expect to trim the duplicates by
hand after installing.

Authentication is Google Sign-In on first run, cached in the system keyring.
`agy inspect` and the interactive session both require a TTY.

**Headless mode exists** - the earlier claim that nothing runs under a
non-interactive shell is superseded. Observed on this machine's 1.1.11 binary
on 2026-08-29: `--help` lists `-p`/`--print` (single non-interactive prompt),
`--output-format text|json|stream-json`, `--json-schema`, `--print-timeout`
(default 5m), `--continue`/`-c` and `--conversation <id>` resume,
`--sandbox`, `--mode accept-edits|plan`, and `--dangerously-skip-permissions`.
An unauthenticated `agy -p` run errors cleanly with a login URL instead of
hanging, and the OAuth request it prints asks for `cloud-platform`, identity,
and Google telemetry scopes only - no Gmail, Calendar, or Drive scopes. The
v1.1.22 docs build (antigravity.google/docs/cli/headless, read 2026-08-29)
documents the same flags plus `--input-format stream-json` for multi-turn.
Doc-derived and unprobed here: the `permissions.allow`/`deny` model in
`settings.json` (`command()` / `read_file()` patterns, Deny > Ask > Allow),
and an open upstream report (antigravity-cli issue #548, status unverified)
that headless mode ignores `permissions.allow` and stalls - run the canary
probe pair headless after sign-in before trusting either claim.

## Models

Google's hosted Gemini models. `SPEC.md` invariant 6 bounds this station to
**medium-stakes and hobby work**.
