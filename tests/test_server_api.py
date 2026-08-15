"""FastAPI app (server/app.py) — HTTP layer.

Skipped when FastAPI/httpx aren't installed (e.g. base CI), so it never breaks
the core suite; run with the ``server`` extra to exercise it.
"""

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from server.app import create_app  # noqa: E402


def _cfg(tmp_path):
    return {
        "results_dir": str(tmp_path / "results"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "benchmark_map": {"": "SPY"},
        "memory_log_max_entries": None,
    }


def _seed_backtest(cfg):
    from pathlib import Path
    root = Path(cfg["results_dir"]) / "backtests" / "20240601_000000"
    root.mkdir(parents=True)
    (root / "summary.json").write_text(json.dumps({
        "verdict": "FAIL", "total_return": -0.05, "sharpe": -0.5,
        "p_value": 1.0, "pit": True, "folds": [],
    }))
    import pandas as pd
    pd.DataFrame([{"date": "2024-01-01", "equity": 1.0}]).to_csv(root / "equity.csv", index=False)
    pd.DataFrame([{"ticker": "NVDA", "net_return": -0.05}]).to_csv(root / "trades.csv", index=False)


def _seed_run(cfg):
    from pathlib import Path
    d = Path(cfg["results_dir"]) / "NVDA" / "TradingAgentsStrategy_logs"
    d.mkdir(parents=True)
    (d / "full_states_log_2024-05-10.json").write_text(json.dumps({
        "market_report": "Uptrend.", "final_trade_decision": "Rating: Buy",
        "investment_debate_state": {"bull_history": "bull", "bear_history": "bear"},
        "risk_debate_state": {},
    }))


def test_health_and_reads(tmp_path):
    cfg = _cfg(tmp_path)
    _seed_backtest(cfg)
    _seed_run(cfg)
    client = TestClient(create_app(config=cfg, runner=lambda t, d: None))

    assert client.get("/api/health").json()["status"] == "ok"

    bts = client.get("/api/backtests").json()
    assert bts[0]["name"] == "20240601_000000" and bts[0]["verdict"] == "FAIL"

    detail = client.get("/api/backtests/20240601_000000").json()
    assert detail["equity"][0]["equity"] == 1.0 and len(detail["trades"]) == 1

    runs = client.get("/api/runs").json()
    assert runs == [{"ticker": "NVDA", "date": "2024-05-10", "rating": "Buy"}]

    rd = client.get("/api/runs/NVDA/2024-05-10").json()
    assert rd["rating"] == "Buy"
    assert any(s["label"] == "Market Analyst" and s["content"] == "Uptrend." for s in rd["stages"])


def test_missing_resources_404(tmp_path):
    client = TestClient(create_app(config=_cfg(tmp_path), runner=lambda t, d: None))
    assert client.get("/api/backtests/nope").status_code == 404
    assert client.get("/api/runs/NVDA/2024-01-01").status_code == 404
    assert client.get("/api/jobs/job-1").status_code == 404


def test_submit_run_blocked_without_key(tmp_path, monkeypatch):
    from server.app import _LLM_KEYS
    for k in _LLM_KEYS:  # conftest sets these to "placeholder"; clear them all
        monkeypatch.delenv(k, raising=False)
    client = TestClient(create_app(config=_cfg(tmp_path), runner=lambda t, d: None))
    assert client.post("/api/runs", json={"ticker": "NVDA", "date": "2024-05-10"}).status_code == 400


def test_submit_run_executes_with_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    ran = []
    app = create_app(config=_cfg(tmp_path), runner=lambda t, d: ran.append((t, d)))
    client = TestClient(app)
    resp = client.post("/api/runs", json={"ticker": "NVDA", "date": "2024-05-10"})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    result = app.state.jobs.wait(job_id)
    assert result["status"] == "done"
    assert ran == [("NVDA", "2024-05-10")]
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "done"


def test_run_api_key_enforced(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    ran = []
    app = create_app(config=_cfg(tmp_path), runner=lambda t, d: ran.append(1), run_api_key="secret")
    client = TestClient(app)
    body = {"ticker": "NVDA", "date": "2024-05-10"}

    assert client.post("/api/runs", json=body).status_code == 401              # missing header
    assert client.post("/api/runs", json=body, headers={"X-API-Key": "nope"}).status_code == 401
    ok = client.post("/api/runs", json=body, headers={"X-API-Key": "secret"})
    assert ok.status_code == 200
    app.state.jobs.wait(ok.json()["job_id"])
    assert ran == [1]


def test_run_api_key_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("RUN_API_KEY", "envsecret")
    client = TestClient(create_app(config=_cfg(tmp_path), runner=lambda t, d: None))
    body = {"ticker": "NVDA", "date": "2024-05-10"}
    assert client.post("/api/runs", json=body).status_code == 401
    assert client.post("/api/runs", json=body, headers={"X-API-Key": "envsecret"}).status_code == 200


def test_submit_backtest_dry_run_needs_no_key(tmp_path, monkeypatch):
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    app = create_app(config=_cfg(tmp_path), runner=lambda t, d: None)
    client = TestClient(app)
    resp = client.post("/api/backtests", json={
        "tickers": ["NVDA", "AAPL"], "start": "2024-01-01", "end": "2024-04-01", "dry_run": True,
    })
    assert resp.status_code == 200
    assert app.state.jobs.wait(resp.json()["job_id"])["status"] == "done"
    assert len(client.get("/api/backtests").json()) == 1  # the backtest now exists


def test_seed_demo_populates_all_views(tmp_path):
    client = TestClient(create_app(config=_cfg(tmp_path), runner=lambda t, d: None))
    resp = client.post("/api/seed-demo")
    assert resp.status_code == 200 and resp.json()["runs"] == 2

    assert len(client.get("/api/backtests").json()) >= 1
    assert len(client.get("/api/runs").json()) == 2
    j = client.get("/api/journal").json()
    assert j["summary"]["n_resolved"] == 1
    assert j["summary"]["n_pending"] == 1
