from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from smart_display.config import load_config_from_mapping
from smart_display.models import ProviderSnapshot, WeatherState
from smart_display.state_store import StateStore


class StateStoreTest(unittest.TestCase):
    def test_error_keeps_last_known_good_weather(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config_from_mapping(
                {
                    "app": {"data_dir": temp_dir, "locale": "de-AT", "timezone": "Europe/Vienna"},
                    "screensaver": {"idle_timeout_seconds": 120, "image_duration_seconds": 15},
                },
                root_dir=Path(temp_dir),
            )
            store = StateStore(config)
            store.update_section(
                "weather",
                WeatherState(
                    snapshot=ProviderSnapshot(status="ok", updated_at="2026-04-08T09:00:00+00:00"),
                    location_label="Zuhause",
                    temperature_c=20.0,
                    condition="Klar",
                ),
            )
            store.mark_error(
                "weather",
                error_message="timeout",
                stale_after_seconds=600,
                source="open-meteo",
            )

            current = store.get_state().weather
            self.assertEqual(current.snapshot.status, "stale")
            self.assertEqual(current.temperature_c, 20.0)
            self.assertEqual(current.snapshot.error_message, "timeout")


if __name__ == "__main__":
    unittest.main()

