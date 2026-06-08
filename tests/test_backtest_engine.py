"""End-to-end Gate A engine test with injected stubs (no LLM, no network)."""

import pandas as pd
import pytest

from tradingagents.backtest.engine import generate_dates, run_backtest


CONFIG = {"benchmark_map": {"": "SPY"}, "results_dir": "/tmp/unused"}


def _const_returns(raw=0.02, alpha=0.01, days=5):
    return lambda ticker, date, holding_days, benchmark: (raw, alpha, days)


def test_generate_dates_monthly():
    dates = generate_dates("2024-01-01", "2024-03-31", "monthly")
    assert dates == ["2024-01-01", "2024-02-01", "2024-03-01"]


def test_generate_dates_rejects_unknown_freq():
    with pytest.raises(ValueError):
        generate_dates("2024-01-01", "2024-02-01", "hourly")


def test_run_backtest_end_to_end(tmp_path):
    calls = []

    def propagate(ticker, date):
        calls.append((ticker, date))
        return "Buy"  # -> position +1.0

    summary = run_backtest(
        ["NVDA", "AAPL"], ["2024-01-01", "2024-02-01"],
        config=CONFIG,
        propagate_fn=propagate,
        returns_fn=_const_returns(raw=0.02),
        baseline_fn=lambda b, s, e: 0.0,
        output_dir=str(tmp_path),
        commission_bps=1.0, slippage_bps=5.0,
    )

    assert summary["n_trades"] == 4
    assert len(calls) == 4
    assert summary["pit"] is True

    # cost = (1+5)/1e4 * |1| * 2 = 0.0012 ; net = 0.02 - 0.0012 = 0.0188
    trades = pd.read_csv(tmp_path / "trades.csv")
    assert trades["net_return"].iloc[0] == pytest.approx(0.0188)
    assert trades["cost"].iloc[0] == pytest.approx(0.0012)

    # Two equal-weighted periods of +1.88% each compound the equity curve.
    assert summary["total_return"] == pytest.approx(1.0188 ** 2 - 1)
    assert summary["beats_baseline"] is True
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "summary.md").exists()


def test_run_backtest_is_resumable(tmp_path):
    calls = []

    def propagate(ticker, date):
        calls.append((ticker, date))
        return "Buy"

    kw = dict(
        config=CONFIG, propagate_fn=propagate, returns_fn=_const_returns(),
        baseline_fn=lambda b, s, e: 0.0, output_dir=str(tmp_path),
    )
    run_backtest(["NVDA"], ["2024-01-01"], **kw)
    assert len(calls) == 1

    # Second run over the same cell must skip it (no re-propagation).
    run_backtest(["NVDA"], ["2024-01-01"], **kw)
    assert len(calls) == 1
    trades = pd.read_csv(tmp_path / "trades.csv")
    assert len(trades) == 1


def test_non_pit_analysts_flagged(tmp_path):
    summary = run_backtest(
        ["NVDA"], ["2024-01-01"],
        config=CONFIG,
        selected_analysts=["market", "news"],
        propagate_fn=lambda t, d: "Buy",
        returns_fn=_const_returns(),
        baseline_fn=lambda b, s, e: 0.0,
        output_dir=str(tmp_path),
    )
    assert summary["pit"] is False
    assert summary["verdict"] == "FAIL"  # non-PIT can never PASS
