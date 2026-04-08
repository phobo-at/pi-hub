from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from smart_display.config import load_config


class ConfigTest(unittest.TestCase):
    def test_yaml_and_env_merge(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            (root / "config" / "default.yaml").write_text(
                """
{
  "app": {"host": "127.0.0.1", "port": 8080, "locale": "de-AT", "timezone": "Europe/Vienna", "data_dir": "./data", "log_level": "INFO", "demo_mode": false},
  "weather": {"enabled": true, "provider": "openmeteo", "label": "Zuhause", "latitude": 47.0, "longitude": 15.0, "api_key": null, "timeout_seconds": 10},
  "calendar": {"enabled": false, "url": "", "username": "", "password": "", "calendar_names": [], "timeout_seconds": 10},
  "spotify": {"enabled": false, "client_id": "", "client_secret": "", "refresh_token": "", "device_id": "", "market": "AT", "timeout_seconds": 10},
  "screensaver": {"enabled": true, "idle_timeout_seconds": 120, "image_duration_seconds": 15, "refresh_interval_seconds": 1800, "source_url": "", "cache_dir": "screensaver", "demo_images_enabled": true, "timeout_seconds": 15},
  "refresh_intervals": {"weather_seconds": 900, "calendar_seconds": 300, "spotify_seconds": 10, "lightroom_seconds": 1800}
}
                """.strip(),
                encoding="utf-8",
            )
            (root / ".env").write_text(
                "APP_TIMEZONE=Europe/Berlin\nCALENDAR_NAME=Family,Work\n",
                encoding="utf-8",
            )

            config = load_config(
                env={"APP_DATA_DIR": "./runtime", "WEATHER_LATITUDE": "48.2"},
                root_dir=root,
            )

            self.assertEqual(config.app.timezone, "Europe/Berlin")
            self.assertEqual(config.calendar.calendar_names, ["Family", "Work"])
            self.assertAlmostEqual(config.weather.latitude, 48.2)
            self.assertEqual(config.app.data_dir, (root / "runtime").resolve())


if __name__ == "__main__":
    unittest.main()

