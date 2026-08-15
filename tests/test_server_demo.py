"""Demo seeder (server/demo.py) — pure, offline, no LLM/network/FastAPI."""

from server import demo
from dashboard import data


def _cfg(tmp_path):
    return {
        "results_dir": str(tmp_path / "results"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "benchmark_map": {"": "SPY"},
        "memory_log_max_entries": None,
    }


def test_dry_stubs_are_deterministic():
    p1, r1, _ = demo.dry_stubs(seed=0)
    p2, r2, _ = demo.dry_stubs(seed=0)
    assert p1("NVDA", "2024-01-01") == p2("NVDA", "2024-01-01")
    assert r1("NVDA", "2024-01-01", 5, "SPY") == r2("NVDA", "2024-01-01", 5, "SPY")


def test_seed_demo_writes_readable_artifacts(tmp_path):
    cfg = _cfg(tmp_path)
    counts = demo.seed_demo(cfg)
    assert counts == {"backtests": 1, "runs": 2, "journal_entries": 2}

    # Backtest is loadable via the dashboard data layer.
    runs = data.list_backtest_runs(data.backtests_root(cfg))
    assert len(runs) == 1
    assert "verdict" in data.load_backtest(runs[0])["summary"]

    # Decision runs are discoverable and rate-parseable.
    druns = data.list_decision_runs(data.decisions_root(cfg))
    assert {r["ticker"] for r in druns} == {"NVDA", "AAPL"}
    nvda = next(r for r in druns if r["ticker"] == "NVDA")
    assert data.decision_rating(data.load_decision_run(nvda["path"])) == "Buy"

    # Journal has one resolved (with outcome) + one pending.
    df = data.load_journal(cfg)
    js = data.journal_summary(df)
    assert js["n_resolved"] == 1 and js["n_pending"] == 1
    assert js["mean_return"] > 0
