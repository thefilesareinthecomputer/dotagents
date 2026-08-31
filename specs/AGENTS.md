# Specs folder rules

This `specs/` folder contains one folder per harness, each containing its station spec example files to accelerate setup and config for a new installation.  
[`README.md`](README.md) carries the index and the full folder convention; these are the rules that keep the tree sound while editing it.

- **A spec is the source of truth for a station.**
  Bring a machine into line with it non-destructively: diff first, show what would change, and get approval before overwriting anything that already exists.
- **Seed files and the station files they seed stay in byte parity.**
  An edit to a seed here is a pending change to every machine; never let the two copies drift silently.
- **No personal constants.**
  Specs and seeds carry no names, emails, handles, personal repo URLs, or device-specific paths.
  Anything personal is derived at runtime or asked of the user live.
- **Naming.**
  The folder is the harness slug (`claude-code`, `copilot`); the spec is `SPEC-<HARNESS>.md` and is the only required file.
  A new harness gets a new folder and a row in README's table.
- **Links.**
  Same-folder links are bare filenames; cross-folder links are relative (`../copilot/SPEC-COPILOT.md`).
  Assets shared by several harnesses stay at `specs/` level.
- **Specs describe current state.**
  Session records and retired feature specs go to `tasks/completed/`, never here, and a claim that is doc-derived rather than confirmed by observation says so.
