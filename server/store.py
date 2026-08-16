"""Map TradingAgents artifacts to Supabase rows, and write them.

The Python service becomes a **job worker**: it runs the engine (which still
writes files via the existing code), then syncs those artifacts into Supabase so
the Vercel/Next.js frontend can read them. The pure mapping functions here are
unit-tested offline; :class:`SupabaseStore` is a thin wrapper over supabase-py
(lazily imported) that a live worker uses.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pandas as pd

from dashboard import data


def _records(df: pd.DataFrame) -> List[dict]:
    """DataFrame -> JSON-safe records (NaN -> None)."""
    if df is None or df.empty:
        return []
    return df.astype(object).where(pd.notnull(df), None).to_dict("records")


def backtest_to_row(bt: dict, user_id: Optional[str] = None) -> dict:
    """Map a ``dashboard.data.load_backtest`` result to a ``backtests`` row."""
    summary = bt["summary"]
    return {
        "user_id": user_id,
        "name": bt["name"],
        "verdict": summary.get("verdict"),
        "pit": summary.get("pit"),
        "summary": summary,
        "equity": _records(bt["equity"]),
        "trades": _records(bt["trades"]),
    }


def decision_run_to_row(raw: dict, ticker: str, trade_date: str,
                        user_id: Optional[str] = None) -> dict:
    """Map a run state-log to a ``decision_runs`` row."""
    return {
        "user_id": user_id,
        "ticker": ticker,
        "trade_date": trade_date,
        "rating": data.decision_rating(raw),
        "final_decision": raw.get("final_trade_decision", ""),
        "stages": data.decision_stages(raw),
    }


def journal_rows(df: pd.DataFrame, user_id: Optional[str] = None) -> List[dict]:
    """Map a ``dashboard.data.load_journal`` DataFrame to ``journal`` rows."""
    rows = []
    for r in _records(df):
        rows.append({
            "user_id": user_id,
            "ticker": r["ticker"],
            "trade_date": r["date"],
            "rating": r["rating"],
            "status": r["status"],
            "raw_return": r["raw_return"],
            "alpha_return": r["alpha_return"],
            "holding": r["holding"],
            "reflection": r["reflection"],
            "decision": r["decision"],
        })
    return rows


def collect_artifacts(config: dict, user_id: Optional[str] = None) -> dict:
    """Read every local artifact (via the existing loaders) into row payloads.

    The worker runs the engine (which writes files), then calls this to gather
    rows for a single upsert into Supabase.
    """
    backtests = [
        backtest_to_row(data.load_backtest(run), user_id)
        for run in data.list_backtest_runs(data.backtests_root(config))
    ]
    runs = []
    for r in data.list_decision_runs(data.decisions_root(config)):
        raw = data.load_decision_run(r["path"])
        runs.append(decision_run_to_row(raw, r["ticker"], r["date"], user_id))
    journal = journal_rows(data.load_journal(config), user_id)
    return {"backtests": backtests, "decision_runs": runs, "journal": journal}


class SupabaseStore:
    """Thin writer over supabase-py using the service-role key (worker side)."""

    def __init__(self, url: str, service_key: str):
        from supabase import create_client  # lazy: optional dependency

        self._client = create_client(url, service_key)

    def upsert(self, table: str, rows: List[dict], on_conflict: str) -> None:
        if rows:
            self._client.table(table).upsert(rows, on_conflict=on_conflict).execute()

    def sync(self, artifacts: dict) -> dict:
        """Upsert collected artifacts; returns counts."""
        self.upsert("backtests", artifacts["backtests"], "user_id,name")
        self.upsert("decision_runs", artifacts["decision_runs"], "user_id,ticker,trade_date")
        self.upsert("journal", artifacts["journal"], "user_id,ticker,trade_date")
        return {k: len(v) for k, v in artifacts.items()}
