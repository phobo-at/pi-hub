from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flask import Flask

from smart_display.scheduler import DEFAULT_PAUSE_TTL_SECONDS
from smart_display.web.routes import create_blueprint
from tests._support import make_app_config, make_state_store


class _StubScheduler:
    def __init__(self) -> None:
        # (group, paused, ttl_seconds) — ttl_seconds is ``None`` when the
        # route did not pass the kwarg, matching the real signature.
        self.calls: list[tuple[str, bool, float | None]] = []

    def set_paused(
        self,
        group: str,
        paused: bool,
        *,
        ttl_seconds: float | None = None,
    ) -> None:
        self.calls.append((group, paused, ttl_seconds))


class ScreensaverStateRouteTest(unittest.TestCase):
    """Plan B1: the frontend POSTs screensaver active/inactive so the
    scheduler can pause the Spotify polling group while the panel is idle.
    Saves one upstream hit every 30 s whenever the user is away."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)

        self.config = make_app_config(tmp)
        self.state_store = make_state_store(tmp)
        self.scheduler = _StubScheduler()

        app = Flask(
            __name__,
            template_folder=str(
                Path(__file__).parent.parent
                / "smart_display"
                / "web"
                / "templates"
            ),
        )
        app.extensions["smart_display"] = {
            "config": self.config,
            "state_store": self.state_store,
            "scheduler": self.scheduler,
        }
        app.register_blueprint(create_blueprint())
        self.app = app
        self.client = app.test_client()

    def test_activating_screensaver_pauses_spotify_with_ttl(self) -> None:
        # The route must attach the watchdog TTL so a crashed frontend
        # cannot strand Spotify polling forever — see scheduler.py.
        response = self.client.post(
            "/api/screensaver/state", json={"active": True}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, "active": True})
        self.assertEqual(
            self.scheduler.calls,
            [("spotify", True, DEFAULT_PAUSE_TTL_SECONDS)],
        )

    def test_deactivating_screensaver_resumes_spotify(self) -> None:
        self.client.post("/api/screensaver/state", json={"active": True})
        self.client.post("/api/screensaver/state", json={"active": False})
        self.assertEqual(
            self.scheduler.calls,
            [
                ("spotify", True, DEFAULT_PAUSE_TTL_SECONDS),
                ("spotify", False, None),
            ],
        )

    def test_missing_body_defaults_to_inactive(self) -> None:
        response = self.client.post("/api/screensaver/state")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, "active": False})
        self.assertEqual(self.scheduler.calls, [("spotify", False, None)])

    def test_missing_scheduler_is_tolerated(self) -> None:
        # Dev/test builds may run without a scheduler — the endpoint must
        # still return 200 instead of AttributeError'ing.
        self.app.extensions["smart_display"].pop("scheduler")
        response = self.client.post(
            "/api/screensaver/state", json={"active": True}
        )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
