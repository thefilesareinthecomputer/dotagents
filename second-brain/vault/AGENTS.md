# The vault

**What it is:** a markdown knowledge vault in a tiered layout. The app indexes it into a knowledge graph, searches it and chats over it; agents write to it with their own tools under their own permissions. The tiers are a convention the graph colors by, not a mechanism this app runs.

**What lives here:** eight tier folders, each with its own AGENTS.md stating what belongs in it and the standards its notes keep.

**The tiers:** KNOWLEDGE-BASE (settled notes), _RESEARCH (dated research pending review), LEARNING (study records), PROJECTS (workspaces that draw on the knowledge base), _USER (a personal ledger), _NOTEBOOKLM (study packs), _TEMPLATES (note scaffolding), __archive (everything superseded).

## Standards

- Frontmatter on every note: `date-created`, `last-modified`, `status`, `tags`.
- Wikilinks for every relationship; path-qualify when a basename exists in more than one folder.
- One idea per heading - the graph addresses sections.
- Nothing is deleted; supersede into `__archive/`.
- `CLAUDE.md` files are one-line pointers to their `AGENTS.md`, excluded from the graph.
