# Validation runbook

The measurement phases run `propagate()` many times, which needs an LLM API key,
network egress, token budget, and hours of wall-clock — none of which exist in
the sandbox where this harness was written. Run the `collect` steps on your own
machine (or any keyed environment), then hand the JSONL back for analysis, or run
`analyze` yourself.

## One-time setup
```bash
git checkout claude/pipeline-validation
uv sync                      # or: pip install -e .
export OPENAI_API_KEY=sk-...      # or another provider via TRADINGAGENTS_LLM_PROVIDER
# optional: TRADINGAGENTS_DEEP_THINK_LLM / TRADINGAGENTS_QUICK_THINK_LLM to pick models
```

## Phase 2 — output variance
```bash
# ~450 runs × ~12 LLM calls ≈ 5–6k calls. Budget accordingly; it is RESUMABLE
# (re-run to continue; already-done (ticker,date,run) are skipped).
python validation/variance_run.py collect --repeats 30
# then, anywhere (no key needed):
python validation/variance_run.py analyze      # writes validation/01_variance.md
```
Options: `--tickers NVDA,XOM,JPM,PG,TSLA` `--dates 2024-08-05,2024-11-06,2025-01-15`
(choose dates for a volatile + a quiet regime), `--temperature 0.0` to test the
pinned system, `--with-memory` to include the reflection loop (default: isolated
off, so variance reflects the cold model).

### Cost / time estimate
- Per run: ~12 LLM calls, minutes each depending on model. 450 runs is on the
  order of several hours and (model-dependent) tens to low-hundreds of dollars.
- Start with a smoke: `--tickers NVDA --dates 2024-08-05 --repeats 5` (~60 calls)
  to confirm the plumbing and see a real modal-share number before committing.

## Gate 2 (hard — from validation/01_variance.md)
- median modal share ≥ 0.70 on ≥ 80% of pairs → **PROCEED** to Phase 3.
- median modal share 0.50–0.70 → **PROCEED_WITH_PINNING** (document that the
  ungated system is unusable; re-run with `--temperature 0.0`).
- median modal share < 0.50 → **STOP.** The system has no stable output; report
  and escalate. Phases 3+ would be measuring noise.

Also read "Where variance enters" in the report: if the first four stages are
stable and one stage (e.g. Research Manager) is a coin flip, that localizes the
defect.

## Then send me
`validation/data/variance/results.jsonl` (or just `validation/01_variance.md`),
and I'll write the Phase 2 report with the Gate 2 verdict and the recommendation
(continue / descope / kill). Phases 3–5 harnesses are built only after Gate 2
passes, per the brief.
