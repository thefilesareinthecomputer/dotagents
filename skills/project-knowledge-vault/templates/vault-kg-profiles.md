# vault-kg-config rows for a project knowledge vault

Run `obsidian_kg.py init <vault>/PROJECTS/<NAME>` once, then merge these rows into the
`profiles` and `ignore` arrays of `<vault>/PROJECTS/<NAME>/vault-kg/vault-kg-config.md`.
Config has no CLI write path; the file is edited directly. Longest matching glob wins.

```json
{
  "ignore": [
    {"path": "CLAUDE.md", "reason": "one-line pointer to the contract, not a note"}
  ],
  "profiles": [
    {"path": "index.md", "profile": "hub"},
    {"path": "log.md", "profile": "log-dated", "date_from": "heading"},
    {"path": "notes-*.md", "profile": "log-dated", "date_from": "heading",
     "slots": {"DECISIONS": "authored", "ACTIONS": "routine", "QUESTIONS": "routine",
               "COMMENTS": "quoted", "DONE": "routine", "IN FLIGHT": "routine", "BLOCKED": "routine"}},
    {"path": "notes-questions.md", "profile": "reference"},
    {"path": "user-stories*.md", "profile": "reference"},
    {"path": "[0-9][0-9]-*.md", "profile": "reference"},
    {"path": "agents-*.md", "profile": "generated"},
    {"path": "code-*.md", "profile": "reference", "weight": 0.5},
    {"path": "docs-*.md", "profile": "reference", "weight": 0.8}
  ]
}
```

What each row buys: `hub` keeps `index.md` searchable while taking its edges out of the
degree prior and out of `neighbors` walks. `log-dated` on `notes-*` gives every dated
entry a date for recency ranking, `trajectory`, `themes` and `trends`, and the slots keep
checklists and quoted review threads out of the authored-prose aggregates. The question
register is a reference note because its headings are questions, not dates. Ingested
`code-*` and `docs-*` are down-weighted so a repository dump does not outrank the notes
written about it.
