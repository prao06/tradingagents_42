"""Background job manager for long-running work (runs, backtests).

A live ``propagate()`` run or a Gate A backtest takes far longer than an HTTP
request should block, so the API submits them as background jobs and the client
polls for status. Task-agnostic: ``submit`` takes any zero-arg callable plus a
``kind`` label and ``meta`` for display. Framework-free so it's unit-tested
without FastAPI.
"""

from __future__ import annotations

import threading
from typing import Callable, Dict, List, Optional


class JobManager:
    """Runs a callable on a background thread and tracks its status.

    Status transitions: ``running`` -> ``done`` | ``error``. The task's return
    value is ignored (it works by side effect — writing artifacts to disk); any
    exception is captured and surfaced via :meth:`get`. In-memory only, so this
    suits a single backend instance; a multi-instance deployment would back it
    with a shared queue/store.
    """

    def __init__(self):
        self._jobs: Dict[str, dict] = {}
        self._threads: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._counter = 0

    def submit(self, task: Callable[[], None], *, kind: str = "job", meta: dict = None) -> str:
        with self._lock:
            self._counter += 1
            job_id = f"job-{self._counter}"
            self._jobs[job_id] = {
                "id": job_id, "kind": kind, "status": "running",
                "error": None, **(meta or {}),
            }
            t = threading.Thread(target=self._run, args=(job_id, task), daemon=True)
            self._threads[job_id] = t
        t.start()
        return job_id

    def _run(self, job_id: str, task: Callable[[], None]) -> None:
        try:
            task()
            self._update(job_id, status="done")
        except Exception as e:  # captured; surfaced via get()
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
