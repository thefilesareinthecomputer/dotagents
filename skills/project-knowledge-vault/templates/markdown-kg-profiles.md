# markdown-kg-config rows for a project knowledge vault and its deliverables

`vault_scaffold.py` runs `markdown_kg.py init` on a new vault and on its deliverables folder, and merges these rows into the `profiles` and `ignore` arrays of each one's `markdown-kg/markdown-kg-config.md`, adding only rows whose `path` the config does not already have. For a vault seeded without the graph, run `init` by hand and merge them the same way. Config has no CLI write path; the file is edited directly. Longest matching glob wins.

```json
{
  "ignore": [
    {"path": "AGENTS.md", "reason": "the vault contract, not a note"},
    {"path": "CLAUDE.md", "reason": "one-line pointer to the contract, not a note"},
    {"path": "templates/", "reason": "the deliverables folder's document templates, not documents"}
  ],
  "profiles": [
    {"path": "index.md", "profile": "hub"},
    {"path": "log.md", "profile": "log-dated", "date_from": "heading"},
    {"path": "notes-*.md", "profile": "log-dated", "date_from": "heading",
     "slots": {"DECISIONS": "authored", "ACTIONS": "routine", "QUESTIONS": "routine",
               "COMMENTS": "quoted", "DONE": "routine", "IN FLIGHT": "routine", "BLOCKED": "routine"}},
    {"path": "notes-questions.md", "profile": "reference"},
    {"path": "user-stories*.md", "profile": "reference"},
    {"path": "user-runsheet.md", "profile": "reference"},
    {"path": "[0-9][0-9]-*.md", "profile": "reference"},
    {"path": "agents-*.md", "profile": "generated"},
    {"path": "code-*.md", "profile": "reference", "weight": 0.5},
    {"path": "docs-*.md", "profile": "reference", "weight": 0.8}
  ]
}
```

What each row buys: `hub` keeps `index.md` searchable while taking its edges out of the degree prior and out of `neighbors` walks. `log-dated` on `notes-*` gives every dated entry a date for recency ranking, `trajectory`, `themes` and `trends`, and the slots keep checklists and quoted review threads out of the authored-prose aggregates. The engine learns the date level from the headings, so the `# YYYY-MONTH` H1s group the months while each dated H2 stays one section. The question register is a reference note because its headings are topics, not dates. Ingested `code-*` and `docs-*` are down-weighted so a repository dump does not outrank the notes written about it. The contract is ignored because every vault ships the same text, and indexing it puts the same answer in every search.
