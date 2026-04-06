"""APScheduler-backed job registry and scheduler for AI Infra Radar."""
from __future__ import annotations

import threading
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler


class RadarScheduler:
    """Thin wrapper around APScheduler ``BackgroundScheduler``.

    Jobs are registered by name along with an interval trigger. Any registered
    job can also be triggered immediately (in a daemon thread) without waiting
    for the next scheduled run.
    """

    def __init__(self) -> None:
        self._scheduler: BackgroundScheduler = BackgroundScheduler(timezone="UTC")
        self._job_funcs: dict[str, Callable] = {}

    def register(self, name: str, func: Callable, **trigger_kwargs: object) -> None:
        """Register *func* as job *name* and schedule it via APScheduler.

        ``trigger_kwargs`` are forwarded to the ``interval`` trigger
        (e.g. ``hours=1``, ``minutes=30``).
        """
        self._job_funcs[name] = func
        self._scheduler.add_job(
            func, "interval", id=name, replace_existing=True, **trigger_kwargs
        )

    def known_jobs(self) -> list[str]:
        """Return names of all registered jobs."""
        return list(self._job_funcs)

    def trigger(self, job_name: str) -> bool:
        """Run *job_name* immediately in a background daemon thread.

        Returns ``True`` if the job was found and dispatched, ``False``
        if the job name is unknown.
        """
        if job_name not in self._job_funcs:
            return False
        threading.Thread(
            target=self._job_funcs[job_name], daemon=True, name=f"radar-job-{job_name}"
        ).start()
        return True

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
