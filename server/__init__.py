"""FastAPI backend for TradingAgents.

The "live server-side" tier behind the Vercel/Next.js frontend: it serves the
artifacts the framework produces (backtests, journal, decision runs) as JSON and
triggers live ``propagate()`` runs as background jobs. Runs on any always-on host
(Render/Railway/Fly/VM) — not Vercel serverless, which can't hold a multi-minute
LLM job.
"""
