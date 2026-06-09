"""Dashboard data layer (dashboard/data.py) — pure, offline, no streamlit."""

import json

import pandas as pd
import pytest

from dashboard import data


# --- parse_pct -----------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("+2.5%", 0.025),
    ("-1.3%", -0.013),
    ("0.05", 0.05),
    ("n/a", None),
    (None, None),
    ("", None),
    ("garbage", None),
])
def test_parse_pct(value, expected):
    result = data.parse_pct(value)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


# --- backtests -----------------------------------------------------------

def _write_run(root, name, summary, equity_rows=None, trades_rows=None):
    run = root / name
    run.mkdir(parents=True)
    (run / "summary.json").write_text(json.dumps(summary))
    if equity_rows is not None:
        pd.DataFrame(equity_rows).to_csv(run / "equity.csv", index=False)
    if trades_rows is not None:
        pd.DataFrame(trades_rows).to_csv(run / "trades.csv", index=False)
    return run


def test_list_backtest_runs_newest_first_and_skips_incomplete(tmp_path):
    _write_run(tmp_path, "20240101_000000", {"verdict": "FAIL"})
    _write_run(tmp_path, "20240301_120000", {"verdict": "PASS"})
    (tmp_path / "not_a_run").mkdir()  # no summary.json -> ignored

    runs = data.list_backtest_runs(tmp_path)
    assert [r.name for r in runs] == ["20240301_120000", "20240101_000000"]


def test_list_backtest_runs_missing_root(tmp_path):
    assert data.list_backtest_runs(tmp_path / "nope") == []


def test_load_backtest(tmp_path):
    run = _write_run(
        tmp_path, "20240301_120000",
        {"verdict": "PASS", "sharpe": 1.2},
        equity_rows=[{"date": "2024-01-01", "equity": 1.0}, {"date": "2024-02-01", "equity": 1.1}],
        trades_rows=[{"ticker": "NVDA", "net_return": 0.02}],
    )
    bt = data.load_backtest(run)
    assert bt["summary"]["verdict"] == "PASS"
    assert list(bt["equity"]["equity"]) == [1.0, 1.1]
    assert bt["trades"].iloc[0]["ticker"] == "NVDA"
    assert bt["name"] == "20240301_120000"


# --- journal -------------------------------------------------------------

_MEMORY = (
    "[2024-05-10 | NVDA | Buy | +5.00% | +2.00% | 5d]\n\n"
    "DECISION:\nBuy thesis text.\n\nREFLECTION:\nWorked out.\n\n"
    "<!-- ENTRY_END -->\n\n"
    "[2024-05-12 | AAPL | Hold | pending]\n\n"
    "DECISION:\nHold thesis.\n\n"
    "<!-- ENTRY_END -->\n\n"
)


def _journal_config(tmp_path):
    log = tmp_path / "trading_memory.md"
    log.write_text(_MEMORY)
    return {"memory_log_path": str(log), "memory_log_max_entries": None}


def test_load_journal_parses_entries(tmp_path):
    df = data.load_journal(_journal_config(tmp_path))
    assert len(df) == 2
    nvda = df[df["ticker"] == "NVDA"].iloc[0]
    assert nvda["status"] == "resolved"
    assert nvda["raw_return"] == pytest.approx(0.05)
    assert nvda["alpha_return"] == pytest.approx(0.02)
    assert nvda["reflection"] == "Worked out."
    aapl = df[df["ticker"] == "AAPL"].iloc[0]
    assert aapl["status"] == "pending"
    assert pd.isna(aapl["raw_return"])  # None coerced to NaN in the numeric column


def test_load_journal_missing_file_is_empty(tmp_path):
    df = data.load_journal({"memory_log_path": str(tmp_path / "none.md")})
    assert df.empty
    assert list(df.columns) == data._JOURNAL_COLUMNS


