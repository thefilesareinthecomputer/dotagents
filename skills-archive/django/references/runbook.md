# Operating a Django project

Two entry points: you inherited a codebase, or you are running one you built.
Start with the first - **most work is brownfield**, and the fastest way to do
damage is to apply a template to a project that already made different choices.

## Contents

- [Inheriting an existing project](#inheriting-an-existing-project)
- [Migrations](#migrations)
- [Hunting N+1](#hunting-n1)
- [Debugging](#debugging)
- [Testing](#testing)
- [Pre-deploy](#pre-deploy)

## Inheriting an existing project

**Read before you write. Their conventions beat this skill's templates** - a
consistent codebase with a pattern you dislike is worth more than a codebase
with two patterns, one of which you introduced.

Orient in this order:

```bash
# 1. What is this, and does it even boot?
ls */settings* config/settings/ 2>/dev/null   # settings layout: single file or split?
grep -rn "DJANGO_SETTINGS_MODULE" manage.py wsgi.py asgi.py 2>/dev/null
python manage.py check                        # does it import cleanly?

# 2. What are the apps, and which are theirs vs third-party?
python manage.py showmigrations               # apps + migration state in one view
python manage.py diffsettings --output unified | head -50   # what they changed from Django defaults

# 3. Is the DB in sync with the code?
python manage.py makemigrations --check --dry-run    # exit 1 = a model change has no migration
python manage.py showmigrations --plan | grep -c '\[ \]'   # count unapplied

# 4. What is already broken, security-wise?
python manage.py check --deploy               # Django's own security checklist
python3 scripts/django_check.py .             # the DRF footguns Django does not check
```

Then **triage rather than fix everything**. A repo-wide `django_check.py` run on
a mature project will return dozens of findings; changing all of them in one
sweep is unreviewable and will get reverted. In order:

1. **Fail-open security first** - `drf-permissions-unset`, `allowed-hosts-wildcard`,
   `sql-injection`, `serializer-writable-privilege-field`. These are live
   exposure, and each is a small, isolated diff.
2. **`fields = "__all__"`** - but check what the API currently returns *before*
   enumerating fields, or you will break a client that depended on a field you
   dropped. This one is a behavior change disguised as a cleanup.
3. **Performance** (`possible-n-plus-1`, pagination) - measure first, see below.
4. **Style/consistency** - usually not worth a diff at all.

The `view-no-permissions` warning is noise **if** their global default is already
`IsAuthenticated`. Check `settings` first; if the global default is restrictive,
per-view `permission_classes` is optional and the warning is informational.

## Migrations

The dangerous ones, and what actually goes wrong:

```bash
python manage.py makemigrations --check --dry-run   # CI gate: model changed, migration missing
python manage.py makemigrations app_name            # generate
python manage.py sqlmigrate app_name 0012           # READ THE SQL before running it
python manage.py migrate                            # apply
python manage.py migrate app_name 0011              # roll BACK to 0011 (if reversible)
```

`sqlmigrate` is the step people skip and then regret. Read the SQL, because these
lock:

- **Adding a NOT NULL column with a default** rewrites the whole table on older
  Postgres and locks it. Add nullable → backfill in batches → set NOT NULL.
- **Adding an index** locks writes. Use `AddIndexConcurrently` (Postgres) in a
  `SeparateDatabaseAndState`/`atomic = False` migration.
- **Renaming a column** breaks every running instance of the old code the moment
  it applies. Deploys are not atomic: old and new code run simultaneously. Do it
  in two releases - add new, write both, backfill, switch reads, drop old.
- **`RunPython` without `reverse_code`** is a one-way door. Provide the reverse
  or state loudly that it is irreversible.

The general rule for zero-downtime: **a migration must be safe against the code
that is currently deployed, not just the code you are deploying.**

## Hunting N+1

Do not guess. Count:

```python
from django.test.utils import CaptureQueriesContext
from django.db import connection

with CaptureQueriesContext(connection) as ctx:
    response = client.get("/api/orders/")
print(len(ctx.captured_queries))     # ~4 is fine; 200 means one query per row
```

Lock it in a test so it cannot regress:

```python
def test_order_list_query_count(client, django_assert_num_queries):
    with django_assert_num_queries(4):
        client.get("/api/orders/")
```

That assertion is worth more than any amount of `select_related` discipline,
because it fails the day someone adds a nested serializer field.

The fix, once located: `select_related` for forward FK (JOIN), `prefetch_related`
for reverse/M2M (second query). Using the wrong one does nothing and looks like
it worked. `django-debug-toolbar` in dev shows the counts per request; `nplusone`
raises on them.

## Debugging

```bash
python manage.py shell_plus --print-sql   # django-extensions: see the SQL each ORM call emits
python manage.py dbshell                  # straight to psql
python manage.py showmigrations app       # what is applied
```

```python
print(queryset.query)          # the SQL that WILL run - querysets are lazy
print(queryset.explain())      # the plan; where the missing index shows up
```

Laziness is the source of most ORM confusion: a queryset does nothing until it
is iterated, sliced, or `len()`d. Which is also why `.count()` inside a loop is
one query per iteration.

## Testing

```bash
pytest                                  # pytest-django
pytest --reuse-db                       # skip teardown/recreate; much faster loop
pytest -k order --lf                    # last failures only
```

Use `pytest.mark.django_db` for DB access, factories (`factory_boy`) over
fixtures, and `django_assert_num_queries` on every list endpoint. Test the
**permission denial** path, not just the happy path - the whole point of the DRF
default-deny setup is that a mistake shows up as a 403 in a test rather than a
public endpoint in production.

## Pre-deploy

```bash
python manage.py check --deploy         # Django's security checklist: SSL, HSTS, cookies, DEBUG
python manage.py makemigrations --check --dry-run   # no unmigrated model changes
python manage.py collectstatic --noinput
python3 scripts/django_check.py .       # the DRF footguns check --deploy does not know about
```

`check --deploy` and `django_check.py` are complementary and neither is a superset:
Django's checks the *deployment* settings (SSL redirect, HSTS, cookie flags,
DEBUG); this skill's checks the *API surface* (permissions, serializer exposure,
mass assignment, injection). Run both.
