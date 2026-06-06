"""Pure metric math for the Gate A backtester (offline)."""

import numpy as np
import pandas as pd
import pytest

from tradingagents.backtest import metrics


def test_equity_curve_compounds():
    curve = metrics.equity_curve(pd.Series([0.1, -0.1]))
    assert curve.iloc[0] == pytest.approx(1.1)
    assert curve.iloc[1] == pytest.approx(0.99)


def test_max_drawdown():
    curve = pd.Series([1.0, 1.2, 0.9, 1.1])
    # Trough 0.9 against peak 1.2 -> -25%.
    assert metrics.max_drawdown(curve) == pytest.approx(-0.25)


def test_max_drawdown_empty():
    assert metrics.max_drawdown(pd.Series(dtype=float)) == 0.0


def test_sharpe_zero_variance_is_zero():
    assert metrics.sharpe_ratio(pd.Series([0.01, 0.01, 0.01]), 12) == 0.0


def test_sharpe_sign_and_scale():
    r = pd.Series([0.02, -0.01, 0.03, 0.00])
    expected = r.mean() / r.std(ddof=1) * np.sqrt(12)
    assert metrics.sharpe_ratio(r, 12) == pytest.approx(expected)


def test_annualized_return():
    # +10% over 6 monthly periods -> (1.1)^(12/6) - 1 = 0.21.
    r = pd.Series([0.1] + [0.0] * 5)
    assert metrics.annualized_return(r, 12) == pytest.approx(1.1 ** 2 - 1)


def test_hit_rate_ignores_flat_positions():
    trades = pd.DataFrame({
        "position": [1.0, -1.0, 0.0, 1.0],
        "raw_return": [0.02, 0.01, 0.05, -0.03],
    })
    # Directional trades: +/+ (hit), -/+ (miss), +/- (miss) -> 1/3.
    assert metrics.hit_rate(trades) == pytest.approx(1 / 3)


def test_buy_and_hold_return():
    assert metrics.buy_and_hold_return(pd.Series([100.0, 110.0])) == pytest.approx(0.1)


def test_period_returns_equal_weight_by_date():
    trades = pd.DataFrame({
        "date": ["2024-01-01", "2024-01-01", "2024-02-01"],
        "net_return": [0.02, 0.04, -0.01],
    })
    pr = metrics.period_returns_from_trades(trades)
    assert pr.loc["2024-01-01"] == pytest.approx(0.03)
    assert pr.loc["2024-02-01"] == pytest.approx(-0.01)


def test_t_statistic_known_value():
    # mean 0.02, std 0.01, n 3 -> t = 0.02 / (0.01/sqrt(3)).
    t = metrics.t_statistic(pd.Series([0.01, 0.02, 0.03]))
    assert t == pytest.approx(0.02 / (0.01 / np.sqrt(3)))


def test_t_statistic_zero_variance():
    assert metrics.t_statistic(pd.Series([0.02, 0.02])) == 0.0


def test_bootstrap_pvalue_is_seeded_and_small_for_strong_signal():
    r = pd.Series([0.03, 0.025, 0.035, 0.028, 0.032, 0.027, 0.031, 0.029])
    p1 = metrics.bootstrap_pvalue(r, seed=0)
    p2 = metrics.bootstrap_pvalue(r, seed=0)
    assert p1 == p2          # reproducible
    assert p1 < 0.05         # consistently positive -> significant


def test_bootstrap_pvalue_nonpositive_mean_is_one():
    assert metrics.bootstrap_pvalue(pd.Series([-0.01, 0.0, -0.02])) == 1.0


def test_bootstrap_pvalue_insufficient_data():
    assert metrics.bootstrap_pvalue(pd.Series([0.01])) == 1.0


def test_ascii_equity_curve_renders_and_degrades():
    chart = metrics.ascii_equity_curve(pd.Series([1.0, 1.1, 1.05, 1.2]))
    assert "*" in chart and "\n" in chart
    assert metrics.ascii_equity_curve(pd.Series([1.0])) == "(not enough data to plot)"


def test_summarize_keys_and_cost_backout():
    trades = pd.DataFrame({
        "date": ["2024-01-01", "2024-02-01"],
        "ticker": ["NVDA", "NVDA"],
        "position": [1.0, 1.0],
        "raw_return": [0.05, -0.02],
        "alpha_return": [0.03, -0.01],
        "cost": [0.0012, 0.0012],
        "net_return": [0.05 - 0.0012, -0.02 - 0.0012],
    })
    s = metrics.summarize(trades, "monthly")
    assert s["n_trades"] == 2
    assert s["n_periods"] == 2
    # Gross strips the cost back out, so it must exceed the net total return.
    assert s["gross_total_return"] > s["total_return"]
    assert set(["sharpe", "max_drawdown", "hit_rate", "mean_alpha"]) <= set(s)
