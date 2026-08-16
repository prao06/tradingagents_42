"""Artifact -> Supabase row mappers (server/store.py) — pure, offline."""

import pandas as pd

from server import store, demo
from dashboard import data


def _cfg(tmp_path):
    return {
        "results_dir": str(tmp_path / "results"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "benchmark_map": {"": "SPY"},
        "memory_log_max_entries": None,
    }


def test_records_is_nan_safe():
    df = pd.DataFrame([{"a": 1.0, "b": float("nan")}])
    assert store._records(df) == [{"a": 1.0, "b": None}]
    assert store._records(pd.DataFrame()) == []


def test_backtest_and_run_and_journal_mappers(tmp_path):
    cfg = _cfg(tmp_path)
    demo.seed_demo(cfg)  # writes a backtest, 2 runs, journal (2 entries)

    # backtest row
    run_dir = data.list_backtest_runs(data.backtests_root(cfg))[0]
    bt_row = store.backtest_to_row(data.load_backtest(run_dir), user_id="u1")
    assert bt_row["user_id"] == "u1"
    assert bt_row["name"] == run_dir.name
    assert "verdict" in bt_row["summary"]
    assert isinstance(bt_row["equity"], list) and isinstance(bt_row["trades"], list)

    # decision run row
    r = next(x for x in data.list_decision_runs(data.decisions_root(cfg)) if x["ticker"] == "NVDA")
    raw = data.load_decision_run(r["path"])
    run_row = store.decision_run_to_row(raw, r["ticker"], r["date"], user_id="u1")
    assert run_row["ticker"] == "NVDA" and run_row["rating"] == "Buy"
    assert any(s["label"] == "Market Analyst" for s in run_row["stages"])

    # journal rows: one resolved (with numeric return), one pending (None)
    rows = store.journal_rows(data.load_journal(cfg), user_id="u1")
    assert len(rows) == 2
    resolved = next(x for x in rows if x["status"] == "resolved")
    pending = next(x for x in rows if x["status"] == "pending")
    assert resolved["raw_return"] is not None
    assert pending["raw_return"] is None
    assert all(x["user_id"] == "u1" for x in rows)


def test_collect_artifacts_gathers_everything(tmp_path):
    cfg = _cfg(tmp_path)
    demo.seed_demo(cfg)
    arts = store.collect_artifacts(cfg, user_id="u1")
    assert len(arts["backtests"]) == 1
    assert len(arts["decision_runs"]) == 2
    assert len(arts["journal"]) == 2
