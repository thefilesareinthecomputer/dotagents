# SPEC-ANTIGRAVITY.md - Antigravity CLI station

Google's terminal agent, invoked as `agy`, and the successor to Gemini CLI. It is
a single compiled Go binary with no Node dependency, sharing its agent harness
with the Antigravity IDE so one configuration serves both. Consumer Gemini CLI
was retired on 2026-06-18, and Code Assist Standard and Enterprise are the only
tiers that keep it ([`SPEC-GEMINI.md`](../gemini/SPEC-GEMINI.md)).

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
    { "path": "<home>/.agents/skills" }
  ]
}
```

**The path must be absolute.** Observed on 1.3.3 (2026-10-14) through the
model's own report in print mode, since no listing command exists: with
`"~/.agents/skills"` a run asked to name its loaded skills without tools named
only the two built-ins; with the home folder spelled out it named 29 of this
repo's 32 skills, leaving out `agent-cc-configs-sync`, `harness-bench` and
`plugin-update` for a reason not yet checked. `$HOME` was not tried. Write the
file with the station's real home path; it is a station-local file and is never
committed.

That is preferable to symlinking `~/.gemini/config/skills` at this repo, because
it adds a path rather than claiming a directory Antigravity manages, and it
leaves room for device-local skills beside it. It is also the only place in these
specs where a harness offers a first-class way to point at an external tree.

**Verified on the laptop 2026-10-14:** `agy 1.3.3` at the first probe with
`harness_probe.py` in the `agent-cc-configs-sync` skill, and `1.3.5` at a second
probe the same evening, so the binary updates itself without being asked. The
probe's canary for this harness is the presence of `skills.json`. The file was
written that day with the absolute path and discovery was observed as the model's
self-report in print mode: asked to name its loaded skills without tools, it
listed 29 of this repo's skills beside the two built-ins it named
(`agy-customizations`, `antigravity-guide`). The customization
roots, elements and JSON schema above were read from the 1.1.11 binary's own
documentation strings on 2026-08-08 and still hold at 1.3.3 as far as the skills
entry goes. Google's web documentation gives the global skills path as
`~/.gemini/antigravity-cli/skills/` instead; on disk that directory holds only
`builtin/skills/`. **`agy inspect` is gone at 1.3.3**: the subcommands are
`agent`/`agents`, `changelog`, `help`, `install`, `mcp`, `models`, `plugin`,
`remote-control` and `update`, so a loaded-skills listing is now a print-mode
question rather than a command.

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

## Seeding

What this harness inherits natively from `~/.agents` and what has to be
installed. Shapes are defined once in
[`../SEEDING-SHAPES.md`](../SEEDING-SHAPES.md), and `seed.json` beside this file
is the machine-readable copy that `seed.py` reads.

| Element | Shape | Station path | Notes |
|---|---|---|---|
| Skills | `POINTER` | `~/.gemini/config/skills.json` | an `entries` item whose `path` is the absolute path of this repo's `skills/`; `~` is not expanded. The seed adds the entry when no entry names that path and leaves every other entry alone |
| Subagents | `N/A` | - | no subagent tree documented |
| Commands | `N/A` | - | a flat `.md` in a skills folder is a slash command; this repo uses the directory form only |

## Station config

Settings live under `~/.gemini/antigravity-cli/`, with MCP servers in
`~/.gemini/config/mcp_config.json`. The `~/.gemini/` home is inherited from
Gemini CLI, which Antigravity replaced; `~/.gemini/config/` is the customization
root and `~/.gemini/antigravity-cli/` the state folder. `agy inspect` was the
diagnostic when something did not load and no longer exists at 1.3.3; `agy
agents`, `agy mcp list` and `agy plugin list` cover their parts, and skills are
checked with a print-mode question (above). A one-shot importer migrates a legacy `~/.gemini/`
Gemini CLI setup, converting extensions into plugins and rewriting `settings.json`
into the new schema.

**The installer edits shell profiles.** `install.sh` appends
`export PATH="$HOME/.local/bin:$PATH"` to every profile it finds rather than only
the active shell's. On this machine on 2026-08-08 it wrote to `~/.zshrc`,
`~/.zprofile`, `~/.bash_profile`, `~/.profile` and `~/.config/fish/config.fish`,
each marked `# Added by Antigravity CLI installer`. The `--dir` flag is the only
documented option and does not suppress this. Expect to trim the duplicates by
hand after installing.

**Remote control (invariant 7).** `agy remote-control start` registers a
background daemon that pairs the CLI with a remote client, and `--remote-control`
does the same for one session. Neither has run on the laptop: on 2026-10-15,
`agy remote-control status` reported not running and no launch agent.
`antigravity-task` refuses `--remote-control` in its argv. The telemetry switch
is unverified and remains an open item: the 1.3.5 binary holds no
`usageStatisticsEnabled` string, so Gemini CLI's opt-out key may be ignored, and
the sign-in asks for Google telemetry scope.

Authentication is Google Sign-In on first run, cached in the system keyring.
The interactive session requires a TTY; print mode does not. At 1.3.3 the CLI
also takes `--effort low|medium|high|xhigh|max` and `--mode accept-edits|auto|plan`
(`--help`, 2026-10-14), and a headless run that needs a tool permission is
auto-denied with a message naming the `permissions.allow` rule to add.

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
