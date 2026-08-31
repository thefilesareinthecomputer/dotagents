# SPEC-GEMINI.md - Gemini CLI station

Google's terminal agent. Notable here as the **only harness besides Claude Code
with all three trees**: skills, subagents and slash commands.

## Skills: nothing to install

Gemini CLI reads **`~/.agents/skills/`** as an alias for `~/.gemini/skills/`, and
within the user tier the `.agents` alias *takes precedence*. Cloning this repo to
`~/.agents` is the entire setup.

Discovery order, lowest to highest precedence:

1. built-in skills
2. extension skills
3. user: `~/.gemini/skills/` or **`~/.agents/skills/`**
4. workspace: `.gemini/skills/` or `.agents/skills/`

`/skills list` verifies discovery and `/skills reload` refreshes without a
restart. Workspace skills require the folder to be trusted (`/trust`); user-scope
skills are not subject to that.

**Not verified here.** Gemini CLI is not installed on this machine; the above is
from Google's documentation as of 2026-07-31. Note that `~/.gemini/` does now
exist, created by the Antigravity CLI installer on 2026-08-08, so its presence is
no longer evidence that Gemini CLI is installed. `~/.gemini/config/` and
`~/.gemini/antigravity-cli/` belong to `agy`; see
[`SPEC-ANTIGRAVITY.md`](../antigravity/SPEC-ANTIGRAVITY.md).

## Subagents and commands: the partial exception

This is the one harness where this repo's other two trees are not simply
irrelevant.

**Subagents are mechanically compatible but differently located.** Gemini reads
`~/.gemini/agents/*.md` and `.gemini/agents/*.md`, using the same
YAML-frontmatter-plus-markdown-body shape as `~/.claude/agents/*.md`, where the
body becomes the system prompt. Neither harness reads the other's path, so the
*content* ports while the location does not. `/agents` manages and rescans them.

**Commands do not port at all.** Gemini uses **TOML** at `~/.gemini/commands/`,
where only `prompt` is required, arguments are `{{args}}`, and shell execution is
`!{...}`. Subdirectories namespace the command with colons. This repo's commands
are markdown with `$ARGUMENTS`. Those are different artifacts, not one artifact at
two paths.

## Superseded for most tiers

The replacement warning recorded here on 2026-07-31 has resolved. **Consumer
Gemini CLI was retired on 2026-06-18** in favor of Antigravity CLI (`agy`); Code
Assist Standard and Enterprise are the only tiers that keep it. A one-shot
importer migrates a `~/.gemini/` setup across. Unless the account is on one of
those tiers, [`SPEC-ANTIGRAVITY.md`](../antigravity/SPEC-ANTIGRAVITY.md) is the station that
applies, and it needs a setup step this one did not.

## Models

Google's hosted models. Under `SPEC.md` invariant 6 that bounds this station to
**medium-stakes and hobby work**.

## Station config

Not adapted. Tracked with the goose and Codex station work in `tasks/plan.md`.
