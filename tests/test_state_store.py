from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from smart_display.config import load_config_from_mapping
from smart_display.models import ProviderSnapshot, WeatherState
from smart_display.state_store import StateStore


def _make_store(temp_dir: str) -> StateStore:
    config = load_config_from_mapping(
        {
            "app": {"data_dir": temp_dir, "locale": "de-AT", "timezone": "Europe/Vienna"},
            "screensaver": {"idle_timeout_seconds": 120, "image_duration_seconds": 15},
        },
        root_dir=Path(temp_dir),
    )
    return StateStore(config)


class StateStoreTest(unittest.TestCase):
    def test_error_keeps_last_known_good_weather(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = _make_store(temp_dir)
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


class MarkErrorStatusMachineTest(unittest.TestCase):
    """Plan B4: mark_error must respect the ``empty`` status so a not-yet-
    configured provider does not flip the UI to "Fehler" the moment it is
    first polled. The ok → stale → error escalation is preserved."""

    def test_mark_error_keeps_empty_status_when_no_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = _make_store(temp_dir)
            # Fresh store — weather has never received an ok snapshot.
            self.assertEqual(store.get_state().weather.snapshot.status, "empty")

            store.mark_error(
                "weather",
                error_message="temporarily unreachable",
                stale_after_seconds=600,
                source="open-meteo",
            )

            snapshot = store.get_state().weather.snapshot
            self.assertEqual(snapshot.status, "empty")
            self.assertEqual(snapshot.error_message, "temporarily unreachable")
            self.assertEqual(snapshot.source, "open-meteo")

    def test_mark_error_escalates_stale_to_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = _make_store(temp_dir)
            store.update_section(
                "weather",
                WeatherState(
                    snapshot=ProviderSnapshot(status="ok"),
                    location_label="Zuhause",
                    temperature_c=18.0,
                    condition="Wolkig",
                ),
            )
            store.mark_error(
                "weather", error_message="t1", stale_after_seconds=600, source="open-meteo"
            )
            self.assertEqual(store.get_state().weather.snapshot.status, "stale")

            store.mark_error(
                "weather", error_message="t2", stale_after_seconds=600, source="open-meteo"
            )
            self.assertEqual(store.get_state().weather.snapshot.status, "error")
            self.assertEqual(store.get_state().weather.snapshot.error_message, "t2")


if __name__ == "__main__":
    unittest.main()

