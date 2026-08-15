"""FastAPI app: serve TradingAgents artifacts + trigger live runs.

``create_app(config=..., runner=...)`` is a factory so tests can inject a
temporary results directory and a fake runner (no LLM, no network). The default
runner lazily builds a real ``TradingAgentsGraph`` so importing this module stays
cheap and the read-only endpoints work without the heavy graph dependencies.
"""

from __future__ import annotations

import os
from typing import List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from dashboard import data
from server.jobs import JobManager

# LLM keys that indicate a live run can actually execute. Used only to fail fast
# with a helpful 400 instead of letting the job error deep in the pipeline.
_LLM_KEYS = (
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "XAI_API_KEY",
    "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "ZHIPU_API_KEY", "MINIMAX_API_KEY",
    "OPENROUTER_API_KEY", "AZURE_OPENAI_API_KEY",
)


class RunRequest(BaseModel):
    ticker: str
    date: str


def _records(df: pd.DataFrame) -> List[dict]:
    """DataFrame -> JSON-safe records (NaN -> None)."""
    if df is None or df.empty:
        return []
    return df.astype(object).where(pd.notnull(df), None).to_dict("records")


def _default_runner(ticker: str, date: str) -> None:
    # Lazy import: keeps module import light and lets read endpoints work even
    # where the full graph stack isn't importable.
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    TradingAgentsGraph(config=DEFAULT_CONFIG.copy()).propagate(ticker, date)


def create_app(config: dict = None, runner=None, allow_origins: List[str] = None) -> FastAPI:
    from tradingagents.default_config import DEFAULT_CONFIG

    cfg = config or DEFAULT_CONFIG
    origins = allow_origins or [o for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o]
    app = FastAPI(title="TradingAgents API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware, allow_origins=origins or ["*"],
        allow_methods=["*"], allow_headers=["*"],
    )
    app.state.jobs = JobManager(runner or _default_runner)

    def _find_run(ticker: str, date: str):
        for r in data.list_decision_runs(data.decisions_root(cfg)):
            if r["ticker"].upper() == ticker.upper() and r["date"] == date:
                return r
        return None

    @app.get("/api/health")
    def health():
        return {"status": "ok", "live_runs_enabled": any(os.environ.get(k) for k in _LLM_KEYS)}

    @app.get("/api/backtests")
    def backtests():
        out = []
        for run in data.list_backtest_runs(data.backtests_root(cfg)):
            s = data.load_backtest(run)["summary"]
            out.append({
                "name": run.name, "verdict": s.get("verdict"),
                "total_return": s.get("total_return"), "sharpe": s.get("sharpe"),
                "p_value": s.get("p_value"), "pit": s.get("pit"),
            })
        return out

    @app.get("/api/backtests/{name}")
    def backtest(name: str):
        run = data.backtests_root(cfg) / name
        if not (run / "summary.json").exists():
            raise HTTPException(404, f"no backtest '{name}'")
        bt = data.load_backtest(run)
        return {"name": bt["name"], "summary": bt["summary"],
                "equity": _records(bt["equity"]), "trades": _records(bt["trades"])}

    @app.get("/api/journal")
    def journal():
        df = data.load_journal(cfg)
        return {"summary": data.journal_summary(df), "entries": _records(df)}

    @app.get("/api/runs")
    def runs():
        out = []
        for r in data.list_decision_runs(data.decisions_root(cfg)):
            raw = data.load_decision_run(r["path"])
            out.append({"ticker": r["ticker"], "date": r["date"],
                        "rating": data.decision_rating(raw)})
        return out

    @app.get("/api/runs/{ticker}/{date}")
    def run_detail(ticker: str, date: str):
        r = _find_run(ticker, date)
        if not r:
            raise HTTPException(404, f"no run for {ticker} {date}")
        raw = data.load_decision_run(r["path"])
        return {
            "ticker": r["ticker"], "date": r["date"],
            "rating": data.decision_rating(raw),
            "final_decision": raw.get("final_trade_decision", ""),
            "stages": data.decision_stages(raw),
        }

    @app.post("/api/runs")
    def submit_run(req: RunRequest):
        if not any(os.environ.get(k) for k in _LLM_KEYS):
            raise HTTPException(400, "no LLM API key configured on the server; live runs disabled")
        job_id = app.state.jobs.submit(req.ticker, req.date)
        return {"job_id": job_id, "status": "running"}

    @app.get("/api/jobs")
    def jobs():
        return app.state.jobs.list()

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        j = app.state.jobs.get(job_id)
        if not j:
            raise HTTPException(404, f"no job '{job_id}'")
        return j

    return app


# Module-level app for `uvicorn server.app:app`.
app = create_app()
