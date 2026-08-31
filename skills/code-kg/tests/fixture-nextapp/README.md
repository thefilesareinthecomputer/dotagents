# Fixture NextApp

A small Next.js 15 App Router frontend for an invoicing workspace. It exists
as a parser fixture: the code is realistic but is never installed or compiled.

## Layout

- `src/app/` holds the App Router tree: pages, layouts, route handlers, and
  the root `middleware`.
- `src/components/` is a barrel of shared UI: buttons, tables, modals, form
  fields, and cell renderers.
- `src/hooks/` carries reusable client hooks for debouncing, pagination, async
  loading, and toggles.
- `src/contexts/` provides the signed-in user context.
- `src/services/` wraps the HTTP surface: invoices, customers, auth, settings,
  formatting, and CSRF handling.
- `src/lib/` holds framework-free helpers: the fetch client, currency and date
  math, environment access, and the server-side data layer.

## Scripts

- `npm run dev` starts the dev server.
- `npm run build` produces a production build.
- `npm run observe` runs the agent observation tool before shipping.

## Data

Seed rows live under `data/`. The test harness generates a local SQLite cache
at setup; no binary stores are committed.
