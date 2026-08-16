"""Phase 2 — output-variance harness (the cheapest kill test).

Runs each (ticker, date) pair N times and measures how stable the rating is,
per stage, so we can tell whether the pipeline emits a signal or noise.

Two modes so the expensive part runs where keys exist and the analysis runs
anywhere:

    # on a machine with an LLM API key + network + budget (resumable):
    python validation/variance_run.py collect --repeats 30

    # anywhere, from the collected JSONL (pure, no LLM):
    python validation/variance_run.py analyze

INSTRUMENTATION ONLY — this does not modify pipeline logic. Memory is isolated
per run (unique temp memory log) so variance reflects the COLD model, not the
reflection feedback loop; pass --with-memory to include it.

Gate 2 (hard):
  modal share >= 0.70 on >= 80% of pairs                 -> PROCEED
  median modal share in [0.50, 0.70)                      -> PROCEED_WITH_PINNING
  median modal share < 0.50                               -> STOP (system is noise)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import tempfile
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

from tradingagents.agents.utils.rating import RATINGS_5_TIER, parse_rating

# --- config: pairs (edit for your sector / regime spread) -------------------
# 5 tickers across sectors + volatility; 3 dates spanning regimes. Override with
# --tickers / --dates. Choose dates deliberately: at least one volatile and one
# quiet regime (and note Phase 3a will split on the model's training cutoff).
DEFAULT_TICKERS = ["NVDA", "XOM", "JPM", "PG", "TSLA"]
DEFAULT_DATES = ["2024-08-05", "2024-11-06", "2025-01-15"]

DATA_DIR = Path(__file__).resolve().parent / "data" / "variance"
RESULTS_JSONL = DATA_DIR / "results.jsonl"
REPORT_MD = Path(__file__).resolve().parent / "01_variance.md"

# 5-tier ordinal for spread; Sell=0 … Buy=4 (so Sell↔Overweight = 3).
_ORDINAL = {"Sell": 0, "Underweight": 1, "Hold": 2, "Overweight": 3, "Buy": 4}


# --- metrics (pure; unit-tested in tests/test_variance_metrics.py) ----------

def modal_rating(ratings: List[str]) -> Optional[str]:
    return Counter(ratings).most_common(1)[0][0] if ratings else None


def modal_share(ratings: List[str]) -> float:
    if not ratings:
        return 0.0
    return Counter(ratings).most_common(1)[0][1] / len(ratings)


def shannon_entropy(ratings: List[str]) -> float:
    """Entropy of the rating distribution, in bits."""
    n = len(ratings)
    if n == 0:
        return 0.0
    ent = 0.0
    for count in Counter(ratings).values():
        p = count / n
        ent -= p * math.log2(p)
    return ent


def tier_spread(ratings: List[str]) -> int:
    """Max minus min 5-tier ordinal over the runs (0 if fewer than 2 valid)."""
    ords = [_ORDINAL[r] for r in ratings if r in _ORDINAL]
    return (max(ords) - min(ords)) if len(ords) >= 2 else 0


def parse_trader_action(text: str) -> str:
    """Extract the Trader's 3-tier action (Buy/Hold/Sell) from its rendered plan."""
    low = (text or "").lower()
    # Prefer the explicit "Action:" / "FINAL TRANSACTION PROPOSAL:" lines.
    for line in low.splitlines():
        if "action" in line or "final transaction proposal" in line:
            for word in ("buy", "sell", "hold"):
                if word in line:
                    return word.capitalize()
    for word in ("buy", "sell", "hold"):
        if word in low:
            return word.capitalize()
    return "Hold"


def summarize_stage(ratings: List[str]) -> dict:
    return {
        "n": len(ratings),
        "modal": modal_rating(ratings),
        "modal_share": round(modal_share(ratings), 4),
        "entropy_bits": round(shannon_entropy(ratings), 4),
        "tier_spread": tier_spread(ratings),
        "distribution": dict(Counter(ratings)),
    }


