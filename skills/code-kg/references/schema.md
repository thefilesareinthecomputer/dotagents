# code-kg database schema

SQLite + FTS5 at `<repo>/.code-kg/code-kg.db`. Rebuilt whole by every ingest
except `coverage` and `runs`, which survive so execution evidence outlives a
re-parse. All paths are repo-relative posix.

## Tables

### files
| column | meaning |
|---|---|
| `id` | repo-relative path (the primary key everything joins on) |
| `language` | python, javascript, typescript, bash, dockerfile, yaml, terraform, sql, markdown, json, toml, make |
| `role` | `source`, `test`, `config`, `docs`, `ci` |
| `size`, `lines` | bytes, line count |
| `content_hash` | sha256 of the text |
| `body` | full file text (line-range reads slice this) |
| `parse_error` | non-empty when a parser failed; the file is still indexed for search |
| `origin` | `project` or `dep`. Dependency files (opt-in via config `deps`) are searchable only with `--deps`, carry symbols but no edges of their own, and never join liveness |

### symbols
| column | meaning |
|---|---|
| `id` | `<file>::<qualname>` (duplicates disambiguated `~2`, `~3`...) |
| `kind` | function, class, method, interface, type, enum, target, table, view, resource, module... |
| `line_start`, `line_end` | 1-indexed inclusive. Exact for python (AST); for regex-scanned languages the end is the line before the next symbol, which is approximate |
| `exported` | 1 unless underscore-private (python) or unexported (js) |

### edges
| column | meaning |
|---|---|
| `src`, `dst` | file ids; `dst` NULL unless status is `resolved` |
| `target` | the reference as written in the source |
| `kind` | see below |
| `status` | `resolved`, `external`, `unresolved`, `ambiguous` |

Edge kinds, strongest first:

- **Executable** (`import`, `from-import`, `from-import-sub`, `pkg-init`,
  `require`, `dynamic-import`, `reexport`, `source`, `exec`, `module`,
  `uses`, `script`, `include`) - the reference implies the target loads or
  runs. These drive liveness. `from-import-sub` is a `from pkg import
  submodule` resolved to the submodule file; `pkg-init` records that
  importing `pkg.mod` executes every ancestor `__init__.py`.
- **Weak** (`path-ref`, `link`, `copy`) - a string literal naming a repo
  path, a markdown/html link, or a Docker COPY / compose mount. Evidence of
  presence or reference, not of execution - dead code ships in images all
  the time. Directory COPYs/mounts are expanded to the files under them
  (capped at 200), each edge carrying the expanded path as its target.
- `include-sys` (`#include <...>`) is recorded external and never joins
  liveness.

Statuses: `resolved` means the target exists in this repo; `external` means
a package, stdlib module, base image or marketplace action outside the repo;
`dep` means an external import whose package code is indexed (dst is the
package's entry file, but the edge never joins liveness); `unresolved`
means it looks local and does not exist (a worklist item); `ambiguous`
means two candidates matched and none was chosen.

### entry_points
Detected roots for reachability: `main-guard` (python/go/rust/c/java/c#),
`shebang`, `script` (pyproject console script, msbuild Exe), `bin`
(package.json), `dockerfile`, `compose`, `workflow`, `make`, `page`
(index.html), `config` (declared in config.json). A test file's own entry
points never seed the live tier - that is what keeps `test-only` meaningful.

### coverage / runs
`coverage(file_id, line, hits)` holds max hits per line across every
ingested artifact or consented run; `runs` is the append-only event log.
Both survive re-ingest; coverage rows for deleted files are pruned.

### ignored
What an ingest excluded and why: `config:<glob>`, `oversize`,
`symlink-or-escape`.

### FTS
`symbols_fts(id, qualname, body)` indexes each symbol's text slice;
`files_fts(id, path, body)` indexes whole files. `search` tries symbols
first, then files, on a rung ladder (phrase, all-terms, any-term).
