---
name: sanitize
description: Deterministic scrubbing engine that writes a cleaned copy of any file or folder (text, code, Markdown, JSON, CSV, Word), scans a repo tree without editing it, or gates one answer on stdin - secrets by shape, emails, phones, home paths, the station term list on raw and normalized text (split tokens, confusables, zero-width, base64, hex), plus per-run terms, patterns and ban lists. No model runs inside it; the report holds counts and paths, never a value. Use when a folder, document or export must be cleaned before a model or another person sees it, when a training staging folder needs its cleaning report, when a repo needs a pre-publish scan for identifiers or secrets, or when a vault answer must be checked against protected terms. Not for web input sanitizing or git history rewrites.
---

# sanitize

One engine runs three modes, with no model inside it. The original is read by the script and nothing
else; what comes out is a copy with every hit replaced by a class placeholder
(`[SECRET]`, `[TERM]`, `[EMAIL]`, `[PHONE]`, `[HOME]`, `[ROLE]`, `[CATALOG]`,
`[PATTERN]`) and a report of counts and paths. Any model pass, local or cloud, is
something you run afterwards over the copy.

## Commands

Every command runs as `python3 ~/.agents/skills/sanitize/scripts/sanitize.py ...`.

### copy (alias: corpus)

```
sanitize.py copy <file-or-folder> [--out <path>] [--force] [--include-binary] [--max-mb 50]
                 [--exclude <glob>...] [--terms a,b] [--patterns <regex>...] [--ban-list <file>]
                 [--config <corpus.json>] [--no-station-terms]
```

- Writes a cleaned copy at `--out`, or beside the source as `<name>-clean`. Folders
  are 0700 and files 0600; the original is never touched. The destination must sit
  outside the source, and an existing non-empty destination needs `--force`.
- File names and folder names go through the engine too, so a folder named after a
  client comes out as `[TERM]`; the report counts these under `path`.
- JSON is parsed and every key and string value cleaned, so a term behind a
  `\uXXXX` escape is found. JSONL goes line by line, CSV and TSV cell by cell, a
  `.docx` is rezipped with its `word/*.xml` text cleaned and every other part
  byte-identical. Everything else that decodes as UTF-8 is cleaned as text.
- PDFs and binaries are skipped and listed in the report with a reason;
  `--include-binary` copies them through unchanged. Files over `--max-mb` are
  skipped as `too-large`. `.git`, `node_modules`, `.venv` and the usual caches are
  excluded by default; `--exclude` adds path-component globs.
- The report lands as `sanitize-report.json` in the copy (or `<out>.sanitize-report.json`
  for a single file) and is printed to stdout.

### tree

```
sanitize.py tree <path> [--tracked] [--exclude <glob>...] [--terms ...] [--patterns ...] [--config ...]
```

- Tree mode only reports and writes nothing. It exits `1` when anything would have
  been replaced and `0` when clean. `--tracked` limits the scan to the files git
  tracks under the path, which is the right scope before a publish.

### answer

```
sanitize.py answer [--config <vault.json>] < answer.txt
```

- Answer mode reads text on stdin and writes text to stdout. Secrets and personal
  shapes are replaced; a hit on the station list or a ban list withholds the whole
  answer and exits `3`. This is the local vault's gate before an answer goes to a
  cloud agent.

### doctor

Prints whether the station term list is present (its count, never its contents),
runs a normalization self-test, and states that the recall layer is off. Exits `2`
when the list is missing.

## What gets replaced, in order

1. **Secret shapes:** private key blocks, vendor key prefixes, cloud access keys,
   JWTs, bearer and header credentials, URL passwords, `--password`-style flags, and
   key-like assignments whose value looks like a credential (twelve or more key
   characters with a digit), so `key = parts[0]` in code is left alone.
2. **Personal shapes:** email addresses, phone numbers, a macOS or Linux home
   directory prefix with its user name (the rest of the path stays), role-coded
   initials and environment-prefixed catalog names.
3. **The station term list,** read from `IDENTIFIER_TERMS_FILE` or its default under
   `~/.claude/private/`, by the identifier hook's rule: a single-case term matches any
   case, a mixed-case term matches as typed, and no word character may touch either
   edge. Terms are matched on the raw text, then on a normalized view (whitespace and punctuation
   dropped, confusables and full-width letters folded, zero-width characters removed),
   then inside base64 and hex runs decoded once. The report splits these as `term`,
   `term-normalized` and `term-encoded`, so a noisy view shows up as its own number.
   A missing list is a refusal (exit `2`); `--no-station-terms` runs without it on purpose.
4. **Per-run additions:** `--ban-list <file>` (one term per line, `# ` comments),
   `--terms a,b`, `--patterns <regex>...`, or a `--config` JSON with `ban_list`, `terms`
   and `patterns` (`references/corpus.example.json`). Codenames go in as terms.

## Reading the report

`references/report.schema.json` is the contract. `removed` is hits by class across
the run; `files_changed` lists each file that lost content with its relative path, its
top-level `origin` folder and its per-class counts, so a whole source can be dropped
from a training set; `skipped` lists binaries, PDFs and oversized files. No field
holds a matched value. Terms shorter than four characters are matched on raw text
only, and a two-character term on the station list will fire on prose; if `term`
counts look high, check the list before the files.

## Exit codes

`0` clean or copied; `1` tree found hits; `2` bad arguments, config, or a missing
station term list; `3` answer withheld; `4` self-test or masker failure.

## Boundaries

- The engine never prints a matched value, never edits in tree mode, never writes a
  reversible mapping, and never calls a model.
- The station term list is never copied into this skill; the tests use invented words
  and `tests/test_self_guard.py` scans the skill's own files on every run.
- The recall-layer masker (a local CPU model over the copy) is a later phase and
  ask-first. PDF text is out of scope until a dependency is approved.

Spec: `tasks/SPEC-SANITIZE.md`. Tests: `python3 -m unittest discover -s ~/.agents/skills/sanitize/tests -v`.
