"""Pure data-loading for the Streamlit dashboard.

This module intentionally does **not** import streamlit, so it stays
unit-testable without the optional dashboard dependency. It only reads
artifacts the rest of the system already produces:

- Gate A backtests under ``<results_dir>/backtests/<run-id>/``
  (``summary.json``, ``equity.csv``, ``trades.csv``), and
- the decision/reflection journal, via
  :meth:`tradingagents.agents.utils.memory.TradingMemoryLog.load_entries`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional

import pandas as pd

from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.default_config import DEFAULT_CONFIG

_JOURNAL_COLUMNS = [
    "date", "ticker", "rating", "status",
    "raw_return", "alpha_return", "holding", "reflection", "decision",
]
_NUM_RE = re.compile(r"[-+]?\d*\.?\d+")


# --- backtests -----------------------------------------------------------

def backtests_root(config: dict = None) -> Path:
    """Directory Gate A writes its runs to."""
    cfg = config or DEFAULT_CONFIG
    return Path(cfg["results_dir"]) / "backtests"


def list_backtest_runs(root) -> List[Path]:
    """Return run directories (those containing summary.json), newest first.

    Run directories are named with a sortable ``YYYYMMDD_HHMMSS`` timestamp, so
    a reverse name sort is newest-first.
    """
    root = Path(root)
    if not root.exists():
        return []
    runs = [p for p in root.iterdir() if p.is_dir() and (p / "summary.json").exists()]
    return sorted(runs, key=lambda p: p.name, reverse=True)


def load_backtest(run_dir) -> dict:
    """Load one Gate A run: summary dict + equity/trades DataFrames."""
    run_dir = Path(run_dir)
    summary = json.loads((run_dir / "summary.json").read_text())
    equity = (
        pd.read_csv(run_dir / "equity.csv")
        if (run_dir / "equity.csv").exists() else pd.DataFrame()
    )
    trades = (
        pd.read_csv(run_dir / "trades.csv")
        if (run_dir / "trades.csv").exists() else pd.DataFrame()
    )
    return {"name": run_dir.name, "summary": summary, "equity": equity, "trades": trades}


# --- journal -------------------------------------------------------------

def parse_pct(value) -> Optional[float]:
    """Parse a stored return string into a fraction.

    ``'+2.5%' -> 0.025``, ``'-1.3%' -> -0.013``, ``'0.05' -> 0.05``,
    ``None`` / ``'n/a'`` / unparseable -> ``None``.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() == "n/a":
        return None
    m = _NUM_RE.search(s)
    if not m:
        return None
    num = float(m.group())
    return num / 100.0 if "%" in s else num


def load_journal(config: dict = None) -> pd.DataFrame:
    """Load the decision/reflection log as a tidy DataFrame.

    Returns an empty (typed) frame when no journal exists yet.
    """
    entries = TradingMemoryLog(config or DEFAULT_CONFIG).load_entries()
    rows = [
        {
            "date": e.get("date"),
            "ticker": e.get("ticker"),
            "rating": e.get("rating"),
            "status": "pending" if e.get("pending") else "resolved",
            "raw_return": parse_pct(e.get("raw")),
            "alpha_return": parse_pct(e.get("alpha")),
            "holding": e.get("holding"),
            "reflection": e.get("reflection", ""),
            "decision": e.get("decision", ""),
        }
        for e in entries
    ]
    return pd.DataFrame(rows, columns=_JOURNAL_COLUMNS)


def journal_summary(df: pd.DataFrame) -> dict:
    """Track-record stats over resolved (outcome-known) journal entries."""
    pending = int((df["status"] == "pending").sum()) if not df.empty else 0
    resolved = (
        df[df["status"] == "resolved"].dropna(subset=["raw_return"])
        if not df.empty else df
    )
    if resolved.empty:
        return {"n_resolved": 0, "n_pending": pending, "win_rate": 0.0,
                "mean_return": 0.0, "mean_alpha": 0.0}
    alpha = resolved["alpha_return"].dropna()
    return {
        "n_resolved": int(len(resolved)),
        "n_pending": pending,
        "win_rate": float((resolved["raw_return"] > 0).mean()),
        "mean_return": float(resolved["raw_return"].mean()),
        "mean_alpha": float(alpha.mean()) if not alpha.empty else 0.0,
    }
