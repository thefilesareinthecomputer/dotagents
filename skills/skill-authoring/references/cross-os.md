# Cross-OS skills

Skills here are built on macOS and must keep working there.
Windows support is the next target wherever it costs little rework.
Linux is a bonus when it comes along for free, which it usually does once Windows works.
A new or edited script meets this bar before it is committed, unless the user says otherwise.
A fix never changes behavior on macOS: the safe forms below are byte-identical there.

`scripts/check_portable.py <paths>` flags each construct below and exits 1 on a finding.
For the interpreter row it catches only a hardcoded `/usr/bin/python...`, not a bare `python3` in argv.
Keep a line as written with `# portable: exempt <reason>` on it or in the comment block above.

## The rules

| Construct | Why it breaks on Windows | Portable form |
|---|---|---|
| `os.O_NOFOLLOW`, `os.getuid`, `os.setsid`, `os.killpg` | The attribute does not exist | `getattr(os, "O_NOFOLLOW", 0)`, or a `sys.platform` check |
| `import fcntl` (also `termios`, `pwd`, `grp`, `resource`, `tty`, `pty`) | The module does not exist | Import in a `try` that degrades, such as running unlocked |
| `open(p, "w", encoding="utf-8")`, `os.fdopen(fd, "a")` | Text mode writes `\r\n` | Add `newline="\n"` |
| `Path.write_text(text)` | Writes `\r\n`; `newline=` needs Python 3.10 | `path.write_bytes(text.encode("utf-8"))` |
| An entry script that prints note or source text | The console code page is not UTF-8, so a curly quote raises `UnicodeEncodeError` | The snippet below, in the `__main__` block |
| `/usr/bin/python3` or a bare `python3` in argv | Windows names it `python` or `py` | `sys.executable` |

The console snippet runs only on Windows, so macOS output is unchanged:

```python
if __name__ == "__main__":
    if sys.platform == "win32":  # the console code page is not UTF-8; note text often is
        for _stream in (sys.stdout, sys.stderr):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
```

## Habits the lint cannot check

- Store paths as POSIX keys: `posixpath` and `Path.as_posix()`, never `os.sep` or `str(path)` in a stored key.
- Close a SQLite connection or file handle before `os.replace` or `unlink`. Windows refuses both on an open file.
- NTFS and APFS both ignore case by default. Do not rely on `Notes.md` and `notes.md` being two files.
- `getattr(os, "O_NOFOLLOW", 0)` switches the link guard off on Windows. Where the open can follow a link (an append, a non-exclusive create), check `is_symlink()` first when the flag is absent.
- Windows has no `dir_fd`. Branch on `os.open in os.supports_dir_fd` and keep the `dir_fd` path for macOS.
- Symlink guards do not see Windows junctions. Say so where a guard matters.
- Tests that create symlinks skip on Windows, where creating one needs Developer Mode or admin rights:
  `unittest.skipIf(sys.platform == "win32", "...")`.
- Shell lines in SKILL.md assume Git Bash on Windows, which is what Claude Code uses there.
  Prefer a Python script over a pipeline when a step must also work from PowerShell.
- Commands in SKILL.md say `python3`. On Windows the user substitutes `python`; a script never relies on the name.
