# Vault Probe: Per-Vault Customization Procedure

Run this **read-only** sweep before authoring in any vault. The output is an in-memory
**vault profile** you present to the user for confirmation. All paths are relative to the
vault root (the directory containing `.obsidian/`). Fail soft: a missing file/key means
"use the documented default", not an error.

## Step 1: Read core config

| File | Read for | Authoring impact |
|------|----------|------------------|
| `.obsidian/app.json` | `useMarkdownLinks`, `newLinkFormat`, `attachmentFolderPath`, `alwaysUpdateLinks`, `strictLineBreaks`, `showFrontmatter` | Link style + path depth + attachment location + paragraph spacing |
| `.obsidian/core-plugins.json` (+ `core-plugins-migration.json`) | Which core plugins are on (Templates, Daily notes, Bases, Properties) | Whether to use templates/daily-note format/bases |
| `.obsidian/community-plugins.json` | Array of enabled community plugin IDs | Gate Dataview/Tasks/Templater syntax |
| `.obsidian/daily-notes.json` | `format`, `folder`, `template` | Daily-note filename pattern + location |
| `.obsidian/templates.json` and/or `.obsidian/plugins/templater-obsidian/data.json` | Template folder(s) | Note skeletons to mirror |

**Defaults when a key/file is absent** (keys only appear once changed from default):
- `useMarkdownLinks` → `false` (use `[[wikilinks]]`)
- `newLinkFormat` → `shortest`
- `strictLineBreaks` → `false`
- `attachmentFolderPath` → vault root

### Key meanings
- **`useMarkdownLinks`**: `false` → write `[[wikilinks]]`. `true` → write `[Title](path.md)`.
  The single most important link decision.
- **`newLinkFormat`**: `shortest` (bare filename when unambiguous), `relative` (path from
  current note), `absolute` (path from vault root). With a duplicate basename, root/absolute
  wins over proximity, always disambiguate with a path when two notes share a name.
- **`strictLineBreaks`**: `true` = CommonMark (single newline merges lines, two trailing
  spaces = `<br>`). `false` = every newline is a hard break (Obsidian-only, non-portable).

## Step 2: Sample existing notes

Sample ~15-30 most-recently-modified `.md` files, excluding `.obsidian/**` and `.trash/**`.
From the sample, derive:

- **Property schema**: union of frontmatter keys + inferred types + list-vs-scalar usage
  per key. Reuse these keys/casing rather than inventing new ones.
- **Tag taxonomy**: harvest tags from frontmatter `tags:` lists **and** body `#tags`.
  Record nesting (`area/projects`), casing, and whether the vault tags in frontmatter, body,
  or both. Place new tags into the existing hierarchy.
- **Link convention**: wikilink vs `[]()`; bare vs path-bearing; alias usage. Reconcile with
  `app.json` (notes override stale config if they disagree, flag the conflict).
- **Inline metadata**: detect Dataview `key:: value` fields, Tasks lines, callout types in use.
- **Naming + placement**: filename casing (Title Case / kebab-case / date), folder-per-topic
  vs flat, where notes of each type live.

## Step 3: Read 1-2 template files

From the folders found in Step 1, read a template or two to learn the canonical note skeleton
(property order, default callouts, section headers). Mirror this for new notes of that type.

## Step 4: Synthesize the vault profile

Build:
```
{
  linkStyle:        "wikilink" | "markdown",
  newLinkFormat:    "shortest" | "relative" | "absolute",
  attachmentPath:   "<dir>",
  strictLineBreaks: true | false,
  propertySchema:   { key: type, ... },
  tagTaxonomy:      [ "area/...", ... ],
  enabledPlugins:   [ "dataview", "obsidian-tasks-plugin", ... ],
  dailyNoteFormat:  { format, folder, template },
  templatePaths:    [ "<dir>", ... ]
}
```

## Step 5: Present + confirm (mandatory handshake)

Show the user the profile, your **recommended authoring conventions**, and any ambiguities
or config-vs-reality conflicts. Ask for approval/corrections. **Do not author until confirmed.**

### Suggested probe commands
```
# config
cat .obsidian/app.json .obsidian/community-plugins.json .obsidian/daily-notes.json 2>/dev/null
# note sample (recent, excluding config/trash): adjust to available tools
ls -t **/*.md | grep -v '^\.obsidian/' | grep -v '^\.trash/' | head -30
```
Use the harness's Read/Grep/Glob tools rather than shell where possible. Globs:
`.obsidian/*.json`, `.obsidian/plugins/*/data.json`, `**/*.md` (sampled).
