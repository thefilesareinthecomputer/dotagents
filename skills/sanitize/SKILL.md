---
name: sanitize
description: Deterministic scrubbing engine and the station's one detector source - writes a cleaned copy of any file or folder, scans a repo tree without editing it, gates one answer on stdin, or checks the added lines of a commit or push for secrets by shape, emails, phones, home paths and the station term list. No model inside; output never holds a value. Use when a folder, document or export must be cleaned before a model or another person sees it, when a training staging folder needs its cleaning report, when a repo, a staged change or an unpushed range needs a scan for identifiers or secrets, or when a vault answer must be checked against protected terms. Not for web input sanitizing, git history rewrites, or a full security review, which is my-security-review-checklist.
---

# sanitize

The skill is one engine with no model inside it. The original is read by the script
and nothing else; what comes out is a copy with every hit replaced by a class placeholder
(`[SECRET]`, `[TERM]`, `[EMAIL]`, `[PHONE]`, `[HOME]`, `[ROLE]`, `[CATALOG]`,
`[PATTERN]`) and a report of counts and paths. Any model pass, local or cloud, is
something you run afterwards over the copy.

`scripts/detect.py` is the station's one rule source: every content detector, allowance,
codepoint table and severity table lives there. The `gate` command, the wrap-up lint,
agent-mail's send-time check, the hidden-character scanner and the write-time hooks all
import it, so a detector is fixed once and every consumer gets the fix.

## Commands

Every command runs as `python3 <skill-dir>/scripts/sanitize.py ...`.
The old names `tree`, `answer`, `verify` and `corpus` still run as `check`, `filter`,
`check --raw` and `copy`, with a one-line note on stderr.

### copy

```
sanitize.py copy <file-or-folder> [--out <path>] [--force] [--include-binary] [--include-docx] [--no-verify]
                 [--max-mb 50] [--exclude <glob>...] [--terms a,b] [--patterns <regex>...] [--ban-list <file>]
                 [--config <corpus.json>] [--no-station-terms]
```

- Writes a cleaned copy at `--out`, or beside the source as `<name>-clean`. Folders
  are 0700 and files 0600; the original is never touched. The destination must sit
  outside the source. An existing non-empty destination needs `--force`, which
  replaces it whole rather than overlaying it, and only when it is an earlier copy
  (a report at its top, or beside it for a single file); anything else is refused.
- File names and folder names go through the engine too, so a folder named after a
  client comes out as `[TERM]`; the report counts these under `path`.
- JSON is parsed and every key and string value cleaned, so a term behind a
  `\uXXXX` escape is found, and a string value keeps its key's context, so a
  credential under a key-like name is judged as the assignment `key=value` would
  be. JSONL goes line by line, CSV and TSV cell by cell with the header naming each
  column. A JSON file with a duplicate key is counted (`json_duplicate_key`) and
  cleaned as text, since a parse would drop the earlier value unscanned.
  Everything else that decodes as UTF-8 is cleaned as text.
- A `.docx` is skipped as uninspected unless `--include-docx` is passed, because
  the text-node pass misses attributes, CDATA and a term split across runs; with
  the flag its `word/*.xml` and `docProps/*.xml` text is cleaned and every other
  part kept byte-identical, and a zip whose parts inflate past 64 MB is skipped.
- Encoded runs (base64, url-safe base64, hex, percent-encoding, HTML character
  references) are decoded once and checked against every detector, not the term
  list alone; a run holding a secret or a shape is replaced whole as
  `<class>-encoded`.
- A term shorter than four characters matches as typed only; the any-case rule
  would make an all-caps two-letter term match the common word it spells.
- PDFs and binaries are skipped and listed in the report with a reason;
  `--include-binary` copies them through unchanged. Files over `--max-mb` are
  skipped as `too-large`. `.git`, `node_modules`, `.venv` and the usual caches are
  excluded by default; `--exclude` adds path-component globs.
- The report lands as `sanitize-report.json` in the copy (or `<out>.sanitize-report.json`
  for a single file) and is printed to stdout.

### check

```
sanitize.py check <path> [--tracked] [--exclude <glob>...] [--max-mb 50] [--terms ...] [--patterns ...] [--config ...]
sanitize.py check --raw <copy-path> [--allow-binary] [--terms ...] [--patterns ...] [--config ...]
```

- `check` only reports and writes nothing. It exits `1` when anything would have
  been replaced, `4` when a text-bearing file was left uninspected, and `0` when
  clean. `--tracked` limits the scan to the files git tracks under the path, which
  is the right scope before a publish.
- `check --raw` is the release verifier, a second pass that shares no parser with the engine.
  It reads every file in the copy as flat text, every member of a zip the same way, and
  every path, and runs every matcher over them. Any hit exits `1`; any part it could not
  decode exits `4` (pass `--allow-binary` when binaries were copied through on purpose).
  Its JSON output has its own shape (`ok`, `files`, `hits`, `uninspected`), not the report schema.
  `--tracked`, `--exclude`, `--max-mb` and `--include-docx` with `--raw`, or
  `--allow-binary` without it, exit `2`.
