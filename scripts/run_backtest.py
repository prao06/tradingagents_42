"""Gate A backtester runner.

Walks a grid of (ticker, rebalance-date) cells, turns each TradingAgents rating
into a long/short position, scores it with realized forward returns net of costs,
and compares the equity curve to a buy-and-hold SPY baseline. The point of Gate A
is to learn — cheaply and honestly — whether the signal has any edge before any
execution/live work is justified.

By default it runs **market-only** (the one point-in-time-clean analyst), so the
backtest has no look-ahead leakage. Including news/social/fundamentals is possible
via --analysts but taints results (they pull live/latest-only data); the run is
then tagged pit=false.

Usage:
    # Free dry run (no LLM, no tokens) to validate plumbing + reports:
    python scripts/run_backtest.py --dry-run --tickers NVDA,AAPL \
        --start 2024-01-01 --end 2024-06-01

    # Real market-only run:
    OPENAI_API_KEY=... python scripts/run_backtest.py --tickers NVDA,AAPL \
        --start 2024-01-01 --end 2024-04-01 --freq monthly
"""

from __future__ import annotations

import argparse
import itertools
import logging
import random

from tradingagents.agents.utils.rating import RATINGS_5_TIER
from tradingagents.backtest.engine import generate_dates, load_universe, run_backtest


def _stub_propagate_fn(seed: int = 0):
    """Deterministic offline rating generator for --dry-run (no LLM/network)."""
    rng = random.Random(seed)
    return lambda ticker, date: rng.choice(RATINGS_5_TIER)


def _stub_returns_fn(seed: int = 1):
    """Deterministic offline forward-return generator for --dry-run."""
    rng = random.Random(seed)

    def _fn(ticker, date, holding_days, benchmark):
        raw = rng.gauss(0.0, 0.03)
        alpha = raw - rng.gauss(0.0, 0.01)
        return raw, alpha, holding_days

    return _fn


def main() -> None:
    p = argparse.ArgumentParser(description="Gate A backtester for TradingAgents")
    p.add_argument("--tickers", default="", help="Comma-separated tickers, e.g. NVDA,AAPL")
    p.add_argument("--universe", default=None,
                   help="Path to a file of tickers (one per line, # comments ok). "
                        "Merged with --tickers.")
    p.add_argument("--folds", type=int, default=4,
                   help="Walk-forward folds for consistency reporting (default 4).")
    p.add_argument("--start", required=True, help="First rebalance date YYYY-MM-DD")
    p.add_argument("--end", required=True, help="Last rebalance date YYYY-MM-DD")
    p.add_argument("--freq", default="monthly", choices=["daily", "weekly", "monthly"])
    p.add_argument("--holding-days", type=int, default=5)
    p.add_argument("--analysts", default="market",
                   help="Comma-separated analyst set (default: market). "
                        "Adding news/social/fundamentals makes the run non-PIT.")
    p.add_argument("--long-only", action="store_true",
                   help="Clamp short positions to flat (default is long/short).")
    p.add_argument("--commission-bps", type=float, default=1.0)
    p.add_argument("--slippage-bps", type=float, default=5.0)
    p.add_argument("--limit", type=int, default=None,
                   help="Cap the number of (ticker,date) cells, for quick tests.")
    p.add_argument("--output-dir", default=None)
    p.add_argument("--dry-run", action="store_true",
                   help="Use offline stub ratings/returns — no LLM, no network.")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    if args.universe:
        for t in load_universe(args.universe):
            if t not in tickers:
                tickers.append(t)
    if not tickers:
        p.error("no tickers: pass --tickers and/or --universe")
    analysts = [a.strip() for a in args.analysts.split(",") if a.strip()]
    dates = generate_dates(args.start, args.end, args.freq)

    if args.limit is not None:
        cells = list(itertools.product(tickers, dates))[: args.limit]
        tickers = sorted({t for t, _ in cells})
        dates = sorted({d for _, d in cells})

    kwargs = {}
    if args.dry_run:
        kwargs["propagate_fn"] = _stub_propagate_fn()
        kwargs["returns_fn"] = _stub_returns_fn()
        kwargs["baseline_fn"] = lambda b, s, e: 0.0

    summary = run_backtest(
        tickers, dates,
        holding_days=args.holding_days,
        long_only=args.long_only,
        selected_analysts=analysts,
        commission_bps=args.commission_bps,
        slippage_bps=args.slippage_bps,
        frequency=args.freq,
        n_folds=args.folds,
        output_dir=args.output_dir,
        **kwargs,
    )

    print("\n=== Gate A summary ===")
    for key in ("verdict", "pit", "n_trades", "total_return", "annualized_return",
                "sharpe", "max_drawdown", "hit_rate", "mean_alpha",
                "t_stat", "p_value", "significant", "fold_win_rate",
                "baseline_ticker", "baseline_return", "beats_baseline"):
        print(f"  {key:18}: {summary[key]}")


if __name__ == "__main__":
    main()
