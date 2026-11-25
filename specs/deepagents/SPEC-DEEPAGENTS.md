# SPEC-DEEPAGENTS.md - deepagents station

LangChain's opinionated harness over `create_agent`/LangGraph. MIT, Python, with a
JS twin publishing to npm as `deepagents`.

**This is a wiring spec, not a station spec.** The others describe what to install
on a machine. deepagents is a library, so there is no config directory to seed and
no path it watches: skills are passed in code, per agent, at construction time.

## Skills: passed as arguments, not discovered

There is no home directory scan. `create_deep_agent` takes a `skills` argument,
a list of path strings **relative to the backend's root**:

```python
import os
from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend

agent = create_deep_agent(
    model="anthropic:claude-sonnet-5",
    backend=FilesystemBackend(root_dir=os.path.expanduser("~/.agents")),
    skills=["skills/"],
)
```

`SkillsMiddleware` is added automatically when `skills` is passed. It reads skill
files through the backend's filesystem tools, so a backend is required; with the
default `StateBackend` the files are supplied through `invoke(files={...})`
instead of read from disk.

Sources load in order and a later source wins a name collision, which is the
intended way to layer base then user then project skills.

Subagents take their own `skills` argument. The general-purpose subagent inherits
from `create_deep_agent`.

## Verification status

**Not verified here.** deepagents is not installed on this machine and the snippet
above is written from LangChain's documentation as of 2026-07-31, not from a run.
Confirm before relying on it.

## What does not carry over

Only `skills/`. This repo's `agents/` and `commands/` trees target Claude Code:
deepagents has its own subagent model and no slash-command concept, so neither is
read.

Two further gaps specific to this harness: skills here that reference *other*
skills by name assume a harness that resolves those names, and Claude Code
frontmatter extensions (`disable-model-invocation`, `context`, `model`, `effort`)
are no-ops. A skill still works if those are stripped, which is the house rule, but
its routing lines will point at nothing.

`SkillsMiddleware` lives in the `deepagents` package, not core LangChain, so plain
`create_agent`/LangGraph has no skills support without importing it or
implementing discovery and loading directly.

## The `deepagents-code` CLI

The bundled CLI does scan directories, with this precedence lowest to highest:
`<package>/built_in_skills/`, `.deepagents/skills/`, `.agents/skills/`,
`~/.claude/skills/` (experimental), `.claude/skills/` (experimental). Note that is
**project-level `.agents/skills/`**, not `~/.agents/skills/`, so this repo is not
picked up globally there.

## Constraints

- Skill `name`: 64 chars max, lowercase alphanumeric and hyphens, must match the
  directory name. `description`: 1024 chars max. `SKILL.md`: 10MB ceiling.
- **Pin the version.** deepagents is pre-1.0 and ships breaking changes at minor
  versions; 0.7.0 removed `read_file`'s line-number gutter and changed empty
  `ls`/`glob` output. An unpinned install will not stay compatible.
- Model-agnostic in claim, Anthropic-shaped in practice: prompt caching is
  Anthropic/Bedrock, and the JS default model is Claude.

## Models

Whatever the constructing code passes. `SPEC.md` invariant 6 still binds: work
that matters runs on Anthropic or a genuinely local model.

## Architecture

Not researched in the 2026-11-25 pass. Only facts this spec already states are listed.
deepagents was never installed here, so nothing is **observed**.
The **docs** facts come from LangChain's documentation as of 2026-07-31; this spec records no URL.

1. **Loop:** **unknown - not yet researched**.
2. **Tools:** **docs** - `SkillsMiddleware` reads skill files through the backend's filesystem tools. Parallelism and the tool list: **unknown - not yet researched**.
3. **Permissions:** **unknown - not yet researched**.
4. **Context:** **unknown - not yet researched**.
5. **Cache:** **docs** - prompt caching is Anthropic and Bedrock only. Marker placement: **unknown - not yet researched**.
6. **Sessions:** **unknown - not yet researched**.
7. **Errors:** **unknown - not yet researched**.
8. **Rules files:** **unknown - not yet researched**. Skill sources are covered in the `deepagents-code` section.
9. **Front ends:** **docs** - a bundled `deepagents-code` CLI exists. Event stream, headless mode and protocols: **unknown - not yet researched**.
10. **Subagents:** **docs** - subagents take their own `skills` argument, and the general-purpose subagent inherits from `create_deep_agent`. Isolation and limits: **unknown - not yet researched**.
