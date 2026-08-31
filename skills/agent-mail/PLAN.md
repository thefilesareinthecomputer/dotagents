# Plan: agent-mail implementation

Build order (each slice verified before the next):

1. **lib.sh** - shared helpers: path canonicalization + safety, YAML escaping,
   slug, root detection + report, id timestamp/seed, name validation, `am_die`.
2. **send.sh** - arg parse → repo resolve → root resolution → inbox guard →
   envelope render (escaped) → atomic `ln`-create with NNN retry → print path.
   `--create-inbox` also drops `HOW-TO-AGENT-MAIL.md`. `--inspect` prints the report.
3. **mark.sh** - atomic status rewrite (awk, front-matter only) + move resolved/
   canceled to flat `processed/`; malformed front matter → error (no sidecar).
4. **inbox.sh** - list/summarize top-level unread (`--all` includes processed).
5. **templates/** - request/response/handoff/fyi body skeletons + inbox-guide.md.
6. **SKILL.md** - trigger + send/receive workflow + boot rule + onboarding.
7. **tests/run.sh** - exercises every branch (root resolution, guards, race,
   YAML safety, path safety, status+archive). This is the acceptance gate.

Risks / mitigations:
- BSD vs GNU tools → pin BSD (`stat -f`, `date -u`, `awk` not `sed -i`); test on darwin.
- Atomicity → `ln` create (fails on existing) + temp-then-`mv` for edits.
- id race → render-per-attempt with NNN bump on `ln` failure.
- YAML injection → reject control chars, escape `\`/`"`, validate names.

Verification checkpoint after each slice: a targeted shell check; final gate is
`tests/run.sh` green.
