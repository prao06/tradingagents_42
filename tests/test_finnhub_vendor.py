"""Point-in-time Finnhub vendor (tradingagents/dataflows/finnhub.py).

Offline: the optional ``finnhub`` package is replaced with a controllable fake
injected into ``sys.modules``, so no network or API key is required.
"""

import sys
import types
from datetime import datetime, timezone

import pytest

from tradingagents.dataflows import finnhub as fh
from tradingagents.dataflows.symbol_utils import NoMarketDataError


def _unix(date_str, hour=12):
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=hour, tzinfo=timezone.utc)
    return dt.timestamp()


def _install_fake_finnhub(monkeypatch, *, news=None, basic=None):
    mod = types.ModuleType("finnhub")

    class Client:
        def __init__(self, api_key=None):
            pass

        def company_news(self, symbol, _from=None, to=None):
            return list(news or [])

        def company_basic_financials(self, symbol, metric):
            return basic or {}

    mod.Client = Client
    monkeypatch.setitem(sys.modules, "finnhub", mod)


# --- news ----------------------------------------------------------------

def test_news_happy_path(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    _install_fake_finnhub(monkeypatch, news=[
        {"datetime": _unix("2024-05-08"), "headline": "Beat earnings", "summary": "good"},
        {"datetime": _unix("2024-05-09"), "headline": "Analyst upgrade", "summary": ""},
    ])
    out = fh.get_news("AAPL", "2024-05-01", "2024-05-10")
    assert "Beat earnings" in out and "Analyst upgrade" in out
    assert "[2024-05-08]" in out


def test_news_excludes_articles_after_end_date(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    _install_fake_finnhub(monkeypatch, news=[
        {"datetime": _unix("2024-05-09"), "headline": "In window", "summary": ""},
        {"datetime": _unix("2024-05-11"), "headline": "Leaked future", "summary": ""},
    ])
    out = fh.get_news("AAPL", "2024-05-01", "2024-05-10")
    assert "In window" in out
    assert "Leaked future" not in out  # defensive PIT upper-bound guard


def test_news_end_date_inclusive(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    _install_fake_finnhub(monkeypatch, news=[
        {"datetime": _unix("2024-05-10", hour=23), "headline": "Late on the day", "summary": ""},
    ])
    out = fh.get_news("AAPL", "2024-05-01", "2024-05-10")
    assert "Late on the day" in out  # same-day articles are kept


def test_news_empty_window_raises(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    _install_fake_finnhub(monkeypatch, news=[])
    with pytest.raises(NoMarketDataError):
        fh.get_news("AAPL", "2024-05-01", "2024-05-10")


def test_news_missing_key_raises_unavailable(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    _install_fake_finnhub(monkeypatch, news=[{"datetime": _unix("2024-05-08"), "headline": "x"}])
    with pytest.raises(fh.FinnhubVendorUnavailable):
        fh.get_news("AAPL", "2024-05-01", "2024-05-10")


# --- fundamentals --------------------------------------------------------

_SERIES = {"series": {"quarterly": {
    "currentRatio": [
        {"period": "2023-12-31", "v": 1.1},
        {"period": "2024-03-31", "v": 1.2},
        {"period": "2024-06-30", "v": 1.3},  # after the as-of date
    ],
    "netMargin": [{"period": "2024-03-31", "v": 0.25}],
}}}


def test_fundamentals_selects_latest_period_on_or_before_cutoff(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    _install_fake_finnhub(monkeypatch, basic=_SERIES)
    out = fh.get_fundamentals("AAPL", "2024-05-10")
    assert "currentRatio: 1.2 (as of 2024-03-31)" in out  # not 1.3 (future)
    assert "netMargin: 0.25 (as of 2024-03-31)" in out
    assert "2024-06-30" not in out


def test_fundamentals_no_eligible_period_raises(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    _install_fake_finnhub(monkeypatch, basic=_SERIES)
    with pytest.raises(NoMarketDataError):
        fh.get_fundamentals("AAPL", "2020-01-01")  # everything is in the future


def test_fundamentals_no_series_raises(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    _install_fake_finnhub(monkeypatch, basic={})
    with pytest.raises(NoMarketDataError):
        fh.get_fundamentals("AAPL", "2024-05-10")


# --- router integration --------------------------------------------------

def test_registered_in_vendor_router():
    from tradingagents.dataflows import interface

    assert "finnhub" in interface.VENDOR_LIST
    assert interface.VENDOR_METHODS["get_news"]["finnhub"] is fh.get_news
    assert interface.VENDOR_METHODS["get_fundamentals"]["finnhub"] is fh.get_fundamentals


def test_router_falls_back_when_finnhub_unavailable(monkeypatch):
    import copy
    import tradingagents.default_config as default_config
    from tradingagents.dataflows import interface
    from tradingagents.dataflows.config import set_config

    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    cfg = copy.deepcopy(default_config.DEFAULT_CONFIG)
    cfg["data_vendors"]["news_data"] = "finnhub"
    set_config(cfg)

    monkeypatch.setitem(
        interface.VENDOR_METHODS["get_news"], "yfinance",
        lambda ticker, start_date, end_date: "FALLBACK_YF",
    )
    result = interface.route_to_vendor("get_news", "AAPL", "2024-05-01", "2024-05-10")
    assert result == "FALLBACK_YF"
