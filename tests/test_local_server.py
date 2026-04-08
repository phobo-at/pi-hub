from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from smart_display.config import load_config
from smart_display.local_server import _load_local_env


class LocalServerTest(unittest.TestCase):
    def test_local_demo_profile_uses_isolated_demo_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            (root / "config" / "default.yaml").write_text(
                """
{
  "app": {"host": "127.0.0.1", "port": 8080, "locale": "de-AT", "timezone": "Europe/Vienna", "data_dir": "./data", "log_level": "INFO", "demo_mode": false},
  "weather": {"enabled": true, "provider": "openmeteo", "label": "Zuhause", "latitude": 47.0, "longitude": 15.0, "api_key": null, "timeout_seconds": 10},
  "calendar": {"enabled": true, "url": "https://calendar", "username": "u", "password": "p", "calendar_names": [], "timeout_seconds": 10},
  "spotify": {"enabled": true, "client_id": "id", "client_secret": "secret", "refresh_token": "refresh", "device_id": "", "market": "AT", "timeout_seconds": 10},
  "screensaver": {"enabled": true, "idle_timeout_seconds": 120, "image_duration_seconds": 15, "refresh_interval_seconds": 1800, "source_url": "https://gallery", "cache_dir": "screensaver", "demo_images_enabled": true, "timeout_seconds": 15},
  "refresh_intervals": {"weather_seconds": 900, "calendar_seconds": 300, "spotify_seconds": 10, "lightroom_seconds": 1800}
}
                """.strip(),
                encoding="utf-8",
            )
            (root / "config" / "local-demo.yaml").write_text(
                """
{
  "app": {"port": 8090, "data_dir": "./data/local-demo", "demo_mode": true},
  "weather": {"enabled": false},
  "calendar": {"enabled": false},
  "spotify": {"enabled": false}
}
                """.strip(),
                encoding="utf-8",
            )

            config = load_config(
                config_path=root / "config" / "local-demo.yaml",
                env={},
                dotenv_path=None,
                root_dir=root,
            )

            self.assertEqual(config.app.port, 8090)
            self.assertTrue(config.app.demo_mode)
            self.assertFalse(config.weather.enabled)
            self.assertFalse(config.calendar.enabled)
            self.assertFalse(config.spotify.enabled)
            self.assertEqual(config.app.data_dir, (root / "data" / "local-demo").resolve())

    def test_env_local_overrides_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".env").write_text("APP_PORT=8090\nAPP_HOST=127.0.0.1\n", encoding="utf-8")
            (root / ".env.local").write_text("APP_PORT=8091\n", encoding="utf-8")

            env = _load_local_env(root)

            self.assertEqual(env["APP_PORT"], "8091")
            self.assertEqual(env["APP_HOST"], "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
