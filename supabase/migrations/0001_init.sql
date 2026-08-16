-- TradingAgents schema for Supabase (Postgres).
-- Apply with the Supabase CLI:  supabase db push
-- Artifacts are stored as rows with JSONB payloads (mirroring the file-based
-- structure), scoped per user via row-level security.

create extension if not exists "pgcrypto";

-- Gate A backtests -----------------------------------------------------------
create table if not exists public.backtests (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users (id) on delete cascade,
  name       text not null,
  verdict    text,
  pit        boolean,
  summary    jsonb not null default '{}'::jsonb,
  equity     jsonb not null default '[]'::jsonb,
  trades     jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  unique (user_id, name)
);
create index if not exists backtests_user_created_idx
  on public.backtests (user_id, created_at desc);

-- Saved propagate() decision runs -------------------------------------------
create table if not exists public.decision_runs (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users (id) on delete cascade,
  ticker         text not null,
  trade_date     text not null,
  rating         text,
  final_decision text,
  stages         jsonb not null default '[]'::jsonb,
  created_at     timestamptz not null default now(),
  unique (user_id, ticker, trade_date)
);
create index if not exists decision_runs_user_date_idx
  on public.decision_runs (user_id, trade_date desc);

-- Decision journal (track record) -------------------------------------------
create table if not exists public.journal (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references auth.users (id) on delete cascade,
  ticker       text not null,
  trade_date   text not null,
  rating       text,
  status       text not null default 'pending',       -- pending | resolved
  raw_return   double precision,
  alpha_return double precision,
  holding      text,
  reflection   text,
  decision     text,
  created_at   timestamptz not null default now(),
  unique (user_id, ticker, trade_date)
);

-- Background job queue --------------------------------------------------------
create table if not exists public.jobs (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users (id) on delete cascade,
  kind       text not null,                            -- run | backtest | seed
  status     text not null default 'queued',           -- queued|running|done|error
  params     jsonb not null default '{}'::jsonb,
  error      text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists jobs_status_idx on public.jobs (status, created_at);

-- Row-level security: each user sees and manages only their own rows.
-- The worker connects with the service-role key (bypasses RLS) and sets user_id.
alter table public.backtests     enable row level security;
alter table public.decision_runs enable row level security;
alter table public.journal       enable row level security;
alter table public.jobs          enable row level security;

create policy "own_backtests" on public.backtests
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own_decision_runs" on public.decision_runs
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own_journal" on public.journal
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own_jobs" on public.jobs
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
