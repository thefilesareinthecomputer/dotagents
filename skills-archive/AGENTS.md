# Skills archive rules

Skills in this folder are retired from the active roster but kept whole:
their SKILL.md, scripts, tests and evals stay intact and their history stays
in git. `sync-skills.sh` does not read this folder, so nothing here is
registered with any harness or charged to any session's context.

To restore a skill: `git mv skills-archive/<name> skills/<name>`, then run
`bash ~/.agents/sync-skills.sh`. To retire one: the reverse, plus removing
its rows from `README.md` and `SPEC.md`.

A skill enters this folder instead of being deleted because deletion is a
harder decision than retirement, and the usual reason for retiring one -
its domain is not currently in play - reverses.
