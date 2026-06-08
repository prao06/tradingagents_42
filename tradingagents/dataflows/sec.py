"""Point-in-time SEC 10-K data vendor.

Adapted from AI4Finance-Foundation/FinRobot (Apache-2.0): the sec-api.io query +
section-extraction approach in ``finrobot/data_source/sec_utils.py``. Reworked
here to (a) match the TradingAgents vendor contract used by
:mod:`tradingagents.dataflows.interface`, and (b) enforce **point-in-time
correctness** — only filings with ``filedAt <= curr_date`` are ever returned, so
the Fundamentals Analyst can be honestly backtested (no look-ahead).

Requires the optional ``sec_api`` package and a ``SEC_API_KEY``. When either is
missing the functions raise, and the vendor router falls back to another source.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Annotated, Optional, Tuple

from .symbol_utils import NoMarketDataError, normalize_symbol

# 10-K narrative items most useful to the Fundamentals Analyst. Kept small to
# bound prompt size; extend if the analyst needs more context.
_DEFAULT_SECTIONS = {
    "1": "Business",
    "1A": "Risk Factors",
    "7": "Management's Discussion & Analysis",
}

# Per-section character cap so a long 10-K can't blow up the agent prompt.
_SECTION_CHAR_LIMIT = 4000


class SECVendorUnavailable(RuntimeError):
    """Raised when the SEC vendor cannot run (missing key or ``sec_api`` package).

    Distinct from :class:`NoMarketDataError`: "the vendor can't answer" is not the
    same as "the symbol has no data". The router treats this as an incidental
    failure and falls through to the next vendor.
    """


def _query_api(api_key: str):
    from sec_api import QueryApi  # lazy: optional dependency

    return QueryApi(api_key=api_key)


def _extractor_api(api_key: str):
    from sec_api import ExtractorApi  # lazy: optional dependency

    return ExtractorApi(api_key=api_key)


def _require(api_key_getter=os.environ.get) -> str:
    key = api_key_getter("SEC_API_KEY")
    if not key:
        raise SECVendorUnavailable("SEC_API_KEY not set; SEC vendor unavailable")
    return key


def latest_10k_as_of(
    ticker: str, curr_date: Optional[str], api_key: str
) -> Optional[Tuple[str, str]]:
    """Return ``(filedAt, filing_url)`` for the most recent 10-K filed on or
    before ``curr_date``, or ``None`` if there is no such filing.

    The point-in-time guard lives in the query: ``filedAt:[* TO <curr_date>]``
    plus a descending sort, so the first hit is the latest *as-of* filing.
    """
    upper = curr_date or datetime.now().strftime("%Y-%m-%d")
    query = {
        "query": {
            "query_string": {
                "query": (
                    f'ticker:{ticker} AND formType:"10-K" '
                    f"AND filedAt:[* TO {upper}]"
                )
            }
        },
        "from": "0",
        "size": "1",
        "sort": [{"filedAt": {"order": "desc"}}],
    }
    resp = _query_api(api_key).get_filings(query) or {}
    filings = resp.get("filings") or []
    if not filings:
        return None
    top = filings[0]
    filed_at = top.get("filedAt", "")
    # Defense in depth: never trust a filing dated after the as-of date, even if
    # the upstream query somehow returned one.
    if curr_date and filed_at[:10] > curr_date:
        return None
    return filed_at, top.get("linkToFilingDetails", "")


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "as-of date YYYY-MM-DD; only filings <= this are used"] = None,
) -> str:
    """Point-in-time 10-K narrative sections for ``ticker`` as of ``curr_date``.

    Only filings with ``filedAt <= curr_date`` are considered, so this is safe to
    use inside a backtest. Raises :class:`NoMarketDataError` when no qualifying
    filing exists (router falls back), and :class:`SECVendorUnavailable` when the
    vendor itself can't run.
    """
    canonical = normalize_symbol(ticker)
    api_key = _require()

    found = latest_10k_as_of(canonical, curr_date, api_key)
    if not found:
        raise NoMarketDataError(
            ticker, canonical, "no 10-K filed on or before the as-of date"
        )
    filed_at, link = found

    extractor = _extractor_api(api_key)
    blocks = []
    for item, title in _DEFAULT_SECTIONS.items():
        try:
            text = (extractor.get_section(link, item, "text") or "").strip()
        except Exception:
            text = ""
        if text:
            blocks.append(f"## Item {item} — {title}\n{text[:_SECTION_CHAR_LIMIT]}")

    if not blocks:
        raise NoMarketDataError(
            ticker, canonical, "10-K located but no sections could be extracted"
        )

    header = (
        f"# SEC 10-K (point-in-time) for {canonical}\n"
        f"# Filed: {filed_at[:10]}  |  as of: {curr_date or 'today'}\n\n"
    )
    return header + "\n\n".join(blocks)
