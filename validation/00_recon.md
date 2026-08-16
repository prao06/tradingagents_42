# Phase 1 — Reconnaissance

All claims below are from source (verified by reading node functions and the
state-dict construction, not prompt text or the existing doc). File refs are to
`tradingagents/…`.

## Disconfirming results first

1. **This environment cannot execute the pipeline.** No LLM API key is set
   (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`,
   `XAI_API_KEY` all unset). **Phases 2–5 require running `propagate()` hundreds
   of times** (Phase 2 alone = 15 pairs × 30 = 450 runs, each ~12 LLM calls over
   minutes). That is **NOT_COMPUTED here: no key, no network budget, no wall-clock**.
   This is a hard gate blocker for everything past Phase 1 — see the Gate verdict.
2. **Zero empirical history exists.** `find ~/.tradingagents -name full_states_log_*.json`
   = **0**; no `~/.tradingagents/memory/trading_memory.md`. So "what universe/dates
   have been run and how many resolved decisions exist" = **none, and 0**. There is
   no prior data to analyze, and none can be generated here.
3. **One doc claim is imprecise** (point 5): the four analyst reports are read by
   **two** stages, not one — the risk debators re-read them — so the "every arrow is
   a lossy summarization" telephone framing overstates the compression. Details below.

## Path drift (brief's entry points → actual)

| Brief path | Actual path | Note |
|---|---|---|
| `agents/research_manager.py` | `agents/managers/research_manager.py` | moved |
| `agents/trader.py` | `agents/trader/trader.py` | moved |
| `agents/portfolio_manager.py` | `agents/managers/portfolio_manager.py` | moved |
| `agents/utils/agent_utils.py` (brief: `agent_utils.py`) | `agents/utils/agent_utils.py` | ok |
| `market_data_validator.py` | `dataflows/market_data_validator.py` | in dataflows |
| `graph/setup.py`, `graph/conditional_logic.py`, `graph/trading_graph.py`, `agents/schemas.py` | same | ok |

## Agent → input table (from state access, not prompts)

Verified by grepping `state[...]` reads in each node.

| Agent | Reads from state | Sees the 4 reports? | Sees memory (`past_context`)? |
|---|---|---|---|
| Market/Sentiment/News/Fundamentals analysts | `trade_date`, `company_of_interest`, `instrument_context`, `messages` (wiped between) | writes them; blind to others' | no |
| **Bull researcher** (`bull_researcher.py:14-17`) | 4 reports + `investment_debate_state{history,current_response,bull_history}` | **yes** | no |
| **Bear researcher** (`bear_researcher.py:14-17`) | 4 reports + `investment_debate_state{…}` | **yes** | no |
| **Research Manager** (`research_manager.py:20-21`) | `instrument_context`, `investment_debate_state.history` **only** | **NO** | no |
| **Trader** (`trader.py:24-26`) | `company_of_interest`, `instrument_context`, `investment_plan` **only** | **NO** | no |
| **Aggressive/Conservative/Neutral** (`*_debator.py:16-22`) | 4 reports + `trader_investment_plan` + others' risk responses | **yes** | no |
| **Portfolio Manager** (`portfolio_manager.py:28-35`) | `risk_debate_state.history`, `investment_plan`, `trader_investment_plan`, `past_context` | **NO (directly)** | **yes — only agent that does** |

Key structural facts this establishes:
- The **reports enter the chain twice**: at the Bull/Bear debate and again at the
  risk debate. RM, Trader, and PM never read the raw reports.
- **Memory reaches exactly one agent, the PM** (no other node reads `past_context`).

## The nine doc points, adjudicated against source

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | Analysts blind to each other (sequential, msg wiped) | **CONFIRMED** | `setup.py:89,107-109`; msg-delete node `agent_utils.py` |
| 2 | RM judges only the transcript, not the reports | **CONFIRMED** | `research_manager.py:20-21` (no report keys read) |
| 3 | Trader told to anchor in reports it cannot see | **CONFIRMED** | reads only `investment_plan` `trader.py:26`; prompt `trader.py:34` |
| 4 | Tier compression 5→3→5 | **CONFIRMED** | `PortfolioRating` 5-tier `schemas.py:32-39`; `TraderAction` 3-tier `schemas.py:42-53` |
| 5 | "~5 lossy hops; every arrow is a summarization" | **STALE / imprecise** | risk debators re-read raw reports (`aggressive_debator.py:16-19`), so the chain re-grounds; hop count defensible, "telephone" framing is not |
| 6 | Debate = 1 exchange by default | **CONFIRMED** | `conditional_logic.py:9,56,66`; exits at `count ≥ 2×rounds` / `3×rounds`, default 1 |
| 7 | Memory reaches only the PM | **CONFIRMED** | only `portfolio_manager.py:35` reads `past_context`; no other node does |
| 8 | Reflection grades fixed 5d vs PM's stated horizon | **CONFIRMED** | `_fetch_returns(holding_days=5)` default, called w/o override in `_resolve_pending_entries`; `PortfolioDecision.time_horizon` is free-text, unused in scoring |
| 9 | Grounding uneven (market strong; news/fund weak) | **CONFIRMED** | `market_analyst.py:51` "source of truth… do not invent"; news/fundamentals only "supporting evidence" |

## Temperature / sampling config

- Single global knob: `default_config.py:72` `"temperature": None` (⇒ each provider's
  default, ~1.0 for OpenAI). Env override `TRADINGAGENTS_TEMPERATURE`.
- Applied **identically to both** the deep and quick clients
  (`trading_graph.py:159-161`, `kwargs["temperature"]=…` only when set). **There is
  no per-agent temperature and no seed anywhere.** ⇒ default runs are maximally
  non-deterministic; this is the Phase-2 hypothesis, and there is no built-in way to
  pin one stage.

## Existing evaluation code — trust assessment

- **Gate A backtester** (`tradingagents/backtest/`: `engine.py`, `metrics.py`,
  `position.py`, `returns.py`) exists and is tested. It maps rating→position,
  computes forward return/alpha, walk-forward folds, and a bootstrap p-value.
  **Not trustworthy as the brief's harness as-is:** (a) it drives the same
  `propagate()` (so it can't run here either); (b) it does **not** disable the
  reflection/memory loop, so a multi-date same-ticker backtest feeds realized
  outcomes into later PMs — the brief's contamination #1; (c) only baseline is
  buy-and-hold SPY (not the 5 required baselines); (d) no multi-horizon, no factor
  attribution, no calibration. Treat as a scaffold to extend, not a result.
- **Reflection/memory** (`graph/reflection.py`, `agents/utils/memory.py`,
  `trading_graph._resolve_pending_entries`): a resolved memory entry embeds the
  realized `raw`/`alpha` and a reflection, then `get_past_context` injects it into
  the PM on the next same-ticker run. Confirmed mechanism for "fitting on the
  evaluation set." (Chronological dates ⇒ not naive look-ahead, but the measured
  system self-references prior eval outcomes; non-chronological dates or overlapping
  `holding_days` windows *would* be look-ahead. Flagged for Phase 3a.)

## Gate 1 verdict

**PASS on its own terms:** I can state, from source, exactly what every agent sees
(table above) — the input plumbing is fully determinable, no tangle.

**But the project is blocked at Phase 2** by the operational reality in
disconfirming-results #1–#2: no API key, no network budget, no run history, and no
ability to execute 450+ multi-minute LLM pipelines in this environment. Per the
standing rule ("if a phase gate fails, stop and say so… escalate"), I am stopping
before Phase 2 and escalating with options (see FINDINGS.md and the message to you).

## Self-critique (run before reporting)

- *Numbers that would collapse at small N?* — None reported; Phase 1 reports **zero**
  computed rates by design. Good.
- *Anything computed on memorized data?* — No computation performed.
- *Tuned on holdout?* — No.
- *Resting on a single run/ticker/regime?* — No runs exist; explicitly stated.
- *Described intended vs observed behaviour?* — Every claim is from a node's state
  access or config line, not prompt intent. The one place I could only infer intent
  (grounding "strength") is labeled as prompt-clause presence, not measured
  hallucination — that measurement is deferred to Phase 5.7.
- *Strongest argument the system is elaborate noise, and do I defeat it?* — The
  strongest argument: default temperature is unpinned and the final rating is a
  regex over one deep-model call whose inputs are twice-summarized text; nothing
  here shows the rating tracks the data. **I do not defeat it** — Phase 1 cannot;
  it only establishes the plumbing. Defeating/confirming it is exactly Phases 2–4,
  which cannot run here. That is the honest state.
