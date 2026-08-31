# vault-kg-config

Configuration for the vault knowledge graph. Everything specific
to this vault lives here; the engine itself knows only markdown
structure. Edit this file directly.

```json
{
  "ignore": [
    {
      "path": "archive/**",
      "reason": "superseded copies"
    }
  ],
  "profiles": [
    {
      "date_from": "heading",
      "path": "journal.md",
      "profile": "log-dated",
      "slots": {
        "Metrics": "instrument",
        "Reflection": "authored",
        "Synthesis": "generated"
      }
    },
    {
      "path": "monolith.md",
      "profile": "log-dated"
    },
    {
      "group_by": "h2",
      "grain": "list-item",
      "path": "sources.md",
      "profile": "dimension"
    },
    {
      "path": "generated/*.md",
      "profile": "generated",
      "weight": 0.2
    },
    {
      "path": "hub.md",
      "profile": "hub"
    },
    {
      "path": "roster.md",
      "profile": "list"
    }
  ],
  "entities": [
    {
      "aliases": [
        "Dana"
      ],
      "canonical": "Dana Okonjo",
      "note": "",
      "type": "person"
    },
    {
      "aliases": [
        "drip"
      ],
      "canonical": "drip irrigation",
      "time": "evolving",
      "type": "method"
    },
    {
      "canonical": "Season Review",
      "time": "2026-06-10..2026-06-20",
      "type": "event"
    }
  ]
}
```