def gate2_verdict(final_shares: List[float]) -> dict:
    """Apply the Gate 2 thresholds to the per-pair FINAL-rating modal shares."""
    if not final_shares:
        return {"verdict": "NOT_COMPUTED", "reason": "no pairs"}
    median_share = statistics.median(final_shares)
    frac_high = sum(1 for s in final_shares if s >= 0.70) / len(final_shares)
    if median_share < 0.50:
        verdict = "STOP"
    elif frac_high >= 0.80:
        verdict = "PROCEED"
    else:
        verdict = "PROCEED_WITH_PINNING"
    return {
        "verdict": verdict,
        "n_pairs": len(final_shares),
        "median_modal_share": round(median_share, 4),
        "frac_pairs_share_ge_0.70": round(frac_high, 4),
    }


# --- collection (needs an LLM key; resumable) -------------------------------

def _done_keys(jsonl: Path) -> set:
    if not jsonl.exists():
        return set()
    done = set()
    for line in jsonl.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            done.add((r["ticker"], r["date"], r["run"]))
    return done


def _run_once(ticker: str, date: str, with_memory: bool, temperature: Optional[float]) -> dict:
    """Run propagate once in an isolated config; return stage ratings."""
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    cfg = DEFAULT_CONFIG.copy()
    cfg["data_cache_dir"] = str(DATA_DIR / "cache")  # shared price cache (deterministic)
    cfg["results_dir"] = tempfile.mkdtemp(prefix="var_res_")
    if not with_memory:
        # Unique, non-existent memory log => empty => no reflection injection.
        cfg["memory_log_path"] = str(Path(tempfile.mkdtemp(prefix="var_mem_")) / "m.md")
    if temperature is not None:
        cfg["temperature"] = temperature

    state, final_rating = TradingAgentsGraph(config=cfg).propagate(ticker, date)
    return {
        "final_rating": final_rating,  # PM 5-tier (== parse_rating(final_trade_decision))
        "research_manager": parse_rating(state.get("investment_plan", "")),
        "trader_action": parse_trader_action(state.get("trader_investment_plan", "")),
        "pm_rating": parse_rating(state.get("final_trade_decision", "")),
    }


def collect(tickers, dates, repeats, with_memory, temperature):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    pairs = [(t, d) for t in tickers for d in dates]
    total = len(pairs) * repeats
    done = _done_keys(RESULTS_JSONL)
    est_calls = (total - len(done)) * 12
    print(f"{len(pairs)} pairs x {repeats} = {total} runs "
          f"({len(done)} already done); ~{est_calls} LLM calls remaining.")

    with RESULTS_JSONL.open("a") as f:
        for ticker, date in pairs:
            for i in range(repeats):
                if (ticker, date, i) in done:
                    continue
                rec = {"ticker": ticker, "date": date, "run": i}
                try:
                    rec.update(_run_once(ticker, date, with_memory, temperature))
                except Exception as e:  # a failed run is a datum, not a fabrication
                    rec["error"] = f"{type(e).__name__}: {e}"
                f.write(json.dumps(rec) + "\n")
                f.flush()
                tag = rec.get("final_rating", rec.get("error", "?"))
                print(f"  {ticker} {date} run {i}: {tag}")
    print(f"Wrote {RESULTS_JSONL}. Now: python {Path(__file__).name} analyze")


# --- analysis (pure; no LLM) ------------------------------------------------

def analyze(jsonl: Path = RESULTS_JSONL) -> dict:
    if not jsonl.exists():
        return {"verdict": "NOT_COMPUTED", "reason": f"no data at {jsonl}"}
    records = [json.loads(l) for l in jsonl.read_text().splitlines() if l.strip()]
    ok = [r for r in records if "error" not in r]
    errors = [r for r in records if "error" in r]

    pairs: Dict[tuple, List[dict]] = {}
    for r in ok:
        pairs.setdefault((r["ticker"], r["date"]), []).append(r)

    per_pair = []
    for (ticker, date), recs in sorted(pairs.items()):
        per_pair.append({
            "ticker": ticker, "date": date, "n_runs": len(recs),
            "final": summarize_stage([r["final_rating"] for r in recs]),
            "research_manager": summarize_stage([r["research_manager"] for r in recs]),
            "trader": summarize_stage([r["trader_action"] for r in recs]),
        })

    final_shares = [p["final"]["modal_share"] for p in per_pair]
    gate = gate2_verdict(final_shares)
    return {
        "n_records": len(records), "n_ok": len(ok), "n_errors": len(errors),
        "per_pair": per_pair, "gate": gate,
    }


