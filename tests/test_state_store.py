from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from smart_display.config import load_config_from_mapping
from smart_display.models import (
    CalendarDaySection,
    CalendarEventItem,
    CalendarState,
    DASHBOARD_SCHEMA_VERSION,
    DashboardState,
    IncompatibleSchemaError,
    ProviderSnapshot,
    SpotifyState,
    SystemState,
    WeatherForecastItem,
    WeatherState,
)
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


def _realistic_dashboard_state() -> DashboardState:
    """Build a fully populated DashboardState so the round-trip test
    exercises every nested dataclass (weather forecast, calendar sections,
    spotify track, system metadata). Mirrors the shape a live Pi would
    serialise to ``last_good.json`` after an hour of uptime."""
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    return DashboardState(
        weather=WeatherState(
            snapshot=ProviderSnapshot(
                status="ok",
                updated_at="2026-04-08T09:00:00+00:00",
                source="open-meteo",
                error_message=None,
                stale_after_seconds=900,
            ),
            location_label="Zuhause",
            temperature_c=18.5,
            apparent_temperature_c=17.2,
            condition="Teilweise bewölkt",
            condition_code=2,
            forecast=[
                WeatherForecastItem(
                    day_label="Heute",
                    condition="Wolkig",
                    condition_code=2,
                    temperature_max_c=21.0,
                    temperature_min_c=11.3,
                ),
                WeatherForecastItem(
                    day_label="Morgen",
                    condition="Bedeckt",
                    condition_code=3,
                    temperature_max_c=19.5,
                    temperature_min_c=9.0,
                ),
            ],
        ),
        calendar=CalendarState(
            snapshot=ProviderSnapshot(status="ok", source="caldav"),
            items=[],
            sections=[
                CalendarDaySection(
                    day_key=today,
                    section_date=today,
                    items=[
                        CalendarEventItem(
                            title="Teamstandup",
                            starts_at=f"{today}T09:30:00+02:00",
                            ends_at=f"{today}T10:00:00+02:00",
                            time_label="09:30–10:00",
                            all_day=False,
                        )
                    ],
                ),
                CalendarDaySection(
                    day_key=tomorrow,
                    section_date=tomorrow,
                    items=[
                        CalendarEventItem(
                            title="Zahnarzt",
                            starts_at=f"{tomorrow}T14:15:00+02:00",
                            ends_at=f"{tomorrow}T15:00:00+02:00",
                            time_label="14:15–15:00",
                            all_day=False,
                        )
                    ],
                ),
            ],
        ),
        spotify=SpotifyState(
            snapshot=ProviderSnapshot(status="ok", source="spotify"),
            connected=True,
            is_playing=True,
            track_title="Weiß nicht",
            artist_name="Irgendwer",
            album_name="Album",
            album_art_url="https://example.com/cover.jpg",
            device_name="Wohnzimmer",
            device_type="Speaker",
            volume_percent=42,
            supports_volume=True,
            can_control=True,
            empty_message="",
        ),
        system=SystemState(
            generated_at="2026-04-08T09:00:05+00:00",
            locale="de-AT",
            timezone="Europe/Vienna",
            idle_timeout_seconds=120,
            screensaver_interval_seconds=15,
            screensaver_photo_count=12,
        ),
    )


class DashboardRoundTripTest(unittest.TestCase):
    """Any shape change that breaks round-trip is a migration blocker. The
    test serialises a fully-populated state, deserialises it, and asserts
    the JSON bytes are identical. A failure here means a future upgrade
    would either crash on load or lose data silently."""

    def test_round_trip_preserves_every_field(self) -> None:
        state = _realistic_dashboard_state()
        serialised = state.to_dict()
        # JSON round-trip via the same path StateStore uses.
        json_bytes = json.dumps(serialised, sort_keys=True).encode("utf-8")
        reloaded_payload = json.loads(json_bytes.decode("utf-8"))

        reloaded = DashboardState.from_dict(reloaded_payload)
        re_serialised = reloaded.to_dict()

        self.assertEqual(
            json.dumps(serialised, sort_keys=True),
            json.dumps(re_serialised, sort_keys=True),
        )
        # schema_version must be embedded so a future bump can detect drift.
        self.assertEqual(serialised["schema_version"], DASHBOARD_SCHEMA_VERSION)

    def test_missing_schema_version_still_loads(self) -> None:
        # Pre-versioning payloads (before V1 ships) must still deserialise
        # so the very first upgrade doesn't quarantine a valid cache.
        state = _realistic_dashboard_state()
        payload = state.to_dict()
        payload.pop("schema_version")
        reloaded = DashboardState.from_dict(payload)
        self.assertEqual(
            reloaded.weather.temperature_c, state.weather.temperature_c
        )

    def test_future_schema_version_raises(self) -> None:
        payload = _realistic_dashboard_state().to_dict()
        payload["schema_version"] = DASHBOARD_SCHEMA_VERSION + 99
        with self.assertRaises(IncompatibleSchemaError):
            DashboardState.from_dict(payload)


class SchemaMismatchQuarantineTest(unittest.TestCase):
    """If ``last_good.json`` was written by an incompatible version, the
    StateStore must quarantine it and boot from an empty state instead of
    crashing. Mirrors DiskCache's corrupt-JSON quarantine pattern."""

    def _make_config(self, temp_dir: str):
        return load_config_from_mapping(
            {
                "app": {
                    "data_dir": temp_dir,
                    "locale": "de-AT",
                    "timezone": "Europe/Vienna",
                },
                "screensaver": {
                    "idle_timeout_seconds": 120,
                    "image_duration_seconds": 15,
                },
            },
            root_dir=Path(temp_dir),
        )

    def test_incompatible_cache_is_quarantined_and_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._make_config(temp_dir)
            # Write a future-schema payload directly to the last_good path.
            stale_payload = _realistic_dashboard_state().to_dict()
            stale_payload["schema_version"] = DASHBOARD_SCHEMA_VERSION + 99
            config.last_good_path.parent.mkdir(parents=True, exist_ok=True)
            config.last_good_path.write_text(
                json.dumps(stale_payload), encoding="utf-8"
            )

            store = StateStore(config)

            # Fresh empty state — no fields carried over from the stale cache.
            current = store.get_state()
            self.assertEqual(current.weather.snapshot.status, "empty")
            self.assertIsNone(current.weather.temperature_c)

            # Original file renamed aside, new one re-created by the fresh boot.
            siblings = list(config.last_good_path.parent.iterdir())
            corrupt = [
                p for p in siblings if ".corrupt-" in p.name
            ]
            self.assertEqual(len(corrupt), 1)

    def test_malformed_payload_is_also_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._make_config(temp_dir)
            config.last_good_path.parent.mkdir(parents=True, exist_ok=True)
            # Missing required nested shape entirely.
            config.last_good_path.write_text(
                json.dumps({"weather": "not a dict"}), encoding="utf-8"
            )

            store = StateStore(config)
            self.assertEqual(store.get_state().weather.snapshot.status, "empty")
            corrupt = [
                p
                for p in config.last_good_path.parent.iterdir()
                if ".corrupt-" in p.name
            ]
            self.assertEqual(len(corrupt), 1)


if __name__ == "__main__":
    unittest.main()

