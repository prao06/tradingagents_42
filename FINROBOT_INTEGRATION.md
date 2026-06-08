# FinRobot → TradingAgents: Integration Review & Plan

**Question:** Can we merge AI4Finance's
[FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) into the
TradingAgents setup?
**Verdict:** **Do not merge the frameworks. Selectively port FinRobot's
point-in-time data fetchers** (SEC filings, Finnhub history, a few FMP helpers)
as new TradingAgents *data vendors*, behind the existing vendor-dispatch seam.
This adds higher-quality, **as-of-date** fundamentals and news — directly closing
the point-in-time gap (G4 / risk 3.3) from the project review — without taking on
FinRobot's orchestration engine.

---

## 1. Why not a framework merge

| | TradingAgents | FinRobot |
|---|---|---|
| Orchestration | **LangGraph** (stateful graph, `graph/setup.py`) | **Microsoft AutoGen / AG2** (conversational) |
| Model layer | own multi-provider `llm_clients/` | autogen config, gpt-4-oriented |
| Output | 5-tier rating + thesis | equity-research reports, forecasts |
| License | Apache-2.0 | Apache-2.0 |

The two use incompatible agent paradigms. Merging the engines means running and
maintaining both — high cost, little benefit. The value in FinRobot for us is its
**data-source layer**, which is framework-agnostic Python and ports cleanly.

## 2. License & attribution — clear to proceed

Both are **Apache-2.0** (FinRobot © AI4Finance Foundation). We may incorporate
its code with attribution. The FinRobot source files carry **no per-file license
headers**, so when we port a module we will:
- add a short docstring crediting "Adapted from AI4Finance-Foundation/FinRobot
  (Apache-2.0)", and
- add a `NOTICE` entry at repo root.

## 3. What FinRobot actually provides (verified from source)

FinRobot's `finrobot/data_source/` modules, with the **point-in-time** lens that
matters for honest backtesting:

### `sec_utils.py` — SEC 10-K filings (**strong PIT win**)
- `get_10k_metadata(ticker, start_date, end_date)`, `get_10k_section(ticker, fyear, section, ...)`, `download_10k_filing/pdf(...)`.
- Accepts `start_date`/`end_date`; **returns `filedAt`** → we can restrict to
  filings *filed on or before the trade date* and pull sections (1A risk factors,
  7 MD&A, etc.).
- Backed by the **paid `sec-api.io`** service (`SEC_API_KEY`), *not* free EDGAR.

### `finnhub_utils.py` — news + historical financials (**good PIT win**)
- `get_company_news(symbol, start_date, end_date, ...)` → dated news (PIT).
- `get_basic_financials_history(symbol, freq, start_date, end_date, ...)` →
  historical metrics (PIT).
- `get_basic_financials(...)` → **latest snapshot only (non-PIT)**.
- `get_company_profile(...)`. Backed by **Finnhub** (`FINNHUB_API_KEY`).

### `fmp_utils.py` — Financial Modeling Prep (**mixed**)
- PIT-capable: `get_historical_market_cap(ticker, date)`,
  `get_historical_bvps(ticker, target_date)`, `get_target_price(ticker, date)`,
  `get_sec_report(ticker, fyear)` (returns filing date).
- **NOT PIT:** `get_financial_metrics(ticker, years)` and
  `get_competitor_financial_metrics(...)` return **latest N years only** — i.e.
  the headline statement-metrics function would reintroduce look-ahead if used in
  a backtest as written.
- Backed by **FMP** (`FMP_API_KEY`).

**Caveat we must respect:** "has a date parameter" ≠ "point-in-time." Several
functions still return latest-only data. Any ported fetcher used in backtest must
be wrapped to assert `as_of_date <= trade_date` (e.g. filter on `filedAt`).

## 4. The integration seam in TradingAgents (already perfect for this)

`tradingagents/dataflows/interface.py` is a clean vendor registry:
- `VENDOR_LIST` (`interface.py:64`) — currently `["yfinance", "alpha_vantage"]`.
- `VENDOR_METHODS` (`interface.py:70`) — per-method `{vendor: fn}` dispatch for
  `get_fundamentals`, `get_balance_sheet`, `get_income_statement`, `get_news`,
  `get_insider_transactions`, etc.
