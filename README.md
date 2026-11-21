# SunPower Solutions — Solar Installation Management System

One platform that takes a rooftop solar customer from first enquiry to the 20-year warranty:
leads and surveys, quotes from package templates, orders and payments, warehouse picking with
serial scanning, the technician field app, after-sales tickets, and the director's dashboard.

> **Status:** Phase 0a (foundation) complete. See [Roadmap](#roadmap).

## Requirements

- Node.js 20.11+ (tested on 24)
- pnpm 9 — `npm install -g pnpm@9.15.0`
- PostgreSQL 15+ running locally (tested on 18). **No Docker or Redis needed.**

## Setup (one command)

```bash
cp .env.example .env      # then edit DATABASE_URL / TEST_DATABASE_URL with your postgres password
pnpm setup                # install, create databases, apply migrations, seed demo data
pnpm dev                  # http://localhost:3000
```

If your Postgres password contains special characters, URL-encode them in `.env`
(`@` → `%40`, `#` → `%23`, `%` → `%25`, `:` → `%3A`, `/` → `%2F`).

Generate `AUTH_SECRET` with:

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"
```

Run the background worker (notifications and automations) in a second terminal:

```bash
pnpm worker
```

## Demo logins

All seeded users share the password in `SEED_USER_PASSWORD` (default `SunPower@123`).

| Role       | Email                     | Lands on     |
| ---------- | ------------------------- | ------------ |
| Admin      | `admin@sunpower.test`     | `/dashboard` |
| Director   | `director@sunpower.test`  | `/dashboard` |
| Sales      | `sales@sunpower.test`     | `/leads`     |
| Warehouse  | `warehouse@sunpower.test` | `/warehouse` |
| Technician | `tech@sunpower.test`      | `/jobs`      |
| Support    | `support@sunpower.test`   | `/tickets`   |

There are 15 technicians: `tech@`, `tech2@` … `tech15@sunpower.test`.

## Scripts

| Command                        | What it does                                                  |
| ------------------------------ | ------------------------------------------------------------- |
| `pnpm dev`                     | Next.js dev server                                            |
| `pnpm worker`                  | Outbox relay + job handlers (pg-boss on Postgres)             |
| `pnpm db:migrate`              | Create/apply a migration after editing `prisma/schema.prisma` |
| `pnpm db:seed`                 | Seed demo data (idempotent)                                   |
| `pnpm db:studio`               | Browse the database                                           |
| `pnpm typecheck` / `pnpm lint` | TypeScript (strict) / ESLint                                  |
| `pnpm test`                    | Vitest: unit + DB integration (resets `sunpower_test`)        |
| `pnpm test:e2e`                | Playwright against a production build on the test DB          |
| `pnpm gate`                    | The full quality gate                                         |

`pnpm test` and `pnpm test:e2e` **wipe and rebuild the `sunpower_test` database** on every run.
They refuse to run against a database with any other name. Your dev data in `sunpower_dev` is never touched.

## Architecture (short version)

```
src/
  app/                 Routes. Thin: pages, server actions and route handlers call services.
  server/
    services/          ALL business logic. Every function takes an Actor and checks permissions.
    state-machines/    Lead, survey, quote, order, pick list, job, ticket, subsidy transitions.
    auth/              Auth.js config, permission matrix, Actor, credential checks.
    audit/             writeAudit(tx, …): who, what, before, after, when — in the same transaction.
    jobs/              Transactional outbox → pg-boss queue → handlers (`pnpm worker`).
    notifications/     Provider interface (console in dev; WhatsApp/SMS in Phase 6).
    storage/           Provider interface (local disk in dev; S3 later). Uploads are sniffed and size-limited.
    db/                Prisma client and transaction helper.
  lib/                 Shared, framework-free helpers: money (paise), dates (IST, warranty), phone, Zod schemas.
prisma/
  schema.prisma        Full data model. Money = integer paise, power = watts, GST = basis points.
  migrations/
  seed/                Catalogue, 15 BOM package templates, users, stock, customers.
tests/
  unit/  db/  e2e/
```

Key rules:

- **Money** is integer paise everywhere; displayed with Indian grouping (`₹1,50,000`).
- **State changes** go through a state machine; illegal moves throw `IllegalTransitionError`.
- **Every state change** writes an `AuditLog` row in the same transaction.
- **Permissions** are enforced on the server (middleware for pages, services for data).
  Technicians never receive costs, margins or anyone's pay — fields are stripped server-side.
- **Background work** is written to an outbox table inside the same transaction, so nothing is lost.

## Roadmap

| Phase | Scope                                                        | Status |
| ----- | ------------------------------------------------------------ | ------ |
| 0a    | Repo, schema, seed, auth + roles, platform services          | Done   |
| 0b    | Design tokens, app shell, shared component library           | Next   |
| 1     | Sales: enquiry form, lead pipeline, survey, quotes, payments |        |
| 2     | Fulfilment: pick/pack, serial scanning, dispatch, warranty   |        |
| 3     | Technician field app                                         |        |
| 4     | After-sales tickets                                          |        |
| 5     | Director dashboard, finance, reporting                       |        |
| 6     | Hardening, real notifications, docs, full lifecycle demo     |        |
