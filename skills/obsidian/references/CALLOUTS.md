# Callouts Reference

A callout is a blockquote whose first line is `> [!type]`.

## Grammar
- `> [!type]`, no space between `>` and `[!`. Type token is **case-insensitive**
  (`[!NOTE]` == `[!note]`). **Unknown types fall back to `note`** (still render).
- **Foldable:** append `-` (collapsed by default) or `+` (expanded, collapsible) directly
  after the token: `> [!faq]-`.
- **Custom title:** text after the token: `> [!tip] My Title`. Title-only (no body) is valid.
- **Body** supports full Markdown, wikilinks, and embeds.
- **Nesting:** add a `>` per level.

```markdown
> [!note]
> Basic callout.

> [!info] Custom Title
> Body supports **markdown**, [[Wikilinks]], and ![[embeds]].

> [!tip] Title only

> [!faq]- Collapsed by default
> Hidden until expanded.

> [!faq]+ Expanded by default
> Visible but can be collapsed.

> [!question] Outer
> > [!todo] Inner
> > > [!example] Deeper
```

## Built-in types (type → aliases → color / icon)
| Type | Aliases | Color / icon |
|------|---------|--------------|
| `note` | (none) | Blue, pencil |
| `abstract` | `summary`, `tldr` | Teal, clipboard |
| `info` | (none) | Blue, info |
| `todo` | (none) | Blue, checkbox |
| `tip` | `hint`, `important` | Cyan, flame |
| `success` | `check`, `done` | Green, checkmark |
| `question` | `help`, `faq` | Yellow, question mark |
| `warning` | `caution`, `attention` | Orange, warning |
| `failure` | `fail`, `missing` | Red, X |
| `danger` | `error` | Red, lightning |
| `bug` | (none) | Red, bug |
| `example` | (none) | Purple, list |
| `quote` | `cite` | Gray, quote |

## Custom callout type (CSS snippet)
```css
.callout[data-callout="custom-type"] {
  --callout-color: 255, 0, 0;          /* RGB */
  --callout-icon: lucide-alert-circle; /* any Lucide icon id */
}
```

## Portability note
Callouts render only in Obsidian (and compatible tools). Elsewhere they degrade to plain
nested blockquotes.
