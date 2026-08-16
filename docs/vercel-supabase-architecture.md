# Vercel + Supabase architecture (in progress)

The full rebuild: move storage, auth, and reads to Vercel + Supabase, and shrink
the Python service to a **job worker**. Neither Vercel nor Supabase can run the
engine (a `propagate()` run is minutes of heavy Python), so one small always-on
worker remains — but everything around it moves.

```
Browser
  │  (Supabase Auth session)
  ▼
Vercel — Next.js UI + API routes ──────────────┐
  reads: SELECT from Supabase (RLS by user)     │
  writes: INSERT a job row                       │
                                                 ▼
                                          Supabase Postgres
                                          backtests / decision_runs
                                          journal / jobs   (+ Auth, Realtime)
                                                 ▲
Python worker (Render/Railway/Fly) ──────────────┘
  poll jobs(status=queued) → run engine (writes files)
  → collect_artifacts() → SupabaseStore.sync() → mark job done
```

## Data model
`supabase/migrations/0001_init.sql` — `backtests`, `decision_runs`, `journal`,
`jobs`, each with RLS so a user only sees their own rows. JSONB payloads mirror
the current file structure, so the existing loaders map over cleanly.

## Auth
Supabase Auth (magic link / OAuth). The frontend holds a user session; Next.js
API routes query with the user's JWT so **RLS scopes every read**. The worker
uses the **service-role key** (bypasses RLS) and stamps `user_id` on every row.

## Read path (moves off Python)
The FastAPI read endpoints (`/api/backtests`, `/api/journal`, `/api/runs`) are
replaced by **Next.js route handlers** (`web/app/api/*/route.ts`) that `SELECT`
from Supabase. The frontend keeps its current `getJSON('/api/...')` calls, now
same-origin — `NEXT_PUBLIC_API_URL` is no longer needed for reads.

## Write path (the worker)
1. Frontend/API inserts a `jobs` row (`kind` = run | backtest | seed).
2. The worker polls `jobs` for `queued`, marks `running`.
3. It runs the existing engine (`propagate()` / `run_backtest()` / `seed_demo()`),
   which writes artifacts to disk.
4. `store.collect_artifacts(config, user_id)` reads them via the existing loaders;
   `SupabaseStore.sync()` upserts them.
5. Marks the job `done` (or `error`). Frontend sees results via poll/Realtime.

## Status — phased
- [x] **Slice 1 (this branch):** schema + RLS migration; Python write-store
  (`server/store.py` mappers + `SupabaseStore`) with offline tests; `worker` extra.
- [ ] **Slice 2 — worker loop:** `server/worker.py` that polls `jobs`, runs the
  engine, syncs, updates status. Reuses `store` + `demo` + `backtest.engine`.
- [ ] **Slice 3 — Next.js reads + Supabase client:** route handlers querying
  Supabase; point the frontend at them; drop `NEXT_PUBLIC_API_URL` for reads.
- [ ] **Slice 4 — Auth:** Supabase Auth on the frontend; RLS-scoped queries;
  a "trigger run/backtest" action that inserts a job row.

## Deploy (your accounts — I can't provision these)
1. **Supabase:** create a project → `supabase db push` (applies the migration).
   Note the project URL, `anon` key, and `service_role` key.
2. **Vercel:** set `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
3. **Worker host:** set `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, and `OPENAI_API_KEY`.

## Note
This supersedes parts of the earlier Render/FastAPI design: the FastAPI read
endpoints are replaced by Next.js routes, and `server/app.py` gives way to
`server/worker.py`. The engine, Gate A, vendors, and dashboard data-mappers are
reused unchanged.
