"""Forward-return / benchmark math in tradingagents.dataflows.returns (offline)."""

import pandas as pd
import pytest

from tradingagents.dataflows import returns


class _FakeTicker:
    """Stand-in for yf.Ticker whose .history returns a preset Close series."""

    _DATA = {
        "NVDA": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
        "SPY": [200.0, 201.0, 202.0, 203.0, 204.0, 205.0],
        "SHORT": [100.0],  # too few rows -> unavailable
    }

    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, start=None, end=None):
        return pd.DataFrame({"Close": self._DATA[self.symbol]})


@pytest.fixture()
def fake_yf(monkeypatch):
    monkeypatch.setattr(returns.yf, "Ticker", _FakeTicker)


def test_fetch_forward_returns_raw_and_alpha(fake_yf):
    raw, alpha, days = returns.fetch_forward_returns("NVDA", "2024-01-02", 5, "SPY")
    assert raw == pytest.approx(0.05)        # (105-100)/100
    assert alpha == pytest.approx(0.025)     # 0.05 - (205-200)/200
    assert days == 5


def test_fetch_forward_returns_unavailable(fake_yf):
    assert returns.fetch_forward_returns("SHORT", "2024-01-02", 5, "SPY") == (None, None, None)


def test_fetch_forward_returns_clamps_holding_days(fake_yf):
    # Asking for 50 days when only 6 rows exist clamps to len-1 = 5.
    _, _, days = returns.fetch_forward_returns("NVDA", "2024-01-02", 50, "SPY")
    assert days == 5


def test_resolve_benchmark_explicit_override():
    cfg = {"benchmark_ticker": "QQQ", "benchmark_map": {"": "SPY"}}
    assert returns.resolve_benchmark("NVDA", cfg) == "QQQ"


def test_resolve_benchmark_suffix_map():
    cfg = {"benchmark_ticker": None, "benchmark_map": {".T": "^N225", "": "SPY"}}
    assert returns.resolve_benchmark("7203.T", cfg) == "^N225"
    assert returns.resolve_benchmark("NVDA", cfg) == "SPY"
