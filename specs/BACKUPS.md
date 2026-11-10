# Backups - where a local artifact's backup goes

This is the default for a backup that nothing else defines.
A tool or repo whose own docs already say where its backups go keeps that definition.

A backup of a local artifact, such as a database, an export or anything a migration rewrites, goes in one home-level directory and never inside a repo.
That directory holds one folder per repo, with dated files inside:

```
~/backups/<repo-folder-name>/<artifact>_<YYYY-MM-DD>.<ext>
```

`<repo-folder-name>` is the name of the repo's top-level folder as it is checked out on the machine.
`<artifact>` is the backed-up file's name without its extension, and `<ext>` is that extension unchanged.

## Scripts that take a backup

- The destination defaults to the `~/backups/<repo-folder-name>/` path when the caller names none.
- A destination inside a repo (any path under a folder that holds a `.git`) is refused with a non-zero exit, not warned about.
- An existing dated file is never overwritten; a second backup to the same path is refused.

## Lifetime

A backup made for a migration is a rollback copy.
It is deleted once the migration is verified, unless the repo's own docs say it is kept.
