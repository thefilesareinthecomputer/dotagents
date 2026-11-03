---
name: scan
description: Report-only malware and trust check on macOS, fired by the user as /scan <path>. Updates the ClamAV signatures when they are over a day old, runs ClamAV over the file or folder, then judges every app, disk image, installer and bare program found with Apple's checks - Gatekeeper, who signed it, the quarantine tag, the download origin and a SHA-256. A sweep mode lists what in a folder was made on this Mac rather than downloaded, plus agent instruction files and runnable files. Never changes what it scans. Scheduled scanning of the user's folders is local-security's lane.
license: MIT
disable-model-invocation: true
argument-hint: <file-or-folder> [--sweep]
---

# scan

`/scan <path>` checks a file or folder and reports. It never deletes, moves, quarantines or opens anything it scans.

## Run

Downloads, Desktop and Documents are the user's: agents stay out of them.
When the path is inside one of them, do not run anything; give the user the line to run themselves, then interpret the output they get:

```
! python3 <skill-dir>/scripts/scan.py "<path>"
```

Anywhere else, run it:

```
python3 <skill-dir>/scripts/scan.py "<path>" [--json] [--no-update]
python3 <skill-dir>/scripts/scan.py "<folder>" --sweep [--since YYYY-MM-DD]
```

- **Scan** (default). Runs `freshclam` first when the ClamAV signatures are over 24 hours old; that download from ClamAV's mirrors is the one network call besides Gatekeeper's notarization lookup. `--no-update` skips it when offline. A ClamAV pass takes several seconds even for one file.
- **Sweep** (`--sweep`, a folder). Lists, without scanning: files changed since `--since` (default 30 days) with no quarantine tag, meaning they were made on this Mac rather than downloaded by a browser, which is how a file dropped by an agent or a script shows up; agent instruction and auto-run files (`AGENTS.md`, `CLAUDE.md`, `.mcp.json`, `.envrc`, `.vscode` and similar); runnable files counted per top-level folder. Scan whatever the user does not recognize.

## Setup

The scan checks ClamAV's setup before every run. When ClamAV is missing, `freshclam.conf` does not exist, or the config still holds its `Example` line, it scans nothing with ClamAV, reports `setup-needed`, and lists the exact commands in order: `brew install clamav`, copying `freshclam.conf.sample` to `freshclam.conf`, commenting out `Example`, and a first `freshclam` (about 200 MB). Walk the user through them one at a time, each as a `!` line they run, confirm each step's output, then scan again. Apple's checks run either way. With the config in place and no signatures yet, the scan downloads them itself.

## Read the result

| Verdict | Exit | Meaning |
|---|---|---|
| clean | 0 | no signature matched and Apple's checks passed |
| findings | 1 | a ClamAV match, or a broken signature (the file changed after signing) |
| unverified | 3 | Gatekeeper refuses it or nothing says who made it: ad-hoc signed, unsigned or not notarized. This is common for self-built apps and developer tools; the user judges it, and a SHA-256 compared with the vendor's download settles authenticity. A sweep returns 3 when it lists anything to review. |
| incomplete | 4 | ClamAV needs setup (see Setup), or a tool failed; the other lane (ClamAV or Apple's checks) still ran |

Exit 2 is a bad path or argument.

- The signer shows as `Apple`, `Developer ID` with the publisher and team, `ad-hoc (no publisher)`, or unsigned.
- An unsigned disk image is a note, not a finding: Gatekeeper judges the app inside, so the user mounts it and scans the app.
- "No quarantine tag" on an item means it was not downloaded by a browser: built locally, copied, or written by a program.
- A failed signature update is a warning and the scan still runs; say how old the signatures were.
- Apple's XProtect rules are shown by age. Updating them needs root (`sudo xprotect update`), so the scan never does; pass the command to the user when it warns.
- Report the verdict first, then each item that is not clean with its reason, and what the user can do: delete it, or keep it and not open it. Never act on a result yourself. A clean result is not proof the file is safe.
