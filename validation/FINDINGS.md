# FINDINGS — running log of deferred / refused / escalated items

## E1 — BLOCKER: Phases 2–5 cannot execute in this environment
- No LLM API key set (all providers unset); no run history (0 `full_states_log`,
  no memory log). Phase 2 needs 450 multi-minute runs; Phases 3–5 need more.
- Status: **NOT_COMPUTED — no key, no network budget, no wall-clock.**
- Requires: an execution environment with a provider key, network egress, token
  budget (order-of-magnitude thousands of LLM calls), and hours of runtime.
- Escalated at Gate 1. Recommendation options in the gate report.

## F1 — Doc correction (point 5): reports enter the chain twice
- The four analyst reports are read by both the Bull/Bear researchers **and** the
  three risk debators (`aggressive_debator.py:16-19` etc.), not once.
- The doc's "every arrow is a lossy summarization" telephone framing is imprecise;
  the risk stage re-grounds on raw reports. Hop count is defensible.
- Action: corrected in `00_recon.md` point 5; will fold into the Phase-6 rewrite.
- NOT a pipeline change (doc only).

## F2 — Gate A backtester shares the contamination defect
- `tradingagents/backtest/` does not disable reflection/memory, so a multi-date
  same-ticker backtest injects prior realized outcomes into later PMs.
- Also: single baseline (SPY B&H), no multi-horizon, no factor attribution.
- Action: do not trust Gate A numbers as-is; the Phase-4 harness must run with
  memory quarantined (brief repair #1) and add the 5 baselines + factor model.

## F3 — No per-agent temperature / no seed
- Global `temperature=None` applied to both models (`trading_graph.py:159-161`).
- If Phase 2 shows the system is only usable when pinned, there is currently **no
  code path to seed or set temperature per agent** — a fix would be required and
  would itself be a pipeline change (out of scope until Phase 5).

## Instrument status
- Phase 2 harness `validation/variance_run.py` is **built and unit-tested**
  (`tests/test_variance_metrics.py`, 15 tests: metrics + Gate 2 + analyze). The
  pure analysis/gate math is verified; only `collect` (the LLM runs) is deferred.
  See `validation/RUNBOOK.md`.

## Deferred measurements (owed a number, not yet computable)
- Output variance / modal share / entropy (Phase 2) — NOT_COMPUTED (E1); harness ready.
- Look-ahead / pre-vs-post training-cutoff gap (Phase 3a) — NOT_COMPUTED (E1).
- Baselines 1–5 vs pipeline (Phase 3b) — NOT_COMPUTED (E1).
- Hit rate, multi-horizon alpha, IR/Sharpe, calibration, factor alpha (Phase 4) —
  NOT_COMPUTED (E1).
- Hallucination rate on 100 sampled news/fundamentals claims (Phase 5.7) — NOT_COMPUTED (E1).
