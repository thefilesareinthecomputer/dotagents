# PROJECTS/

**What it is:** where the knowledge base gets used, and the one tier that may be shared. Each subfolder is a project workspace, often a clone of that project's own repo, so this level holds nothing loose but this file and its CLAUDE.md pointer.

**What lives here:** one folder per project. When a project folder is a git clone with its own remote, it is the one surface this vault and the project's team both see; the vault's other tiers stay private to it.

**Shape inside a project:** a project is flat and does not repeat the vault's tier structure. The note contract still applies: frontmatter on every note, wikilinks for relationships, and one idea per heading so sections stay addressable.

**Fed by:** `KNOWLEDGE-BASE/` - projects draw on it. Durable learnings from a project become dated artifacts in `_RESEARCH/`.

## Standards

- Wikilinks between project files are path-qualified - projects share basenames.
- `raw/` originals stay unmodified; distillation happens alongside them.
- A project folder that is a shared repo reaches the team that pulls it. Review a diff before it goes out.
