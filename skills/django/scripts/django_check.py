#!/usr/bin/env python3
"""Deterministic Django/DRF footgun checker - AST-based, stdlib only.

EXECUTE this. It does NOT replace `manage.py check --deploy` (Django's own
security checklist) - it catches what that misses: the DRF defaults that fail
OPEN, and the serializer patterns that quietly widen your API.

Parsed with `ast`, not regex: it reads structure, so `fields = "__all__"` is
found wherever it lives, and there is no catastrophic-backtracking surface at
all. No imports of your code, no settings loaded, no DB touched - it never
executes a line of what it reads.

    python3 django_check.py <path>...      # exit 1 on any FAIL
    python3 django_check.py --json <path>

The rules encode the failures that actually ship:
  - DRF's default permission is AllowAny. Forget DEFAULT_PERMISSION_CLASSES and
    the entire API is public - no error, no warning, just open.
  - `fields = "__all__"` re-exposes every field you add to the model LATER.
    Today's model has no `is_admin`; tomorrow's does, and the API now serves it.
  - `read_only_fields` omissions are mass-assignment: a writable `is_staff` lets
    a user PATCH themselves into staff.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

FAIL, WARN = "FAIL", "WARN"

# Fields nobody should be able to write through a serializer.
PRIVILEGE_FIELDS = {"is_staff", "is_superuser", "is_active", "password", "user_permissions", "groups"}

SERIALIZER_BASES = {"ModelSerializer", "HyperlinkedModelSerializer"}
VIEW_BASES = {"ModelViewSet", "ViewSet", "GenericViewSet", "APIView", "ListAPIView", "RetrieveAPIView"}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    severity: str
    rule: str
    message: str


def _const(node: ast.AST) -> object:
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return None


class Visitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = str(path)
        self.findings: list[Finding] = []
        self.uses_drf = False          # any serializer/viewset subclass seen
        self.saw_rest_framework = False # a REST_FRAMEWORK setting seen
        self.saw_permission_default = False

    def add(self, node: ast.AST, severity: str, rule: str, message: str) -> None:
        self.findings.append(Finding(self.path, getattr(node, "lineno", 1), severity, rule, message))

    # Annotated assignments (`ALLOWED_HOSTS: list[str] = [...]`) are modern style -
    # and this skill's own scaffold uses them. Route them through the same logic
    # as a bare assignment, or every settings rule silently misses them.
    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and node.value is not None:
            self._check_setting(node, node.target.id, node.value)
        self.generic_visit(node)

    # --- module-level settings -------------------------------------------
    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                self._check_setting(node, target.id, node.value)
        self.generic_visit(node)

    def _check_setting(self, node: ast.AST, name: str, value_node: ast.AST) -> None:
        value = _const(value_node)

        if name == "SECRET_KEY" and isinstance(value, str) and value:
            self.add(
                node, FAIL, "hardcoded-secret-key",
                "SECRET_KEY is a literal in source. It signs sessions and password-reset tokens; in git it is compromised. "
                "Read it from the environment and rotate this one.",
            )
        if name == "DEBUG" and value is True:
            self.add(
                node, WARN, "debug-true",
                "DEBUG = True. Fine locally; in production it serves tracebacks with settings and SQL to anyone who triggers a 500.",
            )
        if name == "ALLOWED_HOSTS" and isinstance(value, list) and "*" in value:
            self.add(
                node, FAIL, "allowed-hosts-wildcard",
                "ALLOWED_HOSTS = ['*'] disables the Host header check, enabling cache-poisoning and password-reset poisoning.",
            )
        # Both the current name and the pre-3.5.0 django-cors-headers alias.
        if name in {"CORS_ALLOW_ALL_ORIGINS", "CORS_ORIGIN_ALLOW_ALL"} and value is True:
            self.add(
                node, FAIL, "cors-wildcard",
                f"{name} = True sends Access-Control-Allow-Origin: * to every site. Combined with "
                "CORS_ALLOW_CREDENTIALS = True it reflects the origin and leaks credentialed responses. Allowlist origins.",
            )
        if name in {"SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE"} and value is False:
            self.add(node, WARN, "insecure-cookie", f"{name} = False sends the cookie over plain HTTP.")

        if name == "REST_FRAMEWORK" and isinstance(value_node, ast.Dict):
            self.saw_rest_framework = True
            self._check_drf_settings(node, value_node)

    def _check_drf_settings(self, node: ast.AST, dict_node: ast.Dict) -> None:
        keys = {_const(k) for k in dict_node.keys}
        if "DEFAULT_PERMISSION_CLASSES" in keys:
            self.saw_permission_default = True

        if "DEFAULT_PERMISSION_CLASSES" not in keys:
            self.add(
                node, FAIL, "drf-permissions-unset",
                "REST_FRAMEWORK has no DEFAULT_PERMISSION_CLASSES. DRF's default is AllowAny - every view without an explicit "
                "permission_classes is PUBLIC, silently. Set it to IsAuthenticated and opt views out deliberately.",
            )
        else:
            for k, v in zip(dict_node.keys, dict_node.values):
                if _const(k) == "DEFAULT_PERMISSION_CLASSES":
                    val = _const(v)
                    if isinstance(val, (list, tuple)) and any("AllowAny" in str(x) for x in val):
                        self.add(
                            node, FAIL, "drf-permissions-allowany",
                            "DEFAULT_PERMISSION_CLASSES is AllowAny - the API is public by default. Invert it: default to "
                            "IsAuthenticated, and mark the genuinely public views.",
                        )

        if "DEFAULT_PAGINATION_CLASS" not in keys:
            self.add(
                node, WARN, "drf-no-pagination",
                "No DEFAULT_PAGINATION_CLASS. List endpoints will serialize the entire table - fine at 10 rows, an outage at 10 million.",
            )

    # --- classes: serializers and views ----------------------------------
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        bases = {b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "") for b in node.bases}

        if bases & SERIALIZER_BASES:
            self.uses_drf = True
            self._check_serializer(node)
        if bases & VIEW_BASES:
            self.uses_drf = True
            self._check_view(node)

        self.generic_visit(node)

    def _check_serializer(self, node: ast.ClassDef) -> None:
        meta = next(
            (n for n in node.body if isinstance(n, ast.ClassDef) and n.name == "Meta"),
            None,
        )
        if meta is None:
            return

        fields = read_only = None
        depth = None
        write_only: set[str] = set()   # extra_kwargs / declared fields marked write_only
        for stmt in meta.body:
            if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name):
                key = stmt.targets[0].id
                if key == "fields":
                    fields = (_const(stmt.value), stmt)
                elif key == "read_only_fields":
                    read_only = _const(stmt.value)
                elif key == "exclude":
                    self.add(
                        stmt, WARN, "serializer-exclude",
                        "Meta.exclude is a denylist: any field added to the model later is exposed automatically. "
                        "List `fields` explicitly instead.",
                    )
                elif key == "depth":
                    depth = (_const(stmt.value), stmt)
                elif key == "extra_kwargs":
                    kw = _const(stmt.value)
                    if isinstance(kw, dict):
                        write_only |= {f for f, opts in kw.items() if isinstance(opts, dict) and opts.get("write_only")}

        # A field declared on the serializer body as write_only (e.g.
        # password = serializers.CharField(write_only=True)) is also safe to write.
        write_only |= self._declared_write_only(node)

        if fields and fields[0] == "__all__":
            self.add(
                fields[1], FAIL, "serializer-fields-all",
                f"{node.name}: fields = '__all__' exposes every model field, including ones added later. A future `internal_notes` "
                "or `is_admin` column ships to the API the day it is created. Enumerate the fields.",
            )

        if fields and isinstance(fields[0], (list, tuple)):
            safe = set(read_only or ()) | write_only
            leaked = (set(fields[0]) & PRIVILEGE_FIELDS) - safe
            if leaked:
                self.add(
                    fields[1], FAIL, "serializer-writable-privilege-field",
                    f"{node.name}: {', '.join(sorted(leaked))} is writable. A user can PATCH their own privileges. "
                    "Put it in read_only_fields (or, for password, mark it write_only), or drop it from the serializer.",
                )

        if depth and isinstance(depth[0], int) and depth[0] > 0:
            self.add(
                depth[1], WARN, "serializer-depth",
                f"{node.name}: Meta.depth={depth[0]} auto-nests relations and generates an N+1 query per row. "
                "Use an explicit nested serializer plus select_related/prefetch_related on the queryset.",
            )

    def _declared_write_only(self, node: ast.ClassDef) -> set[str]:
        """Fields declared on the serializer body with write_only=True."""
        out: set[str] = set()
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name) and isinstance(stmt.value, ast.Call):
                for kw in stmt.value.keywords:
                    if kw.arg == "write_only" and _const(kw.value) is True:
                        out.add(stmt.targets[0].id)
        return out

    def _check_view(self, node: ast.ClassDef) -> None:
        perms = None
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name) and stmt.targets[0].id == "permission_classes":
                perms = _const(stmt.value)
                # An explicit AllowAny / [] at the view level is not "safe because set".
                flat = str(perms) if perms is not None else ast.dump(stmt.value)
                if "AllowAny" in flat or perms in ([], ()):
                    self.add(
                        stmt, FAIL, "view-permission-allowany",
                        f"{node.name}: permission_classes is AllowAny (or empty) - this endpoint is explicitly public. "
                        "If that is intended, fine; if it was copied from a template, it is a hole.",
                    )
                break
        else:
            self.add(
                node, WARN, "view-no-permissions",
                f"{node.name} sets no permission_classes. It inherits DEFAULT_PERMISSION_CLASSES - which is AllowAny unless you "
                "changed it. Confirm the global default is restrictive, or set one here.",
            )

        # N+1 heuristic: a queryset of `.all()` with no select_related/prefetch_related
        # anywhere in the class. Cheap, and it catches the common case.
        src = ast.dump(node)
        if "'all'" in src and "select_related" not in src and "prefetch_related" not in src:
            self.add(
                node, WARN, "possible-n-plus-1",
                f"{node.name}: queryset uses .all() with no select_related/prefetch_related. If the serializer touches a "
                "ForeignKey or reverse relation, this is one query per row.",
            )

    # --- raw SQL ----------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        fn = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")

        if fn in {"raw", "execute"} and node.args:
            arg = node.args[0]
            interpolated = (
                isinstance(arg, ast.JoinedStr)  # f-string
                or (isinstance(arg, ast.BinOp) and isinstance(arg.op, (ast.Mod, ast.Add)))
                or (isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) and arg.func.attr == "format")
            )
            if interpolated:
                self.add(
                    node, FAIL, "sql-injection",
                    "Raw SQL built by string interpolation. Pass parameters instead: cursor.execute(sql, [value]) - "
                    "the driver quotes them, f-strings do not.",
                )

        if fn == "extra":
            self.add(node, WARN, "queryset-extra", ".extra() is legacy and injection-prone. Use annotate/Func/RawSQL with params.")

        self.generic_visit(node)


def check_file(path: Path) -> tuple[list[Finding], Visitor | None]:
    try:
        if path.stat().st_size > 1_000_000:
            return [], None
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except (OSError, SyntaxError, RecursionError) as exc:
        return [Finding(str(path), getattr(exc, "lineno", 0) or 0, WARN, "unparseable", f"Could not parse: {exc}")], None

    v = Visitor(path)
    try:
        v.visit(tree)
    except RecursionError:
        return [Finding(str(path), 0, WARN, "too-deep", "AST too deeply nested to analyze.")], None
    return v.findings, v


def iter_targets(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    skip = {".git", "node_modules", ".venv", "venv", "migrations", "__pycache__"}
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            out.extend(
                f
                for f in sorted(p.rglob("*.py"))
                if not f.is_symlink() and not any(part in skip for part in f.parts)
            )
        elif p.suffix == ".py":
            out.append(p)
    return out


def safe(path: str) -> str:
    return path.replace("\n", "\\n").replace("\r", "\\r")


def main() -> int:
    ap = argparse.ArgumentParser(description="Django/DRF footgun checker (AST-based, stdlib only).")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--warn-only", action="store_true")
    args = ap.parse_args()

    targets = iter_targets(args.paths)
    if not targets:
        print("no .py files found", file=sys.stderr)
        return 0

    findings: list[Finding] = []
    visitors: list[Visitor] = []
    for t in targets:
        fs, v = check_file(t)
        findings.extend(fs)
        if v is not None:
            visitors.append(v)

    # Run-level: DRF is used somewhere but NO file set DEFAULT_PERMISSION_CLASSES
    # and NO file even had a REST_FRAMEWORK block - the "forgot it entirely" case,
    # which is invisible per-file because the settings live in a different file.
    # Only meaningful when the run is broad enough to include settings (a directory,
    # or >1 file); linting a lone viewset would false-positive, so we gate on that.
    if len(targets) > 1 or any(t.is_dir() for t in map(Path, args.paths)):
        drf_used = any(v.uses_drf for v in visitors)
        perms_set = any(v.saw_permission_default for v in visitors)
        rf_seen = any(v.saw_rest_framework for v in visitors)
        if drf_used and not perms_set and not rf_seen:
            # FAIL when a settings file WAS in scope and still lacks the config -
            # that is a real hole. WARN when no settings*.py was scanned at all,
            # because the config may simply live in a file the run did not include.
            saw_settings = any(Path(v.path).name.startswith("settings") or "settings" in Path(v.path).parts
                               for v in visitors)
            sev = FAIL if saw_settings else WARN
            tail = ("" if saw_settings else
                    " (No settings*.py was in this run - if your DEFAULT_PERMISSION_CLASSES lives elsewhere, scan it too.)")
            findings.append(Finding(
                str(next(v.path for v in visitors if v.uses_drf)), 1, sev, "drf-no-permission-config",
                "DRF is used but no DEFAULT_PERMISSION_CLASSES (nor any REST_FRAMEWORK block) was found in the scanned files. "
                "DRF defaults to AllowAny, so the API is public by default. Set a restrictive default in settings." + tail,
            ))

    fails = [f for f in findings if f.severity == FAIL]

    if args.json:
        print(json.dumps({"findings": [asdict(f) for f in findings], "files": len(targets)}, indent=2))
    else:
        for f in sorted(findings, key=lambda f: (f.path, f.line)):
            print(f"{safe(f.path)}:{f.line}: {f.severity}: {f.rule}: {f.message}")
        print(f"\n{len(fails)} fail, {len(findings) - len(fails)} warn, {len(targets)} file(s)")
        if not findings:
            print("clean - now run `manage.py check --deploy` and `makemigrations --check --dry-run`, which this does not duplicate.")

    return 1 if fails and not args.warn_only else 0


if __name__ == "__main__":
    sys.exit(main())
