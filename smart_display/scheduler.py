from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable


logger = logging.getLogger(__name__)


@dataclass
class ScheduledJob:
    name: str
    interval_seconds: int
    task: Callable[[], None]
    run_immediately: bool = True


class Scheduler:
    def __init__(self):
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self, jobs: list[ScheduledJob]) -> None:
        for job in jobs:
            thread = threading.Thread(
                target=self._run_job,
                args=(job,),
                name=f"job-{job.name}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        self._stop_event.set()
        for thread in self._threads:
            thread.join(timeout=1)

    def _run_job(self, job: ScheduledJob) -> None:
        if job.run_immediately:
            self._execute(job)
        while not self._stop_event.wait(job.interval_seconds):
            self._execute(job)

    def _execute(self, job: ScheduledJob) -> None:
        try:
            job.task()
        except Exception:  # pragma: no cover
            logger.exception("scheduled job failed: %s", job.name)

