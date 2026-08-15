"""Background job manager (server/jobs.py) — pure, offline, no FastAPI."""

import threading

from server.jobs import JobManager


def test_successful_job_reaches_done():
    seen = []
    jm = JobManager(lambda t, d: seen.append((t, d)))
    job_id = jm.submit("NVDA", "2024-05-10")
    result = jm.wait(job_id)
    assert result["status"] == "done"
    assert result["error"] is None
    assert seen == [("NVDA", "2024-05-10")]


def test_failing_job_captures_error():
    def boom(ticker, date):
        raise RuntimeError("pipeline exploded")

    jm = JobManager(boom)
    job_id = jm.submit("AAPL", "2024-05-10")
    result = jm.wait(job_id)
    assert result["status"] == "error"
    assert "pipeline exploded" in result["error"]


def test_unknown_job_is_none():
    jm = JobManager(lambda t, d: None)
    assert jm.get("job-999") is None


def test_ids_unique_and_listed():
    started = threading.Event()

    def slow(ticker, date):
        started.wait(1.0)

    jm = JobManager(slow)
    a = jm.submit("NVDA", "2024-01-01")
    b = jm.submit("AAPL", "2024-01-01")
    assert a != b
    ids = {j["id"] for j in jm.list()}
    assert {a, b} <= ids
    started.set()
    jm.wait(a); jm.wait(b)
    assert all(j["status"] == "done" for j in jm.list())