def _stage_variance_entry(per_pair: List[dict]) -> str:
    """Where does variance enter? Compare mean modal share across stages."""
    if not per_pair:
        return "NOT_COMPUTED: no pairs"
    def mean_share(stage):
        return statistics.mean(p[stage]["modal_share"] for p in per_pair)
    rm, tr, fin = mean_share("research_manager"), mean_share("trader"), mean_share("final")
    return (f"mean modal share — Research Manager {rm:.2f}, Trader {tr:.2f}, "
            f"Final/PM {fin:.2f} (lower = more variance enters at that stage)")


def write_report(result: dict) -> None:
    if result.get("verdict") == "NOT_COMPUTED":
        REPORT_MD.write_text(
            f"# Phase 2 — Output variance\n\n**NOT_COMPUTED:** {result['reason']}\n\n"
            "Run `python validation/variance_run.py collect` on a machine with an "
            "LLM API key first (see validation/RUNBOOK.md).\n"
        )
        print(f"NOT_COMPUTED — wrote {REPORT_MD}")
        return

    g = result["gate"]
    lines = [
        "# Phase 2 — Output variance", "",
        f"N runs: {result['n_ok']} ok, {result['n_errors']} errored "
        f"(errors are data, not dropped).", "",
        "## Gate 2 verdict (disconfirming first)",
        f"- **Verdict: {g['verdict']}**",
        f"- Median modal share (final rating): {g.get('median_modal_share')}  "
        f"(N pairs = {g.get('n_pairs')})",
        f"- Pairs with modal share ≥ 0.70: {g.get('frac_pairs_share_ge_0.70')}",
        "",
        "Thresholds: ≥0.70 on ≥80% pairs → PROCEED · median 0.50–0.70 → "
        "PROCEED_WITH_PINNING · median <0.50 → STOP.",
        "",
        f"## Where variance enters\n{_stage_variance_entry(result['per_pair'])}",
        "",
        "## Per pair (final rating unless noted)",
        "| ticker | date | n | modal | share | entropy(bits) | tier spread | RM share | Trader share |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for p in result["per_pair"]:
        fs = p["final"]
        lines.append(
            f"| {p['ticker']} | {p['date']} | {p['n_runs']} | {fs['modal']} | "
            f"{fs['modal_share']} | {fs['entropy_bits']} | {fs['tier_spread']} | "
            f"{p['research_manager']['modal_share']} | {p['trader']['modal_share']} |"
        )
    lines += ["", "Raw per-run records: `validation/data/variance/results.jsonl`."]
    REPORT_MD.write_text("\n".join(lines) + "\n")
    print(f"Verdict {g['verdict']} — wrote {REPORT_MD}")


def main():
    ap = argparse.ArgumentParser(description="Phase 2 output-variance harness")
    sub = ap.add_subparsers(dest="mode", required=True)

    c = sub.add_parser("collect", help="run propagate N times per pair (needs LLM key)")
    c.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    c.add_argument("--dates", default=",".join(DEFAULT_DATES))
    c.add_argument("--repeats", type=int, default=30)
    c.add_argument("--with-memory", action="store_true",
                   help="include the reflection feedback loop (default: isolated/off)")
    c.add_argument("--temperature", type=float, default=None,
                   help="pin sampling temperature (default: provider default / ungated)")

    sub.add_parser("analyze", help="compute metrics + Gate 2 from the JSONL (no LLM)")

    args = ap.parse_args()
    if args.mode == "collect":
        collect(
            [t.strip() for t in args.tickers.split(",") if t.strip()],
            [d.strip() for d in args.dates.split(",") if d.strip()],
            args.repeats, args.with_memory, args.temperature,
        )
    else:
        write_report(analyze())


if __name__ == "__main__":
    main()
