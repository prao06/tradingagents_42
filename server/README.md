# TradingAgents backend (FastAPI)

The **live server-side tier** behind the Vercel/Next.js frontend. It serves the
artifacts the framework produces and triggers live `propagate()` runs as
background jobs.

**Why a separate service (not Vercel):** a `propagate()` run is ~12 LLM calls over
*minutes*; Vercel serverless functions cap out in seconds. This service must run
on an **always-on host** — Render, Railway, Fly.io, or a VM.

## Endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness + whether live runs are enabled (LLM key present) |
| GET | `/api/backtests` | list Gate A runs (verdict/sharpe/p-value/pit) |
| GET | `/api/backtests/{name}` | one run: summary + equity + trades |
| GET | `/api/journal` | decision journal summary + entries |
| GET | `/api/runs` | saved propagate() runs (ticker/date/rating) |
| GET | `/api/runs/{ticker}/{date}` | one run: rating, final decision, persona stages |
| POST | `/api/runs` `{ticker,date}` | start a live run (background job); needs an LLM key |
| GET | `/api/jobs/{id}` | job status (`running`/`done`/`error`) |

## Run locally
```bash
uv run --python 3.13 --extra server uvicorn server.app:app --reload --port 8000
# open http://localhost:8000/docs  (interactive OpenAPI)
```
Python 3.13 is required (the app loads `tradingagents`, which needs `tiktoken`;
`tiktoken` has no prebuilt wheel for 3.14+).

## Deploy (Render / Railway / Fly)
Build the image in `server/Dockerfile` and set:
- **Secrets:** `OPENAI_API_KEY` (or another provider) to enable live runs; optionally
  `SEC_API_KEY` / `FINNHUB_API_KEY` for point-in-time vendors.
- **`CORS_ORIGINS`:** your Vercel URL, e.g. `https://yourapp.vercel.app` (comma-separated).
- **Persistent volume** mounted at `~/.tradingagents` (or set `TRADINGAGENTS_RESULTS_DIR`
  / `TRADINGAGENTS_MEMORY_LOG_PATH` to a mounted path) so runs survive restarts.
- The container listens on `$PORT`.

## Notes / limits
- The job registry is **in-memory** — fine for a single instance. Multi-instance
  needs a shared queue/store (Redis, a DB).
- Storing LLM keys server-side means the host runs real, paid analyses on demand;
  rate-limit or auth the `POST /api/runs` endpoint before exposing it publicly.
