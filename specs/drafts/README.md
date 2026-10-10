# specs/drafts

Station elements that are built and tested but have not passed the gate their feature spec names. Nothing here is seeded, wired or configured by `agent-cc-configs-sync` or any other ritual, and no harness spec under `specs/<harness>/` describes it.

Drafts are laid out one subfolder per target harness, mirroring `specs/`. A draft for Claude Code lives at `specs/drafts/claude-code/<element>/`; a draft hook for Codex would live at `specs/drafts/codex/<element>/`, and so on, using the same folder names as the harness tree so the eventual move is a rename. Each draft has a feature spec in `tasks/` (or `tasks/backlog/`) that names its gate; when it passes, the folder moves into `specs/<harness>/` and that harness's spec gains its section in the same commit.

| Harness | Draft | Gate | Spec |
|---|---|---|---|
| `claude-code/` | `decision-hook/` | its judgment clears recall 0.80 and the base-rate false-escalation budget on the held-out fifth of the user's real labels | `tasks/SPEC-DECISION-HOOK.md` |
