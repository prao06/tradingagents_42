"""Pure performance-metric helpers for the Gate A backtester.

Everything here operates on in-memory pandas objects and performs no I/O, so the
math is fully unit-testable offline. Network-bound work (fetching the SPY price
series for the baseline) lives in :mod:`tradingagents.backtest.engine`; the
baseline *return* is then computed here via :func:`buy_and_hold_return`.
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

# Default rebalance cadence -> trading periods per year, used to annualize
# return and Sharpe. Falls back to ~252 (daily) for an unknown frequency.
PERIODS_PER_YEAR = {
    "daily": 252,
    "weekly": 52,
    "monthly": 12,
}


def equity_curve(period_returns: pd.Series) -> pd.Series:
    """Compound a series of per-period returns into a growth-of-$1 curve."""
    return (1.0 + period_returns.fillna(0.0)).cumprod()


def max_drawdown(curve: pd.Series) -> float:
    """Largest peak-to-trough fractional decline of an equity curve (<= 0)."""
    if curve.empty:
        return 0.0
    running_max = curve.cummax()
    drawdown = curve / running_max - 1.0
    return float(drawdown.min())


def sharpe_ratio(period_returns: pd.Series, periods_per_year: int) -> float:
    """Annualized Sharpe (excess return assumed already net; rf = 0)."""
    r = period_returns.dropna()
    if len(r) < 2 or r.std(ddof=1) == 0:
        return 0.0
    return float(r.mean() / r.std(ddof=1) * np.sqrt(periods_per_year))


def annualized_return(period_returns: pd.Series, periods_per_year: int) -> float:
    """Geometric annualized return from a series of per-period returns."""
    r = period_returns.dropna()
    if r.empty:
        return 0.0
    total_growth = float((1.0 + r).prod())
    if total_growth <= 0:
        return -1.0
    return total_growth ** (periods_per_year / len(r)) - 1.0


def hit_rate(trades: pd.DataFrame) -> float:
    """Directional accuracy: fraction of non-flat trades whose position sign
    matched the realized raw-return sign. Returns 0.0 if there are no directional
    trades."""
    directional = trades[trades["position"] != 0]
    if directional.empty:
        return 0.0
    correct = np.sign(directional["position"]) == np.sign(directional["raw_return"])
    return float(correct.mean())


def buy_and_hold_return(prices: pd.Series) -> float:
    """Total return of holding from the first to the last price in ``prices``."""
    p = prices.dropna()
    if len(p) < 2 or p.iloc[0] == 0:
        return 0.0
    return float(p.iloc[-1] / p.iloc[0] - 1.0)


def period_returns_from_trades(trades: pd.DataFrame) -> pd.Series:
    """Collapse per-trade net returns into one equal-weighted return per
    rebalance date (the portfolio holds an equal slice of each ticker traded on
    that date). Indexed and sorted by date."""
    if trades.empty:
        return pd.Series(dtype=float)
    grouped = trades.groupby("date")["net_return"].mean().sort_index()
    return grouped


def t_statistic(period_returns: pd.Series) -> float:
    """One-sample t-statistic of per-period returns against a zero mean."""
    r = period_returns.dropna()
    n = len(r)
    if n < 2 or r.std(ddof=1) == 0:
        return 0.0
    return float(r.mean() / (r.std(ddof=1) / np.sqrt(n)))


def bootstrap_pvalue(
    period_returns: pd.Series, n_boot: int = 5000, seed: int = 0
) -> float:
    """One-sided bootstrap p-value for H0: mean period return <= 0.

    Resamples the mean-centered returns (the null) and reports how often a
    bootstrap mean reaches the observed mean. Dependency-free and seeded, so the
    value is reproducible. Returns 1.0 when there is too little data to reject.
    """
    r = period_returns.dropna().to_numpy()
    n = len(r)
    if n < 2:
        return 1.0
    observed = r.mean()
    if observed <= 0:
        return 1.0
    rng = np.random.default_rng(seed)
    centered = r - observed
    boot_means = rng.choice(centered, size=(n_boot, n), replace=True).mean(axis=1)
    return float((boot_means >= observed).mean())


def ascii_equity_curve(curve: pd.Series, width: int = 60, height: int = 12) -> str:
    """Render an equity curve as a fixed-size ASCII line chart (no plotting deps)."""
    vals = curve.dropna().to_numpy(dtype=float)
    if len(vals) < 2:
        return "(not enough data to plot)"
    # Downsample to at most `width` columns.
    if len(vals) > width:
        idx = np.linspace(0, len(vals) - 1, width).astype(int)
        vals = vals[idx]
    lo, hi = float(vals.min()), float(vals.max())
    span = hi - lo or 1.0
    rows = [[" "] * len(vals) for _ in range(height)]
    for col, v in enumerate(vals):
        level = int(round((v - lo) / span * (height - 1)))
        rows[height - 1 - level][col] = "*"
    chart = "\n".join("".join(row) for row in rows)
    return f"{hi:7.3f} |\n{chart}\n{lo:7.3f} +" + "-" * len(vals)


def summarize(trades: pd.DataFrame, frequency: str) -> Dict[str, float]:
    """Aggregate a per-trade DataFrame into the Gate A summary metrics.

    ``trades`` must have columns: date, ticker, position, raw_return,
    alpha_return, cost, net_return.
    """
    ppy = PERIODS_PER_YEAR.get(frequency, 252)
    period_rets = period_returns_from_trades(trades)
    curve = equity_curve(period_rets)
    return {
        "n_trades": int(len(trades)),
        "n_periods": int(len(period_rets)),
        "total_return": float(curve.iloc[-1] - 1.0) if not curve.empty else 0.0,
        "annualized_return": annualized_return(period_rets, ppy),
        "sharpe": sharpe_ratio(period_rets, ppy),
        "max_drawdown": max_drawdown(curve),
        "hit_rate": hit_rate(trades),
        "mean_alpha": float(trades["alpha_return"].dropna().mean()) if not trades.empty else 0.0,
        "mean_cost": float(trades["cost"].dropna().mean()) if not trades.empty else 0.0,
        "t_stat": t_statistic(period_rets),
        "p_value": bootstrap_pvalue(period_rets),
        "gross_total_return": (
            float(equity_curve(
                trades.assign(gross=trades["net_return"] + trades["cost"])
                .groupby("date")["gross"].mean().sort_index()
            ).iloc[-1] - 1.0)
            if not trades.empty else 0.0
        ),
    }