def test_journal_summary(tmp_path):
    df = data.load_journal(_journal_config(tmp_path))
    js = data.journal_summary(df)
    assert js["n_resolved"] == 1
    assert js["n_pending"] == 1
    assert js["win_rate"] == pytest.approx(1.0)
    assert js["mean_return"] == pytest.approx(0.05)
    assert js["mean_alpha"] == pytest.approx(0.02)


def test_journal_summary_empty():
    js = data.journal_summary(data.load_journal({"memory_log_path": "/nonexistent"}))
    assert js == {"n_resolved": 0, "n_pending": 0, "win_rate": 0.0,
                  "mean_return": 0.0, "mean_alpha": 0.0}


# --- decision runs -------------------------------------------------------

_RUN = {
    "company_of_interest": "NVDA",
    "trade_date": "2024-05-10",
    "market_report": "Uptrend, RSI 60.",
    "sentiment_report": "Bullish chatter.",
    "news_report": "Strong earnings.",
    "fundamentals_report": "High margins.",
    "investment_debate_state": {
        "bull_history": "Bull: growth runway.",
        "bear_history": "Bear: valuation rich.",
        "history": "...",
        "current_response": "...",
        "judge_decision": "Manager: lean bullish.",
    },
    "trader_investment_decision": "Enter long, stop at -5%.",
    "risk_debate_state": {
        "aggressive_history": "Push it.",
        "conservative_history": "Trim size.",
        "neutral_history": "Balanced.",
        "history": "...",
        "judge_decision": "...",
    },
    "investment_plan": "Manager plan: accumulate.",
    "final_trade_decision": "Rating: Buy\nThesis: strong setup.",
}


def _write_decision_run(results_dir, ticker, date, payload):
    d = results_dir / ticker / "TradingAgentsStrategy_logs"
    d.mkdir(parents=True)
    p = d / f"full_states_log_{date}.json"
    p.write_text(json.dumps(payload))
    return p


def test_list_decision_runs_newest_first(tmp_path):
    _write_decision_run(tmp_path, "NVDA", "2024-05-10", _RUN)
    _write_decision_run(tmp_path, "AAPL", "2024-06-01", _RUN)
    runs = data.list_decision_runs(tmp_path)
    assert [(r["ticker"], r["date"]) for r in runs] == [("AAPL", "2024-06-01"), ("NVDA", "2024-05-10")]


def test_list_decision_runs_missing_root(tmp_path):
    assert data.list_decision_runs(tmp_path / "nope") == []


def test_decision_rating_and_load(tmp_path):
    p = _write_decision_run(tmp_path, "NVDA", "2024-05-10", _RUN)
    raw = data.load_decision_run(p)
    assert data.decision_rating(raw) == "Buy"


def test_decision_stages_structure_and_content():
    stages = data.decision_stages(_RUN)
    labels = [s["label"] for s in stages]
    assert labels[:4] == ["Market Analyst", "Sentiment Analyst", "News Analyst", "Fundamentals Analyst"]
    # final_trade_decision is rendered separately, not as a stage
    assert "Portfolio Manager" not in labels
    bull = next(s for s in stages if s["label"] == "Bull Researcher")
    assert bull["content"] == "Bull: growth runway."
    assert bull["group"] == "Research debate"
    mgr = next(s for s in stages if s["label"] == "Research Manager")
    assert mgr["content"] == "Manager plan: accumulate."


def test_decision_stages_research_manager_falls_back_to_judge():
    raw = dict(_RUN)
    raw["investment_plan"] = ""  # force fallback to judge_decision
    mgr = next(s for s in data.decision_stages(raw) if s["label"] == "Research Manager")
    assert mgr["content"] == "Manager: lean bullish."


def test_decision_stages_tolerates_missing_fields():
    stages = data.decision_stages({"final_trade_decision": "Rating: Hold"})
    assert all(s["content"] == "" for s in stages)  # nothing crashes, all empty
