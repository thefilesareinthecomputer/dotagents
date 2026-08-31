# code-kg config reference

`<repo>/.code-kg/config.json`, one JSON object. A missing config is valid:
every field defaults to empty. Edit the file directly.

```json
{
  "ignore": ["generated/**", "*.pb.py"],
  "roots": ["backend/src"],
  "entry_points": ["tools/nightly_job.py", "jobs/**/handler.py"],
  "aliases": {"@/*": "src/*"},
  "profile": "",
  "test_command": "python3 -m coverage run -m pytest -q"
}
```

## Fields

- **ignore** - glob patterns (same dialect as .gitignore's common core: `*`
  within a segment, `**` across segments, bare names match any path part).
  Matched files are recorded in the `ignored` table with the rule that
  excluded them, so an ignore is always auditable. Use for generated code,
  third-party trees, and fixtures that would pollute liveness.
- **roots** - extra Python import roots besides the repo root. `src/` is
  auto-detected; add others (`backend/`, `services/api/`) when absolute
  imports resolve from somewhere deeper. A wrong root shows up as a burst of
  `unresolved` python edges - run `unresolved` to check.
- **entry_points** - repo-relative paths or globs to treat as reachability
  roots on top of the detected ones (main guards, shebangs, packaging
  scripts/bins, Dockerfiles, compose files, workflows, Makefiles, framework
  convention files). Use for jobs invoked by external schedulers the repo
  cannot see - cron entries, serverless handlers, plugin hooks. An entry
  that matches nothing is warned about at ingest, never silently ignored.
- **aliases** - import-alias map merged after autodetection (tsconfig
  `paths`, package.json `imports`); config wins on pattern collision.
  Single-star patterns only. The escape hatch for Vite/webpack/Deno-import-
  map conventions the engine deliberately does not parse.
- **profile** - framework profile override: `"django"`, `"nextjs"`, or
  `"generic"` to disable convention rules. Empty (default) auto-detects and
  prints the result at init/ingest.
- **deps** - `"none"` (default) or `"referenced"`. Referenced mode indexes
  the code of dependencies the project imports, from repo-local installs
  only (`.venv`, `venv`, `node_modules`), tagged `origin='dep'`: searchable
  with `--deps`, readable by path or symbol id, excluded from liveness and
  default search. Caps: 400 files per package, 4000 total (overflow lands
  in `ignored` as `dep-cap`). Drift detection watches lockfiles rather than
  the dependency tree, so run `ingest` after installing packages.
- **test_command** - what `coverage run --yes` executes, split with shlex,
  cwd at the repo root - this is also the override for repos whose runner
  needs flags (e.g. `python3 -m coverage run manage.py test core
  --settings=config.settings_test`). When empty, detection prefers the
  Django runner (`manage.py test`) on Django repos without pytest config,
  else pytest under coverage.py. JS test scripts are never auto-run (their
  coverage flags are repo-specific); the refusal names the script it saw.
  A custom command is expected to leave a standard artifact
  (`coverage.json`, `lcov.info`, `coverage/coverage-final.json`) for
  auto-ingest.

## Built-in exclusions (not configurable)

Dot folders (except `.github` and the agent-tooling layer: `.claude`,
`.agents`, `.cursor`), `node_modules`, virtualenvs, build output,
caches, lockfiles, minified bundles, files over 2 MB, and symlinks -
symlinked "source" pointing outside the repo is refused and recorded, never
followed.
