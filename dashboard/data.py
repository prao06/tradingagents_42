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
from tradingagents.agents.utils.rating import parse_rating
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


# --- decision runs (the agent pipeline) ----------------------------------

def decisions_root(config: dict = None) -> Path:
    """Directory where propagate() writes per-run state logs (one tree per ticker)."""
    cfg = config or DEFAULT_CONFIG
    return Path(cfg["results_dir"])


def list_decision_runs(results_dir) -> List[dict]:
    """Enumerate saved propagate() runs, newest (by trade date) first.

    Each run is a ``full_states_log_<date>.json`` under
    ``<results_dir>/<ticker>/TradingAgentsStrategy_logs/``.
    """
    root = Path(results_dir)
    if not root.exists():
        return []
    runs = []
    for log in root.glob("*/TradingAgentsStrategy_logs/full_states_log_*.json"):
        runs.append({
            "ticker": log.parts[-3],
            "date": log.stem.replace("full_states_log_", ""),
            "path": log,
        })
    return sorted(runs, key=lambda r: (r["date"], r["ticker"]), reverse=True)


def load_decision_run(path) -> dict:
    """Load a single run's full state-log JSON."""
    return json.loads(Path(path).read_text())


def decision_rating(raw: dict) -> str:
    """The final 5-tier rating, parsed from the Portfolio Manager decision."""
    return parse_rating(raw.get("final_trade_decision", "") or "")


def _nested(raw: dict, *keys) -> str:
    """Safely pull a nested string field, returning '' when absent."""
    cur = raw
    for k in keys:
        if not isinstance(cur, dict):
            return ""
        cur = cur.get(k, "")
    return cur if isinstance(cur, str) else ""


def decision_stages(raw: dict) -> List[dict]:
    """Turn a run log into the ordered agent pipeline, with investor-persona
    framing for the UI. The final Portfolio Manager decision is rendered
    separately (see :func:`decision_rating`), so it is not included here.

    Each stage: ``{group, label, persona, icon, content}`` (content stripped).
    """
    spec = [
        ("Analysts", "Market Analyst", "The Technician — price & momentum", "📈",
         ("market_report",)),
        ("Analysts", "Sentiment Analyst", "The Crowd-Reader — social mood", "💬",
         ("sentiment_report",)),
        ("Analysts", "News Analyst", "The Macro Watcher — headlines & events", "📰",
         ("news_report",)),
        ("Analysts", "Fundamentals Analyst", "The Value Lens — Graham/Buffett school", "📒",
         ("fundamentals_report",)),
        ("Research debate", "Bull Researcher", "The Optimist — Lynch-style growth", "🐂",
         ("investment_debate_state", "bull_history")),
        ("Research debate", "Bear Researcher", "The Skeptic — Klarman/Marks school", "🐻",
         ("investment_debate_state", "bear_history")),
        ("Research debate", "Research Manager", "The CIO — synthesizes the debate", "⚖️",
         ("investment_plan",)),
        ("Trade plan", "Trader", "The Trader — turns thesis into a plan", "💹",
         ("trader_investment_decision",)),
        ("Risk committee", "Aggressive", "Risk: Aggressive — push the position", "🔥",
         ("risk_debate_state", "aggressive_history")),
        ("Risk committee", "Conservative", "Risk: Conservative — protect capital", "🛡️",
         ("risk_debate_state", "conservative_history")),
        ("Risk committee", "Neutral", "Risk: Neutral — weigh both sides", "⚖️",
         ("risk_debate_state", "neutral_history")),
    ]
    stages = []
    for group, label, persona, icon, keys in spec:
        content = _nested(raw, *keys)
        # Research Manager judge_decision is a good fallback for investment_plan.
        if not content and label == "Research Manager":
            content = _nested(raw, "investment_debate_state", "judge_decision")
        stages.append({
            "group": group, "label": label, "persona": persona,
            "icon": icon, "content": (content or "").strip(),
        })
    return stages


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
