from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from dataclasses import replace
from typing import Any

from smart_display.cache.disk_cache import DiskCache
from smart_display.config import AppConfig
from smart_display.models import (
    CalendarState,
    DashboardState,
    IncompatibleSchemaError,
    ProviderSnapshot,
    SpotifyState,
    SystemState,
    WeatherState,
    utcnow_iso,
)


logger = logging.getLogger(__name__)


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
        self._serialized_state = b""
        self._state_etag = ""
        self._refresh_serialized_locked()
        self._persisted_spotify_key = self._spotify_persistence_key(
            self._state.spotify
        )

    def get_state(self) -> DashboardState:
        with self._lock:
            return DashboardState.from_dict(self._state.to_dict())

    def to_dict(self) -> dict[str, Any]:
        # ``DashboardState.to_dict`` already returns a detached tree of plain
        # dicts/lists. Re-hydrating a second DashboardState only to serialise it
        # again made every local /api/state poll do the same deep conversion
        # twice.
        with self._lock:
            return self._state.to_dict()

    def to_dict_with_etag(self) -> tuple[dict[str, Any], str]:
        """Return an atomic SSR snapshot and the matching API entity tag."""
        with self._lock:
            return self._state.to_dict(), self._state_etag

    def api_payload(self) -> tuple[bytes, str]:
        """Return immutable, pre-encoded state for the hot local poll route."""
        with self._lock:
            return self._serialized_state, self._state_etag

    def update_section(
        self, section_name: str, section: WeatherState | CalendarState | SpotifyState
    ) -> None:
        with self._lock:
            persist = True
            if section_name == "spotify" and isinstance(section, SpotifyState):
                # progress_ms and the provider timestamp move on every Spotify
                # tick, but neither makes the cold-boot fallback more useful.
                # Keep publishing those values to /api/state while sparing the
                # SD card an atomic rewrite every 10 seconds. Track, playback,
                # volume, device, status and error changes still persist now.
                persist = (
                    self._spotify_persistence_key(section)
                    != self._persisted_spotify_key
                )
            setattr(self._state, section_name, section)
            self._state.system.generated_at = utcnow_iso()
            self._provider_health[section_name] = replace(section.snapshot)
            self._publish_locked(persist=persist)

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
        self._publish_locked(persist=True)

    def _publish_locked(self, *, persist: bool) -> None:
        self._refresh_serialized_locked()
        if not persist:
            return
        self._cache.save_serialized(self._serialized_state)
        self._persisted_spotify_key = self._spotify_persistence_key(
            self._state.spotify
        )

    def _refresh_serialized_locked(self) -> None:
        # /api/state is polled much more often than providers update. Encode on
        # mutation, then serve the same immutable bytes until the next update.
        # The digest is content-based rather than a process-local counter so a
        # kiosk browser surviving a backend restart can never receive a false
        # 304 because both processes happened to use the same revision number.
        self._serialized_state = DiskCache.serialize(self._state.to_dict())
        self._state_etag = hashlib.blake2s(
            self._serialized_state,
            digest_size=12,
        ).hexdigest()

    @staticmethod
    def _spotify_persistence_key(spotify: SpotifyState) -> bytes:
        payload = spotify.to_dict()
        payload.pop("progress_ms", None)
        snapshot = payload.get("snapshot")
        if isinstance(snapshot, dict):
            snapshot.pop("updated_at", None)
        return DiskCache.serialize(payload)

    def _quarantine_cache(self) -> None:
        """Rename the on-disk cache aside so a bad payload can't poison
        the next boot. Mirrors ``DiskCache`` corruption handling so ops can
        always find the old file with a ``*.corrupt-*`` suffix."""
        path = self._cache.path
        try:
            if path.exists():
                target = path.with_name(
                    f"{path.name}.corrupt-{int(time.time())}"
                )
                os.replace(path, target)
                logger.warning("moved stale cache to %s", target)
        except OSError as exc:  # pragma: no cover — best effort
            logger.warning("could not quarantine %s: %s", path, exc)

    def _load_initial_state(self) -> DashboardState:
        payload = self._cache.load()
        if payload:
            try:
                state = DashboardState.from_dict(payload)
            except IncompatibleSchemaError as exc:
                # Same quarantine pattern as DiskCache (Plan S2): log once,
                # rename the file aside, fall through to an empty boot.
                logger.warning(
                    "quarantining last_good.json due to schema mismatch: %s", exc
                )
                self._quarantine_cache()
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                # ``from_dict`` duck-types its input — if the payload is a
                # list or a dict-of-string-at-expected-nested-dict, the
                # deserialiser raises AttributeError. Widen the catch so
                # any malformed cache lands in quarantine instead of
                # crashing the app at boot.
                logger.warning(
                    "quarantining last_good.json due to malformed payload: %s", exc
                )
                self._quarantine_cache()
            else:
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