- `get_vendor()` / `route_to_vendor()` (`interface.py:120,135`) resolve the
  vendor from config and **already build a fallback chain** — so a new vendor that
  is missing a key or returns empty degrades gracefully to yfinance.
- Config knobs already exist (`default_config.py:101-110`):
  ```python
  "data_vendors":  {"fundamental_data": "yfinance", "news_data": "yfinance", ...},
  "tool_vendors":  { "get_income_statement": "fmp" },   # per-tool override
  ```

**Adding a FinRobot-derived vendor therefore requires no framework change:** new
fetcher module + register it in `VENDOR_LIST` and the relevant `VENDOR_METHODS`
entries + document the config + env keys. Existing TradingAgents tool signatures
already pass a date (e.g. `get_news(..., curr_date)`), so PIT slots in naturally.

## 5. Recommended scope & phasing

### Phase 1 — SEC point-in-time fundamentals/filings (highest value)
- New `tradingagents/dataflows/sec.py` adapting `sec_utils.get_10k_section` /
  `get_10k_metadata`, **filtering on `filedAt <= curr_date`**.
- Register `"sec"` for `get_fundamentals` (and optionally a new
  `get_filing_section` tool the Fundamentals Analyst can call).
- Outcome: the Fundamentals Analyst becomes **honestly backtestable** in Gate A
  (today it's excluded because yfinance fundamentals are latest-only).

### Phase 2 — Finnhub dated news + historical financials
- New `tradingagents/dataflows/finnhub.py` wrapping `get_company_news` and
  `get_basic_financials_history`, registered for `get_news` and as a
  fundamentals source.
- Outcome: a PIT news path, an alternative to the current free RSS/scrape that
  the review flagged as fragile (risk 3.4) and non-PIT (risk 3.3).

### Phase 3 (optional) — FMP dated helpers
- Port only the PIT helpers (`get_historical_market_cap`, `get_historical_bvps`,
  `get_target_price`); **do not** port `get_financial_metrics` as-is for backtest
  use.

### Not recommended
- FinRobot's agents (Forecaster/Strategist/Director) — overlap our existing
  analysts and are AutoGen-native; porting = rewrite for marginal gain.
- FinRobot's report generator — nice but separate; revisit later.
- AutoGen / FinRobot's model layer — keep our `llm_clients/`.

## 6. Risks & costs

- **Paid APIs.** sec-api.io, FMP, and Finnhub all need paid keys. This *raises*
  data quality but *adds* recurring cost and new failure/quota modes — mitigated
  by the existing fallback chain to yfinance.
- **PIT correctness is on us.** Must wrap each fetcher with an `as_of` guard;
  "has a date arg" is not sufficient (see §3 caveat).
- **New dependencies** (`sec_api`, `finnhub-python`) — add as optional extras so
  a user without keys is unaffected.
- **FinRobot is research-grade too** — port specific functions, not modules
  wholesale; add our own tests.
- Does **not** advance the IBKR/Gate-B execution goal — this is a data-quality
  upgrade, not an execution step.

## 7. Verification (when we build Phase 1)

- Unit tests with a mocked `sec_api` client: assert a filing dated *after* the
  trade date is **excluded**, and a section is returned for a valid as-of date.
- Register `"sec"` and run the existing `route_to_vendor` fallback test path to
  confirm graceful degradation to yfinance when `SEC_API_KEY` is absent.
- Run Gate A twice on the same historical universe with `fundamental_data: sec` —
  inputs/returns must be **identical across wall-clock days** (true PIT), unlike
  the live-data analysts.
- A/B Gate A verdict: `fundamental_data: yfinance` vs `sec` to see whether higher-
  quality, point-in-time fundamentals change the edge result.

## 8. Bottom line

FinRobot is a sibling research framework, not a drop-in module — but its
**data-source layer is genuinely useful and license-compatible**. The clean move
is a **targeted port of its point-in-time SEC and Finnhub fetchers** into our
existing vendor-dispatch system, starting with SEC fundamentals so the
Fundamentals Analyst finally becomes backtestable under Gate A. Skip the
orchestration, the agents, and the latest-only functions.
