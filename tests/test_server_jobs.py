"""Background job manager (server/jobs.py) — pure, offline, no FastAPI."""

import threading

from server.jobs import JobManager


def test_successful_job_reaches_done():
    seen = []
    jm = JobManager()
    job_id = jm.submit(lambda: seen.append(1), kind="run", meta={"ticker": "NVDA"})
    result = jm.wait(job_id)
    assert result["status"] == "done"
    assert result["error"] is None
    assert result["kind"] == "run"
    assert result["ticker"] == "NVDA"
    assert seen == [1]


def test_failing_job_captures_error():
    def boom():
        raise RuntimeError("pipeline exploded")

    jm = JobManager()
    result = jm.wait(jm.submit(boom))
    assert result["status"] == "error"
    assert "pipeline exploded" in result["error"]


def test_unknown_job_is_none():
    assert JobManager().get("job-999") is None


def test_ids_unique_and_listed():
    started = threading.Event()
    jm = JobManager()
    a = jm.submit(lambda: started.wait(1.0))
    b = jm.submit(lambda: started.wait(1.0))
    assert a != b
    assert {a, b} <= {j["id"] for j in jm.list()}
    started.set()
    jm.wait(a)
    jm.wait(b)
    assert all(j["status"] == "done" for j in jm.list())
