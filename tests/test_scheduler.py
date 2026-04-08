from __future__ import annotations

import threading
import time
import unittest

from smart_display.scheduler import ScheduledJob, Scheduler


class ComputeWaitTest(unittest.TestCase):
    """Plan B2: wait-duration helpers are pure and deterministic so we can
    assert startup stagger and jitter clamps without spinning threads."""

    def test_initial_wait_equals_startup_delay_when_no_jitter(self) -> None:
        scheduler = Scheduler(rng=lambda a, b: 0.0)
        job = ScheduledJob(
            name="weather",
            interval_seconds=900,
            task=lambda: None,
            startup_delay_seconds=4.0,
            jitter_seconds=0.0,
        )
        self.assertEqual(scheduler.compute_initial_wait(job), 4.0)

    def test_initial_wait_adds_positive_jitter(self) -> None:
        # rng returns the upper bound, so we expect startup + jitter.
        scheduler = Scheduler(rng=lambda a, b: b)
        job = ScheduledJob(
            name="calendar",
            interval_seconds=300,
            task=lambda: None,
            startup_delay_seconds=2.0,
            jitter_seconds=1.5,
        )
        self.assertEqual(scheduler.compute_initial_wait(job), 3.5)

    def test_next_wait_applies_symmetric_jitter(self) -> None:
        # rng returns the lower bound → interval - jitter.
        scheduler = Scheduler(rng=lambda a, b: a)
        job = ScheduledJob(
            name="spotify",
            interval_seconds=30,
            task=lambda: None,
            jitter_seconds=5.0,
        )
        self.assertEqual(scheduler.compute_next_wait(job), 25.0)

    def test_next_wait_clamps_to_one_second(self) -> None:
        # Even if jitter would push us below 1s we never wait less.
        scheduler = Scheduler(rng=lambda a, b: a)
        job = ScheduledJob(
            name="fast",
            interval_seconds=2,
            task=lambda: None,
            jitter_seconds=5.0,
        )
        self.assertEqual(scheduler.compute_next_wait(job), 1.0)

    def test_startup_delays_are_staggered_across_jobs(self) -> None:
        """With rng=0 the initial wait equals the declared startup delay."""
        scheduler = Scheduler(rng=lambda a, b: 0.0)
        jobs = [
            ScheduledJob("weather", 900, lambda: None, startup_delay_seconds=0.0, jitter_seconds=1.0),
            ScheduledJob("calendar", 300, lambda: None, startup_delay_seconds=2.0, jitter_seconds=1.0),
            ScheduledJob("spotify", 30, lambda: None, startup_delay_seconds=4.0, jitter_seconds=1.0),
            ScheduledJob("screensaver", 1800, lambda: None, startup_delay_seconds=6.0, jitter_seconds=1.0),
        ]
        waits = [scheduler.compute_initial_wait(job) for job in jobs]
        self.assertEqual(waits, [0.0, 2.0, 4.0, 6.0])


class PauseAndTriggerTest(unittest.TestCase):
    """Plan B2/B1: verify the pause group and trigger wiring against a real
    thread with a short interval. These are still fast (<200 ms each)."""

    def _make_counter_job(
        self,
        *,
        name: str,
        interval: float,
        pause_group: str | None = None,
    ):
        state = {"count": 0, "event": threading.Event()}

        def task() -> None:
            state["count"] += 1
            state["event"].set()

        job = ScheduledJob(
            name=name,
            interval_seconds=interval,
            task=task,
            startup_delay_seconds=0.0,
            jitter_seconds=0.0,
            pause_group=pause_group,
        )
        return job, state

    def test_paused_group_skips_task_but_reschedules(self) -> None:
        scheduler = Scheduler()
        job, state = self._make_counter_job(name="spotify", interval=0.05, pause_group="spotify")
        scheduler.set_paused("spotify", True)
        scheduler.start([job])
        try:
            # Let several ticks fire; none should execute the task.
            time.sleep(0.25)
            self.assertEqual(state["count"], 0)
            self.assertTrue(scheduler.is_paused("spotify"))
        finally:
            scheduler.stop()

    def test_resume_triggers_immediate_tick(self) -> None:
        scheduler = Scheduler()
        job, state = self._make_counter_job(
            name="spotify",
            interval=10.0,  # long interval — without trigger we'd never tick
            pause_group="spotify",
        )
        scheduler.set_paused("spotify", True)
        scheduler.start([job])
        try:
            time.sleep(0.05)
            # Still paused; the first tick fires but is skipped.
            self.assertEqual(state["count"], 0)
            scheduler.set_paused("spotify", False)
            self.assertTrue(state["event"].wait(timeout=1.0))
            self.assertGreaterEqual(state["count"], 1)
        finally:
            scheduler.stop()

    def test_trigger_wakes_named_job(self) -> None:
        scheduler = Scheduler()
        job, state = self._make_counter_job(name="weather", interval=10.0)
        scheduler.start([job])
        try:
            # First tick runs immediately (startup_delay=0).
            self.assertTrue(state["event"].wait(timeout=1.0))
            state["event"].clear()
            scheduler.trigger("weather")
            self.assertTrue(state["event"].wait(timeout=1.0))
            self.assertGreaterEqual(state["count"], 2)
        finally:
            scheduler.stop()

    def test_failing_task_does_not_kill_loop(self) -> None:
        scheduler = Scheduler()
        state = {"count": 0, "event": threading.Event()}

        def task() -> None:
            state["count"] += 1
            if state["count"] == 1:
                raise RuntimeError("boom")
            state["event"].set()

        # Long native interval — we rely on ``trigger`` to pump the second
        # tick so the test stays deterministic even under load.
        job = ScheduledJob(
            name="flaky",
            interval_seconds=10.0,
            task=task,
            startup_delay_seconds=0.0,
            jitter_seconds=0.0,
        )
        scheduler.start([job])
        try:
            # Wait for the first (failing) tick to land.
            deadline = time.monotonic() + 2.0
            while state["count"] < 1 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertGreaterEqual(state["count"], 1)
            scheduler.trigger("flaky")
            self.assertTrue(state["event"].wait(timeout=2.0))
            self.assertGreaterEqual(state["count"], 2)
        finally:
            scheduler.stop()


if __name__ == "__main__":
    unittest.main()
