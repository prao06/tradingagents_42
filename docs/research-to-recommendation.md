# How a recommendation is actually produced — and how to test the logic

A trace of what happens inside `propagate(ticker, date)`, stage by stage, based
on the real code. The goal here is to expose the **decision points worth
scrutinizing**, so you can test whether the research→recommendation logic is
sound. File references are given so you can verify each claim.

## The flow, end to end
```
propagate(ticker, date)
  ├─ resolve instrument identity (deterministic, once) ─► injected into EVERY analyst
  └─ load past lessons (resolved memory)               ─► injected ONLY into the Portfolio Manager

  ANALYSTS  — sequential; each is BLIND to the others (message context wiped between them)
    Market       get_stock_data / get_indicators + VERIFIED SNAPSHOT   (strong grounding)
    Sentiment    pre-fetched news + StockTwits + Reddit, structured out (medium grounding)
    News         get_news / get_global_news                            (weak grounding)
    Fundamentals income/balance/cashflow statements                    (weak grounding)
      → 4 reports on state, all date-bounded to `date`

  RESEARCH DEBATE  — sees the 4 reports (NOT memory)
    Bull ⇄ Bear   (default: 1 exchange)  → transcript

  RESEARCH MANAGER (deep model) — judges ONLY the transcript, not the 4 reports
    → investment_plan: 5-tier recommendation + rationale + strategic actions

  TRADER (quick model) — sees ONLY investment_plan (not the reports, not the debate)
    → 3-tier action (Buy/Hold/Sell) + entry/stop/sizing

  RISK DEBATE — sees the 4 reports + the TRADER's plan; each voice rebuts the others
    Aggressive → Conservative → Neutral   (default: 1 each)  → risk transcript

  PORTFOLIO MANAGER (deep model) — sees risk transcript + research plan + trader plan + PAST LESSONS
    → PortfolioDecision: 5-tier RATING + thesis + price target + horizon

  parse_rating(...) → Buy / Overweight / Hold / Underweight / Sell   (deterministic regex, no LLM)
  return (full_state, rating)

  AFTER THE RUN: decision logged "pending".
  On the NEXT same-ticker run: fetch 5-day forward return + alpha, write a 2–4 sentence
  reflection, mark resolved. Resolved lessons feed FUTURE runs — the Portfolio Manager only.
```
Wiring: `graph/setup.py` (nodes/edges), `graph/conditional_logic.py` (loops).

## What each stage sees and decides

| Stage | Model | Sees | Produces | Lossy? |
|---|---|---|---|---|
| Analysts ×4 | quick | date-bounded tool data + instrument identity; **not each other** | 4 text reports | data → prose |
| Bull / Bear | quick | the 4 reports + opponent's last turn | debate transcript | reports → rhetoric |
| Research Manager | **deep** | **only the transcript** | 5-tier rec + plan | transcript → 1 plan |
| Trader | quick | **only the manager's plan** | 3-tier action + levels | 5-tier → 3-tier |
| Risk ×3 | quick | the 4 reports + **the trader's plan** | risk transcript | plan → rhetoric |
| Portfolio Manager | **deep** | risk transcript + research plan + trader plan + **memory** | **final 5-tier rating** | 3-tier → 5-tier |

## The nine logic points to test

These are the design choices most likely to affect whether the output is
trustworthy. Each is a concrete experiment.

1. **Analysts are blind to each other.** They run sequentially and the message
   context is wiped between them (`agent_utils.py` msg-delete node; `setup.py:107-109`).
   The News analyst can't build on Fundamentals, etc. *Test:* does cross-signal
   reasoning (e.g. "cheap **and** improving sentiment") ever appear, or only at
   the debate stage?

2. **The Research Manager judges the debate, not the data.** It receives **only
   the bull/bear transcript**, not the four reports (`research_manager.py:20-23`).
   If the debate misstates or omits a report, the manager can't catch it — it's
   scoring persuasiveness, not evidence. *Test:* compare the manager's rationale
   against the actual reports in the run log; look for claims that came from
   rhetoric, not data.

3. **The Trader can't see the reports it's told to "anchor" in.** Its prompt says
   "anchor your reasoning in the analysts' reports," but it only receives
   `investment_plan` (`trader.py:24-26`, `44-45`). *Test:* does the trader ever
   cite something not in the plan? It structurally can't.

4. **Rating tier compression then re-expansion.** Manager = 5-tier → Trader
   collapses to 3-tier Buy/Hold/Sell (`schemas.py:42-53`) → PM re-expands to
   5-tier. Degree (Overweight/Underweight) is dropped at the trader and re-
   invented at the PM. *Test:* do the manager's 5-tier and the PM's final 5-tier
   agree? Where they diverge, why?

5. **The final rating is ~5 lossy LLM hops from the data.** data → analyst prose →
   debate → plan → risk debate → PM. Every arrow is an LLM summarization. *Test:*
   change one input report and see whether the final rating moves at all — or
   whether accumulated framing dominates.

6. **"Debate" is one exchange by default.** `max_debate_rounds=1` → a single
   Bull then Bear; `max_risk_discuss_rounds=1` → one of each risk voice
   (`conditional_logic.py:52-73`). It's not a convergent argument. *Test:* set
   `TRADINGAGENTS_MAX_DEBATE_ROUNDS=3` / `TRADINGAGENTS_MAX_RISK_ROUNDS=2` and see
   if ratings change.

7. **Memory reaches only the Portfolio Manager.** Past realized alpha + reflections
   are injected into the PM prompt only (`portfolio_manager.py:35`), not the
   analysts or researchers. It's also a free-text paragraph the PM may ignore.
   *Test:* seed a strong past lesson and check whether the final rating reflects it.

8. **Evaluation horizon may not match the decision horizon.** Reflection scores the
   call on a **fixed 5-day** forward return vs. benchmark (`trading_graph.py`
   `_fetch_returns`, default `holding_days=5`), but the PM emits a `time_horizon`
   that can be weeks/months. *Test:* is a "6-month accumulate" call really being
   graded on 5-day alpha? That mismatch can teach the wrong lesson.

9. **Grounding is uneven.** Market has strong anti-hallucination grounding (the
   verified snapshot, `market_data_validator.py`; "source of truth… do not
   invent"). News and Fundamentals have the weakest ("supporting evidence" only).
   *Test:* check news/fundamentals claims in the run log against the tool output —
   these are the likeliest place for fabricated specifics.

## How to run these tests
- **Inspect any run:** every stage's actual text is saved to
  `~/.tradingagents/logs/<ticker>/TradingAgentsStrategy_logs/full_states_log_<date>.json`
  (analyst reports, both debates, trader plan, final decision). The **Decision
  Detail** dashboard view renders exactly this.
- **Determinism:** run the same `(ticker, date)` twice and diff the ratings — the
  default reasoning model varies run to run.
- **Rounds:** the two env vars in point 6.
- **Isolation:** run with `selected_analysts=["market"]` vs. all four to see how
  much each analyst actually moves the final rating.

## Bottom line
The architecture is a chain of LLM summarizations with two deliberate judgment
gates (Research Manager, Portfolio Manager). Its strengths are the deterministic
grounding on price data and the transparent, inspectable transcript. Its logical
risks are that **judgments are made on compressed rhetoric rather than the raw
evidence** (points 2–3), **conviction degree is lost and re-invented** (point 4),
and **the feedback loop grades the wrong horizon and reaches only the last agent**
(points 7–8). Test those first.
