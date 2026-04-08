from __future__ import annotations

import threading
from dataclasses import replace
from typing import Any

from smart_display.cache.disk_cache import DiskCache
from smart_display.config import AppConfig
from smart_display.models import (
    CalendarState,
    DashboardState,
    ProviderSnapshot,
    SpotifyState,
    SystemState,
    WeatherState,
    utcnow_iso,
)


class StateStore:
    def __init__(self, config: AppConfig):
        self.config = config
        self._lock = threading.Lock()
        self._cache = DiskCache(config.last_good_path)
        self._state = self._load_initial_state()
        self._provider_health: dict[str, ProviderSnapshot] = {
            "weather": self._state.weather.snapshot,
            "calendar": self._state.calendar.snapshot,
            "spotify": self._state.spotify.snapshot,
            "screensaver": ProviderSnapshot(status="empty", source="screensaver"),
        }

    def get_state(self) -> DashboardState:
        with self._lock:
            return DashboardState.from_dict(self._state.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return self.get_state().to_dict()

    def update_section(
        self, section_name: str, section: WeatherState | CalendarState | SpotifyState
    ) -> None:
        with self._lock:
            setattr(self._state, section_name, section)
            self._state.system.generated_at = utcnow_iso()
            self._provider_health[section_name] = replace(section.snapshot)
            self._persist_locked()

    def mark_error(
        self,
        section_name: str,
        *,
        error_message: str,
        stale_after_seconds: int,
        source: str,
    ) -> None:
        """Record a provider fetch failure.

        Status transitions (Plan B4):
          ``ok``    → ``stale`` (first failure after known-good data)
          ``stale`` → ``error``
          ``error`` → ``error``
          ``empty`` → ``empty`` (no prior data — the UI keeps showing "Leer"
                       rather than flipping to "Fehler" the moment a not-yet-
                       configured provider is first polled)

        In every case the error message and source are refreshed so ops and
        the /health endpoint can see the latest attempt.
        """
        with self._lock:
            section = getattr(self._state, section_name)
            previous_status = section.snapshot.status
            if previous_status == "empty":
                next_status = "empty"
            elif previous_status == "ok":
                next_status = "stale"
            else:
                next_status = "error"
            section.snapshot.status = next_status
            section.snapshot.error_message = error_message
            section.snapshot.stale_after_seconds = stale_after_seconds
            section.snapshot.source = source
            self._state.system.generated_at = utcnow_iso()
            self._provider_health[section_name] = replace(section.snapshot)
            self._persist_locked()

    def set_provider_snapshot(self, name: str, snapshot: ProviderSnapshot) -> None:
        with self._lock:
            self._provider_health[name] = replace(snapshot)
            self._state.system.generated_at = utcnow_iso()
            self._persist_locked()

    def set_screensaver_photo_count(self, count: int) -> None:
        with self._lock:
            self._state.system.screensaver_photo_count = max(count, 0)
            self._state.system.generated_at = utcnow_iso()
            self._persist_locked()

    def health_payload(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": "ok",
                "generated_at": self._state.system.generated_at,
                "providers": {
                    name: snapshot.to_dict()
                    for name, snapshot in self._provider_health.items()
                },
            }

    def _persist_locked(self) -> None:
        self._cache.save(self._state.to_dict())

    def _load_initial_state(self) -> DashboardState:
        payload = self._cache.load()
        if payload:
            state = DashboardState.from_dict(payload)
            state.system.locale = self.config.app.locale
            state.system.timezone = self.config.app.timezone
            state.system.idle_timeout_seconds = (
                self.config.screensaver.idle_timeout_seconds
            )
            state.system.screensaver_interval_seconds = (
                self.config.screensaver.image_duration_seconds
            )
            return state

        system = SystemState(
            locale=self.config.app.locale,
            timezone=self.config.app.timezone,
            idle_timeout_seconds=self.config.screensaver.idle_timeout_seconds,
            screensaver_interval_seconds=self.config.screensaver.image_duration_seconds,
        )
        return DashboardState(
            weather=WeatherState(
                snapshot=ProviderSnapshot(status="empty", source="weather")
            ),
            calendar=CalendarState(
                snapshot=ProviderSnapshot(status="empty", source="calendar")
            ),
            spotify=SpotifyState(
                snapshot=ProviderSnapshot(status="empty", source="spotify")
            ),
            system=system,
        )

