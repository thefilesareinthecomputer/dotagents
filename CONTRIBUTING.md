# Contributing

These skills get symlinked into a live `~/.claude`, so a merged change reaches
real sessions immediately. Read [`AGENTS.md`](AGENTS.md) before your first one.

## Setup

```bash
git clone <this-repo> ~/.agents
# make ~/.claude/skills a real dir if it isn't already:
[ -L ~/.claude/skills ] && rm ~/.claude/skills   # removes the link only
mkdir -p ~/.claude/skills
bash ~/.agents/sync-skills.sh --dry-run          # preview
bash ~/.agents/sync-skills.sh
```

The sync script is idempotent and never overwrites a real local entry in
`~/.claude`. [`SPEC-CLAUDE-CODE.md`](specs/claude-code/SPEC-CLAUDE-CODE.md) covers the rest of the station.

## Branches and commits

Branch from `develop` and target it; `main` is fast-forwarded from `develop`.
Commits follow [Conventional Commits](https://www.conventionalcommits.org),
scoped to what you touched: `feat(docker):`, `fix(sync):`, `docs(readme):`. One
logical change per pull request. Never force-push a shared branch or rebase
shared history.

## Skills

A skill is `skills/<name>/SKILL.md` with YAML frontmatter carrying `name` and
`description`. Malformed frontmatter breaks discovery for the whole tree.

The `description` is the trigger contract, and it is the only text an agent sees
when deciding whether to load the skill. Name the situations it fires in.
Situation clauses beat keyword lists.

Anything mechanically checkable belongs in a stdlib script that exits non-zero
rather than in the prose. A checklist applied by the model that wrote the code is
the model grading its own homework.

Subagents are one `.md` under `agents/`, commands one `.md` under `commands/`.
Give a read-only subagent a read-only `tools:` allowlist. Prose telling it not to
write files will not stop it from writing files.

Update the skills catalog in the [README](README.md) when you add, rename, or
remove an entry.

## Verification

Say how you checked it. Per-skill suites live in `skills/<name>/tests/`, station
hooks in `tests/station-hooks/`. A new or reworded `description` needs a trigger
eval run through the skill-creator plugin's `run_eval.py`; report recall and
precision. Edits to `sync-skills.sh` need a `--dry-run` transcript.

## Style

No emojis, no em dashes, no secrets in a diff or a fixture. Match the surrounding
style and touch only what your change requires. Claims with a shelf life get a
verification date next to them.

Security reports go through a private advisory rather than an issue. See
[`SECURITY.md`](SECURITY.md).
