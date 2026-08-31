# Plugin-Specific Syntax (gated on detection)

Only emit this syntax when the corresponding plugin is **enabled** (see
`.obsidian/community-plugins.json` / `core-plugins.json`) **and** the vault already uses it.
Otherwise stick to plain frontmatter + standard tasks.

## Dataview (`dataview`)
Inline fields and query blocks.

```markdown
Full-line field:  Author:: Brandon Sanderson
Bracketed (mid-line / multiple / on tasks):  Rating [rating:: 9] and [mood:: great]
Hidden key (parenthesis):  (key:: value)
```
Key normalization: `[Author Name:: X]` → `file.authorname` / `file["Author Name"]`.

Query blocks:
~~~
```dataview
TABLE rating, author FROM #books WHERE rating > 7 SORT rating DESC
```

```dataviewjs
dv.table(["Name"], dv.pages("#books").map(p => [p.file.link]))
```
~~~

## Tasks (`obsidian-tasks-plugin`)
Checkbox list items with metadata. **One format per vault** (configurable):

Emoji format:
```markdown
- [ ] Write report 📅 2026-06-25 🔁 every week ⏫
```
Markers: ➕ created · 🛫 start · ⏳ scheduled · 📅 due · ✅ done · ❌ cancelled.
Priorities: 🔺 highest · ⏫ high · 🔼 medium · 🔽 low · ⏬ lowest.

Dataview format:
```markdown
- [ ] Write report [due:: 2026-06-25] [priority:: high]
```
Tasks reads tags from the task line, not from frontmatter.

## Templater (`templater-obsidian`)
Command syntax (don't execute, emit literally only when authoring templates):
```markdown
<% tp.date.now("YYYY-MM-DD") %>
<%* if (tp.file.title.startsWith("Untitled")) { %>...<%* } %>
<% tp.file.cursor() %>
```

## Excalidraw / Kanban
`.excalidraw.md` and Kanban board files have special structured markdown, **do not
hand-author**; embed Excalidraw drawings with `![[Drawing.excalidraw]]`.

## Bases (native core, 1.9+)
`.base` files are open YAML. Top-level keys: `filters`, `formulas`, `properties`,
`summaries`, `views`. Embed via `![[Name.base]]`.

```yaml
filters:
  and:
    - file.hasTag("project")
    - 'status != "done"'
formulas:
  ppu: "(price / age).toFixed(2)"
properties:
  status:
    displayName: Status
views:
  - type: table
    name: "Open projects"
    order:
      - file.name
      - note.status
```
- No `FROM`/source, defaults to the whole vault; narrow with `filters`.
- Functions: `file.hasTag(...)`, `file.inFolder(...)`, `file.hasLink(...)`; date arithmetic
  (`now() + "1 day"`); JS-like operators. `this` references the embedding/active file.
- View types: `table`, `cards`, `list`.

Bases syntax was overhauled in mid-2025, treat the above as current to ~1.9.10 and verify
against the live Bases syntax docs for newer builds.
