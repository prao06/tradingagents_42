"""Background job manager for live pipeline runs.

A ``propagate()`` run takes minutes (~12 LLM calls), far longer than any HTTP
request should block — so the API submits it as a background job and the client
polls for status. This module is deliberately free of any web-framework import
so its logic is unit-tested without FastAPI installed.
"""

from __future__ import annotations

import threading
from typing import Callable, Dict, List, Optional


class JobManager:
    """Runs ``runner(ticker, date)`` on a background thread and tracks status.

    Status transitions: ``running`` -> ``done`` | ``error``. The runner's job is
    a side effect (a propagate() run that writes artifacts to disk); its return
    value is ignored. In-memory only — intended for a single backend instance;
    a multi-instance deployment would back this with a shared queue/store.
    """

    def __init__(self, runner: Callable[[str, str], None]):
        self._runner = runner
        self._jobs: Dict[str, dict] = {}
        self._threads: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._counter = 0

    def submit(self, ticker: str, date: str) -> str:
        """Start a run in the background and return its job id."""
        with self._lock:
            self._counter += 1
            job_id = f"job-{self._counter}"
            self._jobs[job_id] = {
                "id": job_id, "ticker": ticker, "date": date,
                "status": "running", "error": None,
            }
        t = threading.Thread(target=self._run, args=(job_id, ticker, date), daemon=True)
        with self._lock:
            self._threads[job_id] = t
        t.start()
        return job_id

    def _run(self, job_id: str, ticker: str, date: str) -> None:
        try:
            self._runner(ticker, date)
            self._update(job_id, status="done")
        except Exception as e:  # capture; surfaced via get()
            self._update(job_id, status="error", error=str(e))

    def _update(self, job_id: str, **fields) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(fields)

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def list(self) -> List[dict]:
        with self._lock:
            return [dict(v) for v in self._jobs.values()]

    def wait(self, job_id: str, timeout: float = 10.0) -> Optional[dict]:
        """Block until the job finishes (or timeout). Mainly for tests/CLI."""
        with self._lock:
            t = self._threads.get(job_id)
        if t is not None:
            t.join(timeout)
        return self.get(job_id)
