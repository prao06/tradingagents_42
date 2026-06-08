"""Walk-forward backtest engine for the Gate A edge test.

``run_backtest`` walks a grid of (ticker, rebalance-date) cells, turns each
TradingAgents rating into a position, scores it with realized forward returns,
nets out trading costs, and compares the resulting equity curve to a buy-and-hold
benchmark. It is resumable (already-computed cells are skipped) and fully
dependency-injectable (``propagate_fn`` / ``returns_fn`` / ``baseline_fn``) so the
whole pipeline can be exercised offline in tests.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd
import yfinance as yf

from tradingagents.backtest import metrics
from tradingagents.backtest.position import rating_to_position
from tradingagents.dataflows.returns import fetch_forward_returns, resolve_benchmark
from tradingagents.default_config import DEFAULT_CONFIG

logger = logging.getLogger(__name__)

# Inputs that are NOT point-in-time: news/social pull live content (README:272)
# and yfinance fundamentals return the latest statements, not as-of the trade
# date. Including any of these makes the backtest non-PIT (look-ahead leakage).
_NON_PIT_ANALYSTS = {"news", "social", "fundamentals"}

# Approximate LLM calls per cell, used only for the up-front cost estimate.
_CALLS_PER_ANALYST = 1
_CALLS_FIXED = 8  # researchers + manager + trader + risk debate + PM (defaults)

TRADE_COLUMNS = [
    "date", "ticker", "rating", "position",
    "raw_return", "alpha_return", "cost", "net_return", "holding_days",
]


def load_universe(path: str) -> List[str]:
    """Read tickers from a file: one per line, ignoring blanks and # comments.

    Inline comments are stripped, so ``NVDA  # Nvidia`` yields ``NVDA``. Order is
    preserved and duplicates are removed.
    """
    seen: List[str] = []
    for raw in Path(path).read_text().splitlines():
        token = raw.split("#", 1)[0].strip()
        if token and token not in seen:
            seen.append(token)
    return seen


def _fold_summaries(trades: pd.DataFrame, frequency: str, n_folds: int) -> List[dict]:
    """Split the rebalance dates into contiguous walk-forward folds and summarize
    each, so a single aggregate number can't hide an edge that lives in one lucky
    window. Returns [] when there are too few periods to fold meaningfully.
    """
    if trades.empty:
        return []
    period_dates = sorted(trades["date"].unique())
    k = max(1, min(n_folds, len(period_dates)))
    if k < 2:
        return []
    folds = []
    for i, chunk in enumerate(np.array_split(period_dates, k)):
        sub = trades[trades["date"].isin(set(chunk))]
        s = metrics.summarize(sub, frequency)
        folds.append({
            "fold": i + 1, "start": str(chunk[0]), "end": str(chunk[-1]),
            "n_periods": s["n_periods"], "total_return": s["total_return"],
            "sharpe": s["sharpe"], "hit_rate": s["hit_rate"],
        })
    return folds


def generate_dates(start: str, end: str, freq: str = "monthly") -> List[str]:
    """Generate rebalance dates (YYYY-MM-DD) from ``start`` to ``end`` inclusive.

    ``freq`` is one of daily/weekly/monthly. Daily uses business days.
    """
    alias = {"daily": "B", "weekly": "W-MON", "monthly": "MS"}.get(freq)
    if alias is None:
        raise ValueError(f"Unknown freq {freq!r}; expected daily/weekly/monthly")
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(start, end, freq=alias)]


def _default_baseline_fn(benchmark: str, start: str, end: str) -> float:
    """Buy-and-hold total return of ``benchmark`` over the window (network)."""
    try:
        end_buffered = (datetime.strptime(end, "%Y-%m-%d") + timedelta(days=14)).strftime("%Y-%m-%d")
        prices = yf.Ticker(benchmark).history(start=start, end=end_buffered)["Close"]
        return metrics.buy_and_hold_return(prices)
    except Exception as e:  # pragma: no cover - network failure path
        logger.warning("Could not fetch baseline %s: %s", benchmark, e)
        return 0.0


def _completed_cells(csv_path: Path) -> set:
    """Return the set of (date, ticker) cells already present in ``csv_path``."""
    if not csv_path.exists():
        return set()
    done = pd.read_csv(csv_path, dtype={"date": str, "ticker": str})
    return set(zip(done["date"], done["ticker"]))


def _append_row(csv_path: Path, row: dict) -> None:
    """Append one trade row to the CSV, writing the header if the file is new."""
    new_file = not csv_path.exists()
    with csv_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TRADE_COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def run_backtest(
    tickers: Sequence[str],
    dates: Sequence[str],
    holding_days: int = 5,
    config: Optional[dict] = None,
    *,
    long_only: bool = False,
    selected_analysts: Sequence[str] = ("market",),
    commission_bps: float = 1.0,
    slippage_bps: float = 5.0,
    frequency: str = "monthly",
    n_folds: int = 4,
    output_dir: Optional[str] = None,
    propagate_fn: Optional[Callable[[str, str], str]] = None,
    returns_fn: Optional[Callable[..., tuple]] = None,
    baseline_fn: Optional[Callable[[str, str, str], float]] = None,
    progress: bool = True,
) -> dict:
    """Run the Gate A backtest and return a summary dict.

    ``propagate_fn(ticker, date) -> rating`` defaults to a real
    ``TradingAgentsGraph`` run; inject a stub to test offline. ``returns_fn`` and
    ``baseline_fn`` default to live yfinance fetches. Writes ``trades.csv`` and
    ``summary.{json,md}`` under ``output_dir`` and is resumable across runs.
    """
    config = config or DEFAULT_CONFIG.copy()
    selected_analysts = list(selected_analysts)
    returns_fn = returns_fn or fetch_forward_returns
    baseline_fn = baseline_fn or _default_baseline_fn

    pit = not (set(selected_analysts) & _NON_PIT_ANALYSTS)
    if not pit:
        logger.warning(
            "NON-POINT-IN-TIME backtest: analysts %s include live/latest-only data "
            "(news/social/fundamentals). Results suffer look-ahead leakage and are "
            "tagged pit=false.", selected_analysts,
        )

    out = Path(output_dir or Path(config["results_dir"]) / "backtests"
               / datetime.now().strftime("%Y%m%d_%H%M%S"))
    out.mkdir(parents=True, exist_ok=True)
    trades_csv = out / "trades.csv"

    # Build the default propagate function lazily so tests never construct a graph.
    if propagate_fn is None:
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        graph = TradingAgentsGraph(selected_analysts=selected_analysts, config=config)
        propagate_fn = lambda t, d: graph.propagate(t, d)[1]  # noqa: E731

    done = _completed_cells(trades_csv)
    total = len(tickers) * len(dates)
    est_calls = total * (len(selected_analysts) * _CALLS_PER_ANALYST + _CALLS_FIXED)
    logger.info(
        "Gate A backtest: %d cells (%d tickers x %d dates), ~%d LLM calls, pit=%s",
        total, len(tickers), len(dates), est_calls, pit,
    )

    processed = 0
    for ticker in tickers:
        benchmark = resolve_benchmark(ticker, config)
        for date in dates:
            processed += 1
            if (date, ticker) in done:
                continue
            try:
                rating = propagate_fn(ticker, date)
            except Exception as e:
                logger.warning("propagate failed for %s on %s: %s", ticker, date, e)
                continue
            raw, alpha, days = returns_fn(ticker, date, holding_days, benchmark)
            if raw is None:
                logger.info("No return data yet for %s on %s; skipping.", ticker, date)
                continue
            position = rating_to_position(rating, long_only=long_only)
            # Round-trip cost: open + close, scaled by gross exposure.
            cost = (commission_bps + slippage_bps) / 1e4 * abs(position) * 2
            row = {
                "date": date, "ticker": ticker, "rating": rating,
                "position": position, "raw_return": raw, "alpha_return": alpha,
                "cost": cost, "net_return": position * raw - cost,
                "holding_days": days,
            }
            _append_row(trades_csv, row)
            if progress:
                logger.info(
                    "[%d/%d] %s %s -> %s (pos %+.2f, net %+.4f)",
                    processed, total, ticker, date, rating, position, row["net_return"],
                )

    trades = (
        pd.read_csv(trades_csv) if trades_csv.exists()
        else pd.DataFrame(columns=TRADE_COLUMNS)
    )
    summary = metrics.summarize(trades, frequency)
    summary["pit"] = pit
    summary["long_only"] = long_only
    summary["selected_analysts"] = selected_analysts

    # Walk-forward folds: is the edge consistent, or one lucky window?
    folds = _fold_summaries(trades, frequency, n_folds)
    summary["folds"] = folds
    summary["fold_win_rate"] = (
        float(np.mean([f["total_return"] > 0 for f in folds])) if folds else 0.0
    )

    # Buy-and-hold baseline over the full window (SPY by default).
    baseline_ticker = config.get("benchmark_map", {}).get("", "SPY")
    summary["baseline_ticker"] = baseline_ticker
    summary["baseline_return"] = (
        baseline_fn(baseline_ticker, min(dates), max(dates)) if dates else 0.0
    )

    # Persist the equity curve for external plotting.
    curve = metrics.equity_curve(metrics.period_returns_from_trades(trades))
    if not curve.empty:
        curve.rename("equity").to_csv(out / "equity.csv", index_label="date")

    summary["beats_baseline"] = bool(summary["total_return"] > summary["baseline_return"])
    # Significance threshold: a positive backtest with p >= 0.05 is not evidence.
    summary["significant"] = bool(summary["p_value"] < 0.05)
    summary["verdict"] = (
        "PASS" if (
            summary["beats_baseline"] and summary["sharpe"] > 0
            and pit and summary["significant"]
        ) else "FAIL"
    )

    _write_reports(out, summary, curve)
    return summary


def _write_reports(out: Path, summary: dict, curve: "pd.Series") -> None:
    """Persist summary.json and a human-readable summary.md."""
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    lines = [
        "# Gate A backtest summary", "",
        f"- Verdict: **{summary['verdict']}**"
        + ("" if summary["pit"] else "  ⚠️ NON-POINT-IN-TIME (leakage)"),
        f"- Trades: {summary['n_trades']}  (periods: {summary['n_periods']})",
        f"- Strategy total return (net): {summary['total_return']:+.2%}",
        f"- Strategy annualized return: {summary['annualized_return']:+.2%}",
        f"- Annualized Sharpe: {summary['sharpe']:.2f}",
        f"- Max drawdown: {summary['max_drawdown']:.2%}",
        f"- Directional hit rate: {summary['hit_rate']:.1%}",
        f"- Mean alpha per trade: {summary['mean_alpha']:+.2%}",
        f"- Gross total return (pre-cost): {summary['gross_total_return']:+.2%}",
        f"- Baseline ({summary['baseline_ticker']} buy & hold): {summary['baseline_return']:+.2%}",
        f"- Beats baseline: {summary['beats_baseline']}",
        "",
        "## Significance",
        f"- t-statistic (mean period return vs 0): {summary['t_stat']:.2f}",
        f"- bootstrap p-value (one-sided): {summary['p_value']:.3f}"
        + ("  ✅ significant" if summary["significant"] else "  ❌ not significant"),
        "",
        "## Walk-forward folds",
        f"- Folds with positive return: {summary['fold_win_rate']:.0%}",
        "",
        "| fold | start | end | periods | total | sharpe | hit |",
        "|------|-------|-----|---------|-------|--------|-----|",
    ]
    for f in summary["folds"]:
        lines.append(
            f"| {f['fold']} | {f['start']} | {f['end']} | {f['n_periods']} | "
            f"{f['total_return']:+.2%} | {f['sharpe']:.2f} | {f['hit_rate']:.0%} |"
        )
    if not summary["folds"]:
        lines.append("| — | — | — | — | — | — | — |")
    lines += [
        "",
        "## Equity curve (growth of $1, net)",
        "```",
        metrics.ascii_equity_curve(curve),
        "```",
        "",
        "Gate A passes only if the strategy beats the baseline net of costs with a "
        "positive Sharpe **and** statistical significance (p < 0.05) on a "
        "point-in-time run. Otherwise, do not proceed to execution work.",
    ]
    (out / "summary.md").write_text("\n".join(lines))
