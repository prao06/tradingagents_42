"""Seed demo artifacts so a fresh deployment shows a populated app immediately.

Writes a (dry-run) Gate A backtest, a couple of decision runs, and journal
entries — all **without any LLM key or network** — into the configured
results/memory locations. Framework-free of FastAPI so it's unit-tested directly.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Callable, Tuple

from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.agents.utils.rating import RATINGS_5_TIER
from tradingagents.backtest.engine import generate_dates, run_backtest


def dry_stubs(seed: int = 0) -> Tuple[Callable, Callable, Callable]:
    """Deterministic offline (propagate, returns, baseline) stubs for a dry
    backtest — no LLM, no network."""
    rng = random.Random(seed)

    def propagate(ticker: str, date: str) -> str:
        return rng.choice(RATINGS_5_TIER)

    def returns(ticker: str, date: str, holding_days: int, benchmark: str):
        raw = rng.gauss(0.0, 0.03)
        return raw, raw - rng.gauss(0.0, 0.01), holding_days

    def baseline(benchmark: str, start: str, end: str) -> float:
        return 0.0

    return propagate, returns, baseline


def _demo_run_payload(ticker: str, rating: str) -> dict:
    return {
        "company_of_interest": ticker,
        "market_report": f"{ticker}: uptrend, price above the 50/200-day EMA, RSI ~60.",
        "sentiment_report": f"{ticker}: net-positive social chatter this week.",
        "news_report": f"{ticker}: earnings beat and an analyst upgrade in the window.",
        "fundamentals_report": f"{ticker}: strong margins; valuation on the rich side.",
        "investment_debate_state": {
            "bull_history": "Bull: durable growth runway and share gains.",
            "bear_history": "Bear: valuation is stretched and the cycle may turn.",
            "judge_decision": "Manager: lean constructive, moderate the size.",
        },
        "investment_plan": "Manager plan: accumulate on strength, respect the stop.",
        "trader_investment_decision": "Enter long; stop at -5%; scale on confirmation.",
        "risk_debate_state": {
            "aggressive_history": "Push the position — momentum is with us.",
            "conservative_history": "Trim size; keep a wide stop.",
            "neutral_history": "Balanced: half size, reassess next print.",
        },
        "final_trade_decision": f"**Rating**: {rating}\nThesis: setup favors a measured long.",
    }


def _write_decision_run(results_dir: str, ticker: str, date: str, rating: str) -> Path:
    d = Path(results_dir) / ticker / "TradingAgentsStrategy_logs"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"full_states_log_{date}.json"
    path.write_text(json.dumps(_demo_run_payload(ticker, rating), indent=2))
    return path


def seed_demo(config: dict) -> dict:
    """Populate demo backtest + decision runs + journal. Returns counts."""
    results_dir = config["results_dir"]

    # 1) A dry-run Gate A backtest (writes under results_dir/backtests/<ts>/).
    propagate, returns, baseline = dry_stubs()
    dates = generate_dates("2024-01-01", "2024-06-01", "monthly")
    run_backtest(
        ["NVDA", "AAPL"], dates, config=config,
        propagate_fn=propagate, returns_fn=returns, baseline_fn=baseline,
    )

    # 2) Two saved decision runs.
    runs = [("NVDA", "2024-05-10", "Buy"), ("AAPL", "2024-05-12", "Hold")]
    for ticker, date, rating in runs:
        _write_decision_run(results_dir, ticker, date, rating)

    # 3) Journal: two decisions, one resolved with a realized outcome.
    log = TradingMemoryLog(config)
    for ticker, date, rating in runs:
        log.store_decision(ticker, date, f"**Rating**: {rating}\nThesis: demo entry.")
    log.batch_update_with_outcomes([{
        "ticker": "NVDA", "trade_date": "2024-05-10",
        "raw_return": 0.05, "alpha_return": 0.02, "holding_days": 5,
        "reflection": "Thesis held; trimmed a touch early.",
    }])

    return {"backtests": 1, "runs": len(runs), "journal_entries": len(runs)}
