# Properties (Frontmatter) Reference

Properties are YAML frontmatter at the very start of a note.

```yaml
---
title: My Note Title
created: 2026-06-25
due: 2026-07-01T14:30:00
tags:
  - area/projects
  - reference
aliases:
  - My Note
  - "My Note (2024)"
cssclasses:
  - wide-page
status: in-progress
rating: 4.5
completed: false
related: "[[Other Note]]"
---
```

## Strict rules
- Must begin on **line 1**: `---`, valid YAML, closed by `---`. Anything before it (even a
  blank line) makes Obsidian treat it as body text, not frontmatter.
- Each property **name must be unique** within a note.
- **Markdown is NOT rendered** inside text properties.
- **Internal links must be quoted:** `related: "[[Other Note]]"`, unquoted brackets break YAML.
- Quote any scalar containing a colon, `#`, or leading special punctuation.
- Dates: prefer ISO `YYYY-MM-DD` and datetime `YYYY-MM-DDTHH:MM:SS` for reliable sorting.

## Property types (auto-inferred since 1.4.2)
| Type | Example |
|------|---------|
| Text | `title: My Title` |
| Number | `rating: 4.5` |
| Checkbox | `completed: true` |
| Date | `created: 2026-06-25` |
| Date & time | `due: 2026-06-25T14:30:00` |
| List | `tags: [one, two]` or a YAML block list |
| Links | `related: "[[Other Note]]"` |

## Reserved / default keys: PLURAL LISTS ONLY (1.9 breaking change)
- `tags`: note tags (searchable, shown in graph view). Values lowercased; leading `#` stripped.
- `aliases`: alternative names (used in link suggestions).
- `cssclasses`: CSS classes applied to the note in reading/editing view.

**Obsidian 1.9 removed the singular forms** `tag` / `alias` / `cssclass` (deprecated since
1.4). Always emit the plural list forms, or properties may silently fail to render.

```yaml
# correct (1.9+)
tags:
  - projects
aliases:
  - MN
cssclasses:
  - wide-page

# WRONG: removed in 1.9
tag: projects
alias: MN
cssclass: wide-page
```

## Tags (in frontmatter and body)
Body: `#tag`, `#nested/tag`, `#tag-with-dashes`, `#tag_with_underscores`.
Frontmatter `tags:` list: no `#` prefix.

Allowed characters: letters (any language), numbers (**not** the first char, `#1984` is
invalid, `#y1984` is valid), `_`, `-`, `/` (nesting). No spaces. Searching a parent tag
(`#area`) matches all nested descendants (`#area/projects`).
