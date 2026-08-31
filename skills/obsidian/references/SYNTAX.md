# Basic Markdown Syntax (Obsidian)

Obsidian uses CommonMark + GitHub-flavored extensions. This file is the full basic reference;
Obsidian-specific syntax lives in the other reference files.

## Headings
```markdown
# H1
## H2
### H3
#### H4
##### H5
###### H6
```
Setext style (`===` / `---` underline) also works. **No heading IDs** are supported.

## Text formatting
| Style | Syntax |
|-------|--------|
| Bold | `**text**` or `__text__` |
| Italic | `*text*` or `_text_` |
| Bold + italic | `***text***` |
| Strikethrough | `~~text~~` |
| Highlight | `==text==` |
| Underline | none native, use `<u>text</u>` |
| Sub / superscript | none native, use `<sub>` / `<sup>` |

## Lists
```markdown
- Item            (also + or *)
1. Ordered        (also 1) )
    - Nested      (indent with Tab/spaces)
```
Blank lines between items create a "loose" list with extra spacing.

## Tasks / checkboxes
```markdown
- [ ] Incomplete
- [x] Complete
- [?] Custom marker (any single char between the brackets renders as a custom state)
```

## Blockquotes
```markdown
> Quoted text
> > Nested quote
```

## Code
````markdown
Inline `code`.

```js
// fenced block, optional language for highlighting
```
````
Nested fences: increase backtick count (4, 5…). A 4-space/Tab indent also makes a code block.

## Tables
```markdown
| First name | Last name |
| ---------- | --------- |
| Max        | Planck    |
```
Alignment via colons in the separator row: `:--` left, `:--:` center, `--:` right.
Use `<br>` for a line break inside a cell. Escape literal pipes as `\|`; a wikilink alias
inside a cell must escape its pipe too: `[[Note\|Display]]`.

## Horizontal rule
```markdown
***
---
___
```

## Links & images
```markdown
[Link text](https://example.com)
![Alt text](https://example.com/image.jpg)
![Alt text|100x145](https://example.com/image.jpg)   # width x height
![Alt text|100](https://example.com/image.jpg)        # width only
```
URLs containing spaces: use `%20` or wrap in `< >`.

## Escaping
Prefix special chars with `\`: `\*  \_  \#  \`  \|  \~  \$`. Use `1\.` to avoid an
unwanted auto-numbered list. Backslash rendering can differ between Live Preview and
Reading view.

## Line breaks
Two trailing spaces + Enter, or Shift+Enter, force a `<br>`. A blank line starts a new
paragraph. Behavior depends on the **Strict line breaks** setting (`strictLineBreaks`):
- `false` (default): every newline is a hard break (Obsidian-only, non-portable).
- `true`: CommonMark, single newlines merge; two trailing spaces = `<br>`.
Use `&nbsp;` to preserve runs of spaces.

## Footnotes
```markdown
Text with a footnote[^1].
[^1]: Footnote content.

Inline footnote.^[This is an inline footnote.]
```

## Comments
```markdown
Visible %%hidden inline%% text.

%%
block comment
spanning lines
%%
```
Comments show in editing/source view, never in reading view.

## Not supported / sanitized
- No heading IDs, no emoji shortcodes, no definition lists, no native sub/superscript.
- HTML is sanitized in reading view: `<script>` is stripped (JS disabled); `<iframe>` is
  allowed. The exact native allowlist is not publicly fixed.
- **Markdown is not parsed inside HTML blocks**, and an HTML block cannot contain blank lines.
