"""Point-in-time SEC 10-K vendor (tradingagents/dataflows/sec.py).

All offline: the optional ``sec_api`` package is replaced with a controllable
fake injected into ``sys.modules``, so no network or API key is needed.
"""

import sys
import types

import pytest

from tradingagents.dataflows import sec
from tradingagents.dataflows.symbol_utils import NoMarketDataError


def _install_fake_sec_api(monkeypatch, *, filings=None, sections=None, captured=None):
    mod = types.ModuleType("sec_api")

    class QueryApi:
        def __init__(self, api_key=None):
            pass

        def get_filings(self, query):
            if captured is not None:
                captured["query"] = query
            return {"filings": list(filings or [])}

    class ExtractorApi:
        def __init__(self, api_key=None):
            pass

        def get_section(self, link, item, fmt):
            return (sections or {}).get(item, "")

    mod.QueryApi = QueryApi
    mod.ExtractorApi = ExtractorApi
    monkeypatch.setitem(sys.modules, "sec_api", mod)


def _filing(filed_at, link="https://sec/filing"):
    return {"filedAt": filed_at, "linkToFilingDetails": link}


def test_pit_query_filters_on_filedAt_and_sorts_desc(monkeypatch):
    captured = {}
    _install_fake_sec_api(monkeypatch, filings=[_filing("2024-02-01T00:00:00-05:00")],
                          captured=captured)
    sec.latest_10k_as_of("AAPL", "2024-05-10", api_key="k")
    qs = captured["query"]["query"]["query_string"]["query"]
    assert "filedAt:[* TO 2024-05-10]" in qs
    assert 'formType:"10-K"' in qs
    assert captured["query"]["sort"] == [{"filedAt": {"order": "desc"}}]


def test_happy_path_returns_pit_sections(monkeypatch):
    monkeypatch.setenv("SEC_API_KEY", "k")
    _install_fake_sec_api(
        monkeypatch,
        filings=[_filing("2024-02-01T00:00:00-05:00")],
        sections={"1": "We make phones.", "1A": "Risks here.", "7": "MD&A text."},
    )
    out = sec.get_fundamentals("AAPL", "2024-05-10")
    assert "Filed: 2024-02-01" in out
    assert "as of: 2024-05-10" in out
    assert "We make phones." in out and "Item 1A" in out


def test_future_filing_is_excluded(monkeypatch):
    # Even if upstream returns a too-recent filing, the as-of guard rejects it.
    monkeypatch.setenv("SEC_API_KEY", "k")
    _install_fake_sec_api(monkeypatch, filings=[_filing("2025-01-01T00:00:00-05:00")])
    with pytest.raises(NoMarketDataError):
        sec.get_fundamentals("AAPL", "2024-05-10")


def test_no_filings_raises_no_market_data(monkeypatch):
    monkeypatch.setenv("SEC_API_KEY", "k")
    _install_fake_sec_api(monkeypatch, filings=[])
    with pytest.raises(NoMarketDataError):
        sec.get_fundamentals("AAPL", "2024-05-10")


def test_filing_but_no_extractable_sections_raises(monkeypatch):
    monkeypatch.setenv("SEC_API_KEY", "k")
    _install_fake_sec_api(monkeypatch, filings=[_filing("2024-02-01T00:00:00-05:00")],
                          sections={})  # extractor returns "" for every item
    with pytest.raises(NoMarketDataError):
        sec.get_fundamentals("AAPL", "2024-05-10")


def test_missing_key_raises_vendor_unavailable(monkeypatch):
    monkeypatch.delenv("SEC_API_KEY", raising=False)
    _install_fake_sec_api(monkeypatch, filings=[_filing("2024-02-01T00:00:00-05:00")])
    with pytest.raises(sec.SECVendorUnavailable):
        sec.get_fundamentals("AAPL", "2024-05-10")


def test_registered_in_vendor_router():
    from tradingagents.dataflows import interface

    assert "sec" in interface.VENDOR_LIST
    assert interface.VENDOR_METHODS["get_fundamentals"]["sec"] is sec.get_fundamentals


def test_router_falls_back_when_sec_unavailable(monkeypatch):
    import copy
    import tradingagents.default_config as default_config
    from tradingagents.dataflows import interface
    from tradingagents.dataflows.config import set_config

    monkeypatch.delenv("SEC_API_KEY", raising=False)
    cfg = copy.deepcopy(default_config.DEFAULT_CONFIG)
    cfg["data_vendors"]["fundamental_data"] = "sec"
    set_config(cfg)

    # Restrict the dispatch to sec (real, unavailable) + one stub fallback, so
    # the assertion can't be satisfied by a networked vendor like alpha_vantage
    # (which may actually return data in CI).
    monkeypatch.setitem(
        interface.VENDOR_METHODS, "get_fundamentals",
        {
            "sec": sec.get_fundamentals,
            "yfinance": lambda ticker, curr_date=None: "FALLBACK_YF",
        },
    )
    # sec is selected first but unavailable (no key) -> router falls through.
    result = interface.route_to_vendor("get_fundamentals", "AAPL", "2024-05-10")
    assert result == "FALLBACK_YF"
