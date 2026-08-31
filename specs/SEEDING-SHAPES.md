# Seeding shapes - the vocabulary every station spec's table uses

What a harness inherits natively from this repo differs element by element, so the variable is not the harness: it is the pair of **harness and element**.
Each spec declares which verb applies where, and this file defines the verbs.

## The shapes

Six, and they are the whole vocabulary. A spec's table uses no others.

| Shape | Meaning | Sync action | Drift check |
|---|---|---|---|
| `NATIVE` | the harness already reads `~/.agents/` | none | none possible; note the path it reads |
| `POINTER` | one small file registering an external path | write the pointer if absent | file exists and names the right path |
| `LINK` | symlinks planted into a directory the harness owns | plant, idempotently, never overwrite a real file | link resolves to this repo |
| `COPY` | a whole file installed and held in byte parity | copy on approval, diff first | `diff` is empty |
| `FRAGMENT` | a seedable portion merged into a station-owned file | merge the named keys only | the named keys match; the rest is the station's |
| `N/A` | does not port to this harness | none | none |

`FRAGMENT` exists because some station files cannot be seeded whole.
A Codex `config.toml` carries credentials, plugin enablement and trusted project paths; a Cursor `cli-config.json` carries an auth cache and UI state.
Seeding those wholesale would clobber a working station, so the seedable unit is a set of keys, not a file.
Any table row that would destroy station state if copied is a `FRAGMENT` row, and getting that wrong is the failure mode this vocabulary exists to prevent.

## Safety rules that bind every table

These came out of reviewing the first four tables, where three rows would have clobbered station state or widened a boundary.

- **Seeding is one-way.**
  Files move from this repo to a station, never back.
  A station file can hold credentials - an `apiKeyHelper`, an auth cache, secrets in an `env` block - so copying one into this repo publishes them.
- **A `COPY` row must be a file the seed fully owns.**
  If a station accumulates keys the seed has no opinion about, it is a `FRAGMENT`, not a `COPY`.
  The test: would a parity check on a working station ever come back clean? If not, the shape is wrong.
- **A `FRAGMENT` row names its keys.**
  An unkeyed merge into a permissions file is an unbounded permission edit.
  A row that cannot name its keys is `N/A` pending a probe, never a fragment "of the relevant part".
- **Widening keys move only in the restrictive direction.**
  Trust lists, URL allowlists and permission modes may be seeded tighter, never looser, and a blanket-allow value is never seeded.
- **A row that grants trust bounds its scope.**
  Trusting a path grants it to everything beneath, so only a specific target is ever written and no ancestor of a home or multi-repo directory is eligible.
- **An unverified location is not a row.**
  If which file a harness reads has not been probed, the row says so and seeds nothing.
  Writing to the wrong file either gets silently overwritten or reports success while nothing enforces.

## The table each spec carries

A section titled **Seeding** with one row per element.
Elements are fixed so the tables are comparable: skills, subagents, commands, rules, permissions, hooks, and any harness-specific extras.

| Element | Shape | Station path | Notes |
|---|---|---|---|

`Station path` is written in portable form (`~/...`, `$VAR/...`) and never as an absolute path from any machine.
`Notes` carries the parity requirement, the keys for a `FRAGMENT`, or the reason for an `N/A`.
