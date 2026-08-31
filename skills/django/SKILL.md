---
name: django
description: Builds, operates, and hardens Django and Django REST Framework projects - from a cold start or inside an existing codebase. Use when scaffolding a new Django/DRF project, when adding or changing models, serializers, viewsets, permissions, or migrations, when inheriting an unfamiliar Django repo and needing to orient in it, when an endpoint is slow or the ORM is issuing hundreds of queries (N+1), when a migration needs to ship without downtime, when an API is or might be exposed (DRF's default permission is AllowAny - it fails OPEN), and when reviewing Django code before merge or deploy. Ships a deterministic AST-based checker (scripts/django_check.py) for the DRF footguns that `manage.py check --deploy` does not catch, and drives Django's own tooling rather than duplicating it.
license: MIT
---

# django

Django is safe by default. **DRF is not.** Its default permission class is
`AllowAny`, so a viewset that forgets `permission_classes` is a public endpoint -
no error, no warning, no log line. That single default causes more real exposure
than every other item in this skill combined, and it is why the checker FAILs a
`REST_FRAMEWORK` block with no `DEFAULT_PERMISSION_CLASSES`.

The other three that ship constantly, all mechanical, all caught by the gate:
`fields = "__all__"` (a standing promise to expose every column you ever add),
writable `is_staff` (a user can PATCH themselves into staff), and `.all()` with
no `select_related` (one query per row).

## First: which situation is this?

**Existing project → orient before touching anything.** Read
`references/runbook.md` § *Inheriting an existing project*. Their conventions
outrank this skill's templates: a consistent codebase with a pattern you dislike
beats one with two patterns, and the second is the one you added. Run
`manage.py check`, `showmigrations`, `makemigrations --check --dry-run`, then the
checker - and **triage**, do not sweep. A repo-wide fix-everything diff is
unreviewable and gets reverted.

**Cold start → scaffold.** Read `references/scaffold.md`: layout, split settings,
the DRF config that inverts the unsafe defaults, model/serializer/viewset
patterns. The templates already pass the checker.

Either way, the same gate applies to what you write.

## The rules

**Permissions fail open.** Set `DEFAULT_PERMISSION_CLASSES` to `IsAuthenticated`
in settings and let genuinely public endpoints opt out, visibly, one at a time.
Then remember that "authenticated" is not "authorized": a permission class does
not stop user A fetching user B's order by id. **Scope the queryset**
(`filter(customer=self.request.user)`), do not rely on the detail view.

**Serializers are an exposure surface.** Enumerate `fields`. Never `"__all__"`,
never `exclude` - both are denylists that auto-expose whatever you add later.
Everything privilege-bearing or server-owned goes in `read_only_fields`.

**The ORM is lazy, and that is where the queries hide.** A queryset does nothing
until evaluated, so `.count()` in a loop is one query per iteration and a nested
serializer is one query per row. `select_related` for forward FKs (JOIN),
`prefetch_related` for reverse/M2M (second query). Using the wrong one silently
does nothing. `Meta.depth` is a per-row query generator wearing a shortcut's
clothes.

**Migrations must be safe against the code already deployed**, not just the code
you are deploying - a deploy is not atomic, so both run at once. Read
`sqlmigrate` output before applying. Adding NOT NULL, adding an index, and
renaming a column all lock or break running instances; each has a two-release
form. Details in the runbook.

**Money is `DecimalField`.** `on_delete` has no safe default - `CASCADE` on a
user FK means deleting one user silently deletes their orders.

## Gate the output

EXECUTE:

```bash
python3 scripts/django_check.py <path>...    # exit 1 on any FAIL
python3 scripts/django_check.py --json .
```

AST-based, stdlib, offline. It never imports or executes the code it reads - it
parses it. (That matters: importing a `settings.py` to inspect it would *run* it.)

Known limits, stated so you do not over-trust it: it flags interpolated SQL **at
the call site only** (no dataflow - `sql = "..." % x; execute(sql)` slips through);
it does not catch `SECRET_KEY = os.environ.get("KEY", "insecure-default")` (the
insecure-*fallback*, only bare literals), `@csrf_exempt`, `mark_safe` on request
data, or `FloatField` for money. It is a footgun tripwire, not a proof of safety.

It is **not** a replacement for Django's own checks, which are better at their
job. Run both - they are complementary and neither is a superset:

```bash
python manage.py check --deploy                    # SSL, HSTS, cookies, DEBUG - the deployment settings
python manage.py makemigrations --check --dry-run  # a model changed with no migration (CI gate)
pytest                                             # with django_assert_num_queries on list endpoints
```

`check --deploy` audits the *deployment*; `django_check.py` audits the *API
surface* - permissions, serializer exposure, mass assignment, injection. Django's
checker knows nothing about DRF.

## The judgment pass

1. **Is authorization actually enforced, or just authentication?** The most common
   real breach in a DRF app is an authenticated user reading another user's
   objects by id. Queryset scoping is the fix; a permission class alone is not.
2. **What does this migration do to the currently-running code?** Not the new code.
3. **Is the N+1 measured or assumed?** `CaptureQueriesContext` or
   `django_assert_num_queries`. Then pin it with a test so it cannot regress.
4. **Does the API contract change?** Narrowing `fields = "__all__"` to an explicit
   list is a *behavior change* dressed as a cleanup - it can break a client that
   relied on a field you just removed. Check what is actually consumed first.
5. **Is the admin exposed?** `/admin/` with a weak password is a full database UI.

## Verify

```bash
python3 -m unittest discover skills/django/tests
```

Fixtures: `bad_api.py` (every footgun - must FAIL) and `good_api.py` (correct -
must be **silent**). The quiet test is the one that matters; a checker that fires
on correct code gets muted, and a muted checker protects nothing. One test asserts
the script contains no `exec`/`eval`/`import`-of-target - it reads code, it never
runs it.

## Ecosystem note (verified 2026-07-14)

The Django agent-tooling ecosystem is thin and one shop carries it:
**Vinta Software** - `django-ai-plugins` (`cdrf-expert`, `django-safe-migration`)
and `django-ai-boost` (MIT, an introspection MCP: schema, migration state, URL
patterns, read-only ORM queries). `django-ai-plugins` **ships with no LICENSE
file**, which blocks bundling it. There is no Django plugin in
`claude-plugins-official`.

Beware the direction trap: `django-mcp-server`, `django-rest-framework-mcp`, and
`django-admin-mcp` expose *your* API **as** MCP tools so an LLM can call it. That
is not help writing Django. Authoring help exists only as skills.