- `copy` runs the raw pass over the staging folder before the copy lands and refuses (exit
  `5`) on either outcome, so a gap in a parser can never ship a copy as clean. The
  report records `verified`; `--no-verify` skips the pass and records `null`.

### filter

```
sanitize.py filter [--config <vault.json>] < answer.txt
```

- `filter` reads text on stdin and writes text to stdout. Secrets and personal
  shapes are replaced; a hit on the station list, a ban list or a per-run pattern
  withholds the whole output and exits `3`. The term check runs on the original
  text, so a term inside an address or a path is still a hit. This is the local
  vault's gate before an answer goes to a cloud agent.

### doctor

`doctor` prints whether the station term list is present (its count, never its contents),
runs a normalization self-test, and states that the recall layer is off. Exits `2`
when the list is missing.

### gate

```
sanitize.py gate --staged | --refs [--remote R] | --range A..B | --message FILE | --files PATH... [--json]
```

`gate` is the commit and push check behind the station's git hooks (`hooks/git/`,
installed with `sh hooks/git/install.sh`). It reports on added lines only: every detector
runs over each touched file's full post-image, and a finding counts when it touches an
added line. A range (and a pre-push ref list) is scanned commit by commit, reading each
commit's diff and message, so a secret added and then removed still counts.
The gate blocks with exit `3` on secrets, hidden-character attacks (tag, bidi, zero-width),
a home path with a real login (a placeholder owner, such as a one-letter name, passes) and
a commit message that describes sensitivity. The other identifier shapes (terms, emails,
work items, GUIDs) warn and exit `0`. `--files` reads whole files at the
review severity the wrap-up lint uses. Output is `path:line  class  tier` and never
includes the value.

A missing term list skips the term class with one note. A git object the gate cannot
read blocks. A bug in the gate exits `0` with a stderr line, so a gate bug never stops
every commit on the machine. Lockfiles, minified bundles and binaries are skipped. A text
file up to 8 MiB is scanned whole; a larger one is scanned within 64 lines of each added
line, so the time follows the change; one over 1 GiB blocks, since it cannot be checked.

A staged file under `.claude/inbox/` or `.agents/inbox/` blocks the commit by path, so
agent-mail stays out of history. To commit inbox files on purpose, run that one commit
as `AGENT_MAIL_COMMIT_INBOX=1 git commit ...`, which lifts the inbox rule and nothing else.
The only full escape hatch is the user's: `--no-verify` on commit and push from their own
terminal. `hooks/guard_git_bypass.py` refuses the same flag when an agent passes it.

## What gets replaced, in order

1. **Secret shapes:** private key blocks, vendor key prefixes, cloud access keys,
   JWTs, bearer and header credentials, URL passwords, `--password`-style flags, and
   key-like assignments whose value looks like a credential (twelve or more key
   characters with a digit), so `key = parts[0]` in code is left alone.
2. **Personal shapes:** email addresses, phone numbers, a macOS or Linux home
   directory prefix with its user name (the rest of the path stays), role-coded
   initials and environment-prefixed catalog names.
3. **The station term list,** read from `IDENTIFIER_TERMS_FILE` or its default in the
   harness config folder's private directory, by the identifier hook's rule: a single-case term matches any
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
only and as typed, so an all-caps two-character term does not fire on the common
word it spells; if `term` counts still look high, check the list before the files.

## Exit codes

| Exit | Meaning |
|---|---|
| `0` | Clean, or the copy was written. |
| `1` | `check` found hits. |
| `2` | Bad arguments or config, a missing station term list, or a copy refused before anything was written (a destination that is a link, two sources cleaning to one path, a source file named like the report, a destination `--force` may not replace). |
| `3` | `filter` withheld its output, or `gate` blocked. |
| `4` | `check` left a text-bearing file uninspected (a PDF, a Word file without `--include-docx`, an oversized, unreadable or undecodable file; known binary types do not count there), or `check --raw` could not decode a file or a zip member (every one counts unless `--allow-binary`, media members aside), or the self-test failed. |
| `5` | The verifier refused a copy, which was then not written. |

## Boundaries

- The engine never prints a matched value, never edits in check mode, never writes a
  reversible mapping, and never calls a model.
- The station term list is never copied into this skill; the tests use invented words
  and `tests/test_self_guard.py` scans the skill's own files on every run.
- The recall-layer masker (a local CPU model over the copy) is a later phase and
  ask-first. PDF text is out of scope until a dependency is approved.

The spec is `tasks/SPEC-SANITIZE.md`, and the tests run with `python3 -m unittest discover -s <skill-dir>/tests -v`.
