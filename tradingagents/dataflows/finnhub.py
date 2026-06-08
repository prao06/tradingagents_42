"""Point-in-time Finnhub vendor: dated company news + as-of basic financials.

Adapted from AI4Finance-Foundation/FinRobot (Apache-2.0):
``finrobot/data_source/finnhub_utils.py`` (``get_company_news`` and
``get_basic_financials_history``). Reworked to match the TradingAgents vendor
contract and to enforce **point-in-time correctness**:

- news is restricted to articles published within the requested window, with a
  defensive upper-bound recheck so nothing dated after ``end_date`` slips in, and
- the financials snapshot selects, per metric, the most recent reported period
  ``<= curr_date`` — never a future period.

This gives the News and Fundamentals analysts a leakage-free source that can be
included in a Gate A backtest, unlike the live RSS path. Requires the optional
``finnhub-python`` package and ``FINNHUB_API_KEY``; when either is missing the
functions raise and the vendor router falls back to another source.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from .symbol_utils import NoMarketDataError, normalize_symbol

# Caps to keep agent prompts bounded.
_MAX_NEWS = 20
_MAX_METRICS = 40


class FinnhubVendorUnavailable(RuntimeError):
    """Raised when the Finnhub vendor cannot run (missing key or package).

    Distinct from :class:`NoMarketDataError`: "the vendor can't answer" is not the
    same as "the symbol has no data", so the router treats it as an incidental
    failure and falls through to the next vendor.
    """


def _client(api_key: str):
    import finnhub  # lazy: optional dependency

    return finnhub.Client(api_key=api_key)


def _require() -> str:
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        raise FinnhubVendorUnavailable("FINNHUB_API_KEY not set; Finnhub vendor unavailable")
    return key


def _exclusive_upper_ts(end_date: str) -> float:
    """Unix UTC timestamp at the start of the day *after* ``end_date``.

    Used as an exclusive upper bound so an article published any time on
    ``end_date`` is kept, but anything later is dropped.
    """
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return (end_dt + timedelta(days=1)).timestamp()


def get_news(
    ticker: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "window start YYYY-MM-DD"],
    end_date: Annotated[str, "window end (as-of) YYYY-MM-DD"],
) -> str:
    """Point-in-time company news from Finnhub between ``start_date`` and
    ``end_date`` (inclusive). Raises :class:`NoMarketDataError` when the window is
    empty and :class:`FinnhubVendorUnavailable` when the vendor can't run."""
    canonical = normalize_symbol(ticker)
    client = _client(_require())
    try:
        articles = client.company_news(canonical, _from=start_date, to=end_date) or []
    except Exception as e:
        raise FinnhubVendorUnavailable(f"Finnhub company_news failed: {e}")

    upper_ts = _exclusive_upper_ts(end_date)
    rows = []
    for a in articles:
        ts = a.get("datetime")
        if ts is None or ts >= upper_ts:  # defensive PIT guard
            continue
        day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        headline = (a.get("headline") or "").strip()
        summary = (a.get("summary") or "").strip()
        if headline:
            rows.append((day, headline, summary))

    if not rows:
        raise NoMarketDataError(ticker, canonical, "no Finnhub news in date range")

    rows = rows[:_MAX_NEWS]
    header = f"# Finnhub company news for {canonical} ({start_date} to {end_date})\n\n"
    body = "\n".join(
        f"- [{day}] {headline}" + (f"\n  {summary}" if summary else "")
        for day, headline, summary in rows
    )
    return header + body


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "as-of date YYYY-MM-DD; only periods <= this are used"] = None,
) -> str:
    """Point-in-time basic-financials snapshot from Finnhub as of ``curr_date``.

    For each metric in Finnhub's quarterly ``series``, selects the most recent
    reported period on or before ``curr_date``. Raises :class:`NoMarketDataError`
    when nothing qualifies and :class:`FinnhubVendorUnavailable` when the vendor
    can't run."""
    canonical = normalize_symbol(ticker)
    client = _client(_require())
    try:
        data = client.company_basic_financials(canonical, "all") or {}
    except Exception as e:
        raise FinnhubVendorUnavailable(f"Finnhub company_basic_financials failed: {e}")

    series = (data.get("series") or {}).get("quarterly") or {}
    if not series:
        raise NoMarketDataError(ticker, canonical, "no Finnhub financial series")

    cutoff = curr_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = []
    for metric in sorted(series):
        eligible = [p for p in series[metric] if (p.get("period") or "") <= cutoff]
        if not eligible:
            continue
        latest = max(eligible, key=lambda p: p["period"])
        lines.append(f"{metric}: {latest.get('v')} (as of {latest['period']})")

    if not lines:
        raise NoMarketDataError(ticker, canonical, "no Finnhub financials on or before the as-of date")

    header = (
        f"# Finnhub basic financials (point-in-time) for {canonical}\n"
        f"# as of: {cutoff}\n\n"
    )
    return header + "\n".join(lines[:_MAX_METRICS])
