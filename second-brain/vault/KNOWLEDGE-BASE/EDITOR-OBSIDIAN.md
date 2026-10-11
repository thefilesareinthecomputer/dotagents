---
date-created: 2026-08-27
last-modified: 2026-08-27
status: canonical
tags:
  - second-brain
  - obsidian
  - editor
  - setup
---

# Obsidian

The vault is plain Obsidian-flavored markdown, so Obsidian is the natural hand-editing companion: open `vault/` as a vault and both tools work on the same files with no sync layer.

## Setup

1. Install Obsidian from https://obsidian.md.
2. Open `vault/` with "Open folder as vault".
3. In `brain config`, set the editor to `obsidian` - once the open-in-editor feature lands, the web UI's viewer hands files to Obsidian through its `obsidian://open` URI. (`system` and custom commands are the other options.)

## How the two coexist

- **Edit anywhere, the graph keeps up.** The knowledge-graph index detects vault drift and re-ingests on the next read, so a note edited in Obsidian is searchable in the app without a manual step. `b build` forces a full rebuild after bulk changes.
- **Wikilinks are shared vocabulary.** `[[Note]]` links, headings, frontmatter, and tags are what the engine indexes into sections and edges - the same structure Obsidian's own graph reads.
- **The lifecycle still applies to canon.** Obsidian edits anywhere in the vault are fine, but `KNOWLEDGE-BASE/` content is supposed to enter through the merge gate - see [[SECOND-BRAIN-KNOWLEDGE-LIFECYCLE]]. Working tiers (`_RESEARCH/`, `LEARNING/`, `PROJECTS/`) are yours to edit freely.
- **`.obsidian/` stays local.** Obsidian's workspace folder is editor state, not content; the engine ignores dot-directories and it should stay out of a public fork.

Back to [[HARNESS-INTEGRATION-OVERVIEW]].
