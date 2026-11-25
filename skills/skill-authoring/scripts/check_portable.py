#!/usr/bin/env python3
"""Cross-OS lint for skill scripts (references/cross-os.md).

    python3 check_portable.py <paths...>   # files or folders; exit 1 on any finding

Skills are built on macOS and must keep working there; Windows support comes next
where it costs little, and Linux after it. Each rule below is a construct that
works on macOS and breaks on Windows, with the fix that keeps both working:

  posix-attr        os.O_NOFOLLOW, os.getuid and friends do not exist on Windows;
                    use getattr(os, "O_NOFOLLOW", 0) or guard by platform
  posix-import      fcntl, termios, pwd, grp, resource, tty and pty imported
                    outside a try or a platform check
  text-write        a text-mode write without newline="\\n" writes CRLF on Windows;
                    Path.write_text has no newline argument before Python 3.10, so
                    use write_bytes(text.encode("utf-8")) or open(..., newline="\\n")
  console-utf8      an entry script that prints without setting its console
                    streams to UTF-8 on Windows
  fixed-interpreter "/usr/bin/python..." hardcoded; use sys.executable
  unparsed          a file that cannot be read or parsed is a finding, never clean

A missing path argument exits 2. A platform check counts as a guard whichever
branch the call sits in, so a call under `if sys.platform == "win32"` passes.

Test files skip text-write and console-utf8: they write throwaway fixtures and
print nothing a user reads. Fixture trees are corpora and are skipped. A line that
must stay takes `# portable: exempt <reason>` on it or in the comment block above.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

POSIX_OS_ATTRS = {"O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK", "getuid", "geteuid", "getgid", "fork",
                  "setsid", "killpg", "getpgid", "setpgrp"}
POSIX_MODULES = {"fcntl", "termios", "pwd", "grp", "resource", "tty", "pty"}
SKIP_PARTS = {"skills-archive", "__archive", "fixtures", "node_modules", ".git", "__pycache__"}
EXEMPT = "# portable: exempt"


def is_test(path: Path) -> bool:
    return "tests" in path.parts or path.name.startswith("test_")


def guarded(node: ast.AST, parents: dict) -> bool:
    """Inside a try body, or under an if that tests the platform or an attribute."""
    child, cur = node, parents.get(node)
    while cur is not None:
        if isinstance(cur, ast.Try) and child in cur.body:
            return True
        if isinstance(cur, ast.If):
            test = ast.unparse(cur.test) if hasattr(ast, "unparse") else ""
            if any(k in test for k in ("os.name", "sys.platform", "hasattr", "platform.system")):
                return True
        child, cur = cur, parents.get(cur)
    return False


def write_mode(call: ast.Call) -> str | None:
    """The mode string of an open-like call, or None when it is not one."""
    f = call.func
    name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
    if name not in ("open", "fdopen"):
        return None
    # open(path, mode), io.open(path, mode), os.fdopen(fd, mode); Path.open(mode).
    module_call = isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) \
        and f.value.id in ("io", "os", "codecs")
    pos = 1 if isinstance(f, ast.Name) or module_call else 0
    mode = None
    if len(call.args) > pos and isinstance(call.args[pos], ast.Constant):
        mode = call.args[pos].value
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            mode = kw.value.value
    return mode if isinstance(mode, str) else None


def lint_file(path: Path) -> list[tuple[int, str, str]]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError, RecursionError) as exc:
        # A file the lint cannot read is never reported clean.
        return [(1, "unparsed", f"could not be checked: {type(exc).__name__}")]
    lines = source.splitlines()
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    test = is_test(path)
    found: list[tuple[int, str, str]] = []

    def exempt(lineno: int) -> bool:
        i = lineno - 1
        if 0 <= i < len(lines) and EXEMPT in lines[i]:
            return True
        i -= 1
        while i >= 0 and lines[i].strip().startswith("#"):
            if EXEMPT in lines[i]:
                return True
            i -= 1
        return False

    def add(node: ast.AST, rule: str, msg: str) -> None:
        if not exempt(node.lineno):
            found.append((node.lineno, rule, msg))

    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == "os" and node.attr in POSIX_OS_ATTRS
                and not guarded(node, parents)):
            add(node, "posix-attr", f"os.{node.attr} is absent on Windows; "
                f"use getattr(os, \"{node.attr}\", ...) or a platform check")
        elif isinstance(node, (ast.Import, ast.ImportFrom)) and not guarded(node, parents):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for name in names:
                if name.split(".")[0] in POSIX_MODULES:
                    add(node, "posix-import", f"{name} does not exist on Windows; "
                        "import it in a try that degrades")
        elif isinstance(node, ast.Call) and not test:
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "write_text":
                add(node, "text-write", "write_text writes CRLF on Windows and has no "
                    "newline argument before 3.10; use write_bytes(text.encode(\"utf-8\"))")
                continue
            mode = write_mode(node)
            if (mode and "b" not in mode and any(c in mode for c in "wax+")
                    and not any(kw.arg == "newline" for kw in node.keywords)):
                add(node, "text-write", f"text-mode '{mode}' write without newline=\"\\n\" "
                    "writes CRLF on Windows")
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and node.value.startswith("/usr/bin/python")):  # portable: exempt the rule's own pattern
            add(node, "fixed-interpreter", f"{node.value} is macOS/Linux only; use sys.executable")

    if not test and "__main__" in source and "print(" in source and "reconfigure(" not in source:
        main_line = next((i + 1 for i, ln in enumerate(lines) if "__main__" in ln), 1)
        if not exempt(main_line):
            found.append((main_line, "console-utf8", "entry script prints but never sets its "
                          "console streams to UTF-8 on Windows (see references/cross-os.md)"))
    return sorted(found)


def collect(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        p = Path(raw)
        candidates = sorted(p.rglob("*.py")) if p.is_dir() else [p]
        for c in candidates:
            if c.suffix == ".py" and not SKIP_PARTS.intersection(c.parts):
                files.append(c)
    return files


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if args else 2
    missing = [a for a in args if not Path(a).exists()]
    if missing:
        print(f"check_portable: no such path: {', '.join(missing)}", file=sys.stderr)
        return 2
    total = 0
    for path in collect(args):
        for lineno, rule, msg in lint_file(path):
            print(f"{path}:{lineno}: {rule}: {msg}")
            total += 1
    print(f"check_portable: {total} finding(s)")
    return 1 if total else 0


if __name__ == "__main__":
    if sys.platform == "win32":  # the console code page is not UTF-8; paths often are not ASCII
        for _stream in (sys.stdout, sys.stderr):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
