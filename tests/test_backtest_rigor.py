"""Gate A rigor features: universe loading, walk-forward folds, significance."""

import pandas as pd
import pytest

from tradingagents.backtest.engine import load_universe, run_backtest


CONFIG = {"benchmark_map": {"": "SPY"}, "results_dir": "/tmp/unused"}


def test_load_universe_strips_comments_blanks_dupes(tmp_path):
    f = tmp_path / "universe.txt"
    f.write_text("# header\nNVDA\n\nAAPL  # Apple\nNVDA\n  MSFT \n")
    assert load_universe(str(f)) == ["NVDA", "AAPL", "MSFT"]


def _varied_returns(values_by_date):
    return lambda ticker, date, hd, bench: (values_by_date[date], values_by_date[date] / 2, hd)


def test_folds_reported(tmp_path):
    dates = [f"2024-{m:02d}-01" for m in range(1, 7)]  # 6 monthly periods
    vals = dict(zip(dates, [0.03, 0.02, 0.04, 0.025, 0.035, 0.028]))
    summary = run_backtest(
        ["NVDA"], dates, config=CONFIG,
        propagate_fn=lambda t, d: "Buy",
        returns_fn=_varied_returns(vals),
        baseline_fn=lambda b, s, e: 0.0,
        n_folds=3, output_dir=str(tmp_path),
    )
    assert len(summary["folds"]) == 3
    assert all(f["n_periods"] == 2 for f in summary["folds"])
    assert summary["fold_win_rate"] == pytest.approx(1.0)  # all folds positive
    assert (tmp_path / "equity.csv").exists()


def test_verdict_requires_significance(tmp_path):
    # Consistently positive, low-variance returns over many periods -> PASS.
    dates = [f"2024-{m:02d}-01" for m in range(1, 13)]
    vals = {d: 0.03 + (i % 3) * 0.002 for i, d in enumerate(dates)}
    summary = run_backtest(
        ["NVDA"], dates, config=CONFIG,
        propagate_fn=lambda t, d: "Buy",
        returns_fn=_varied_returns(vals),
        baseline_fn=lambda b, s, e: 0.0,
        output_dir=str(tmp_path),
    )
    assert summary["significant"] is True
    assert summary["sharpe"] > 0
    assert summary["verdict"] == "PASS"


def test_non_pit_never_passes_even_if_significant(tmp_path):
    dates = [f"2024-{m:02d}-01" for m in range(1, 13)]
    vals = {d: 0.03 for d in dates}
    summary = run_backtest(
        ["NVDA"], dates, config=CONFIG,
        selected_analysts=["market", "news"],
        propagate_fn=lambda t, d: "Buy",
        returns_fn=_varied_returns(vals),
        baseline_fn=lambda b, s, e: 0.0,
        output_dir=str(tmp_path),
    )
    assert summary["pit"] is False
    assert summary["verdict"] == "FAIL"
