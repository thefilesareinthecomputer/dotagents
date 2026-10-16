# SPEC-GEMINI.md - Gemini CLI station

**Retired.** Consumer Gemini CLI was retired on 2026-06-18 (doc-derived, from
Google's announcement as read on 2026-08-08). Antigravity CLI (`agy`) is its
successor, and [`SPEC-ANTIGRAVITY.md`](../antigravity/SPEC-ANTIGRAVITY.md) is
the live station spec. The `gemini` npm package was removed from the laptop on
2026-10-15 (it had never been run), and `~/.gemini/` belongs to `agy`, which
inherited the folder. The rest of this spec describes the Gemini CLI station
for the Code Assist Standard and Enterprise tiers, which keep the product.

Google's terminal agent. Notable here as one of the **two harnesses besides
Claude Code with all three trees** (Cursor is the other): skills, subagents and
slash commands.

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

**Not verified here.** Gemini CLI was never run or set up on either station,
and the laptop's npm install was removed on 2026-10-15. The skill discovery
described in this section comes from Google's documentation as of 2026-07-31.
`~/.gemini/` now exists, created by the Antigravity CLI installer on 2026-08-08,
so its presence is no longer evidence that Gemini CLI is installed. `~/.gemini/config/` and
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
