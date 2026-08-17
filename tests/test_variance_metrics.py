"""Phase 2 variance metrics + Gate 2 logic (validation/variance_run.py) — offline.

The collection step needs an LLM key and can't run in CI; these verify the pure
analysis/gate math so the numbers it will later produce are trustworthy.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "validation"))
import variance_run as vr  # noqa: E402


def test_modal_rating_and_share():
    assert vr.modal_rating(["Buy", "Buy", "Hold"]) == "Buy"
    assert vr.modal_share(["Buy", "Buy", "Hold"]) == pytest.approx(2 / 3)
    assert vr.modal_share([]) == 0.0


@pytest.mark.parametrize("ratings,bits", [
    (["Buy", "Buy"], 0.0),
    (["Buy", "Sell"], 1.0),
    (["Buy", "Hold", "Sell", "Overweight"], 2.0),
])
def test_entropy_known_values(ratings, bits):
    assert vr.shannon_entropy(ratings) == pytest.approx(bits)


def test_entropy_skewed():
    # 3/4 vs 1/4 -> 0.8113 bits
    assert vr.shannon_entropy(["Buy", "Buy", "Buy", "Sell"]) == pytest.approx(0.8113, abs=1e-3)


@pytest.mark.parametrize("ratings,spread", [
    (["Sell", "Overweight"], 3),
    (["Sell", "Buy"], 4),
    (["Hold", "Hold"], 0),
    (["Buy"], 0),          # fewer than 2 valid
])
def test_tier_spread(ratings, spread):
    assert vr.tier_spread(ratings) == spread


@pytest.mark.parametrize("text,action", [
    ("**Action**: Buy\nReasoning: ...", "Buy"),
    ("FINAL TRANSACTION PROPOSAL: **SELL**", "Sell"),
    ("We should hold the position for now.", "Hold"),
    ("", "Hold"),
])
def test_parse_trader_action(text, action):
    assert vr.parse_trader_action(text) == action


def test_gate2_thresholds():
    assert vr.gate2_verdict([0.9, 0.9, 0.85, 0.8, 0.95])["verdict"] == "PROCEED"
    assert vr.gate2_verdict([0.6, 0.6, 0.6])["verdict"] == "PROCEED_WITH_PINNING"
    assert vr.gate2_verdict([0.4, 0.3, 0.45])["verdict"] == "STOP"
    assert vr.gate2_verdict([])["verdict"] == "NOT_COMPUTED"


def test_analyze_over_synthetic_jsonl(tmp_path):
    recs = [
        {"ticker": "NVDA", "date": "2024-08-05", "run": 0, "final_rating": "Buy",
         "research_manager": "Buy", "trader_action": "Buy", "pm_rating": "Buy"},
        {"ticker": "NVDA", "date": "2024-08-05", "run": 1, "final_rating": "Buy",
         "research_manager": "Buy", "trader_action": "Buy", "pm_rating": "Buy"},
        {"ticker": "NVDA", "date": "2024-08-05", "run": 2, "final_rating": "Buy",
         "research_manager": "Buy", "trader_action": "Hold", "pm_rating": "Buy"},
        {"ticker": "NVDA", "date": "2024-08-05", "run": 3, "final_rating": "Hold",
         "research_manager": "Buy", "trader_action": "Buy", "pm_rating": "Hold"},
        {"ticker": "NVDA", "date": "2024-08-05", "run": 4, "error": "RuntimeError: boom"},
    ]
    p = tmp_path / "results.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in recs))

    out = vr.analyze(p)
    assert out["n_ok"] == 4 and out["n_errors"] == 1
    pair = out["per_pair"][0]
    assert pair["final"]["modal"] == "Buy"
    assert pair["final"]["modal_share"] == pytest.approx(0.75)
    assert pair["final"]["tier_spread"] == 2          # Buy(4) - Hold(2)
    assert pair["research_manager"]["modal_share"] == pytest.approx(1.0)
    assert out["gate"]["verdict"] == "PROCEED"        # single pair, share 0.75 >= 0.70
