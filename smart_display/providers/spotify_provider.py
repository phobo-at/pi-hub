from __future__ import annotations

import base64
import threading
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any

from smart_display.config import AppConfig
from smart_display.http_client import HttpClient, HttpError, HttpResponse
from smart_display.models import ProviderSnapshot, SpotifyState
from smart_display.providers.base import BaseProvider
from smart_display.state_store import StateStore


def build_spotify_state_from_payload(
    payload: dict,
    snapshot: ProviderSnapshot,
) -> SpotifyState:
    device = payload.get("device") or {}
    item = payload.get("item") or {}
    artists = item.get("artists") or []
    album = item.get("album") or {}
    images = album.get("images") or []
    album_art_url = images[1]["url"] if len(images) > 1 else images[0]["url"] if images else None
    can_control = bool(device) and not bool(device.get("is_restricted", False))
    supports_volume = bool(device) and not bool(device.get("is_restricted", False))
    if device.get("supports_volume") is not None:
        supports_volume = bool(device.get("supports_volume"))

    return SpotifyState(
        snapshot=snapshot,
        connected=True,
        is_playing=bool(payload.get("is_playing", False)),
        track_title=str(item.get("name", "")),
        artist_name=", ".join(str(artist.get("name", "")) for artist in artists if artist.get("name")),
        album_name=str(album.get("name", "")),
        album_art_url=album_art_url,
        device_name=device.get("name"),
        device_type=device.get("type"),
        volume_percent=device.get("volume_percent"),
        supports_volume=supports_volume,
        can_control=can_control,
        empty_message="Derzeit keine Wiedergabe.",
    )


# Plan C3: Spotify API failures get a short German message so the frontend
# toast surface (Plan A4) can show something honest instead of "Spotify
# antwortete mit 429". Anything we don't recognise falls back to a generic
# "not reachable" string.
_SPOTIFY_STATUS_MESSAGES: dict[int, str] = {
    401: "Spotify-Anmeldung abgelaufen.",
    403: "Spotify-Aktion nicht erlaubt.",
    404: "Kein aktives Spotify-Gerät.",
    429: "Spotify-Limit erreicht. Kurz warten.",
    500: "Spotify nicht erreichbar.",
    502: "Spotify nicht erreichbar.",
    503: "Spotify nicht erreichbar.",
    504: "Spotify nicht erreichbar.",
}
_SPOTIFY_DEFAULT_ERROR = "Spotify nicht erreichbar."


def spotify_status_message(status: int) -> str:
    """Return the German-localised error message for a Spotify HTTP status."""
    return _SPOTIFY_STATUS_MESSAGES.get(status, _SPOTIFY_DEFAULT_ERROR)


class SpotifyProvider(BaseProvider):
    section_name = "spotify"
    source_name = "spotify"

    def __init__(
        self,
        config: AppConfig,
        state_store: StateStore,
        http_client: HttpClient | None = None,
    ):
        super().__init__(config.refresh_intervals.spotify_seconds)
        self.config = config
        self.state_store = state_store
        self._http = http_client or HttpClient()
        self._token_lock = threading.Lock()
        self._access_token: str | None = None
        self._token_expiry = datetime.now(timezone.utc)

    # ---- scheduler entrypoint --------------------------------------------

    def refresh(self) -> None:
        if self.config.app.demo_mode and not self.config.spotify.enabled:
            return

        if not self._is_configured():
            self.state_store.update_section(
                self.section_name,
                SpotifyState(
                    snapshot=self.snapshot(status="empty"),
                    empty_message="Spotify nicht verbunden.",
                ),
            )
            return

        try:
            response = self._api_request("GET", "/me/player")
        except Exception as exc:
            self.logger.exception("spotify refresh failed")
            self.state_store.mark_error(
                self.section_name,
                error_message=str(exc),
                stale_after_seconds=self.refresh_interval_seconds * 2,
                source=self.source_name,
            )
            return

        if response.status in {202, 204, 404} or not response.body:
            self.state_store.update_section(
                self.section_name,
                SpotifyState(
                    snapshot=self.snapshot(status="empty"),
                    connected=True,
                    empty_message="Keine aktive Wiedergabe.",
                ),
            )
            return

        if response.status == 401:
            with self._token_lock:
                self._access_token = None
            self.state_store.mark_error(
                self.section_name,
                error_message="Spotify-Authentifizierung fehlgeschlagen.",
                stale_after_seconds=self.refresh_interval_seconds * 2,
                source=self.source_name,
            )
            return

        if response.status >= 400:
            self.state_store.mark_error(
                self.section_name,
                error_message=f"Spotify antwortete mit {response.status}.",
                stale_after_seconds=self.refresh_interval_seconds * 2,
                source=self.source_name,
            )
            return

        try:
            payload = response.json()
        except Exception as exc:
            self.logger.exception("spotify payload parse failed")
            self.state_store.mark_error(
                self.section_name,
                error_message=str(exc),
                stale_after_seconds=self.refresh_interval_seconds * 2,
                source=self.source_name,
            )
            return

        self.state_store.update_section(
            self.section_name,
            build_spotify_state_from_payload(payload, self.snapshot(status="ok")),
        )

    # ---- control commands -------------------------------------------------

    def toggle_playback(self) -> dict[str, Any]:
        state = self.state_store.get_state().spotify
        endpoint = "/me/player/pause" if state.is_playing else "/me/player/play"
        return self._send_command("PUT", endpoint)

    def next_track(self) -> dict[str, Any]:
        return self._send_command("POST", "/me/player/next")

    def previous_track(self) -> dict[str, Any]:
        return self._send_command("POST", "/me/player/previous")

    def set_volume(self, volume_percent: int) -> dict[str, Any]:
        value = max(0, min(int(volume_percent), 100))
        return self._send_command(
            "PUT",
            f"/me/player/volume?{urllib.parse.urlencode({'volume_percent': value})}",
        )

    def _send_command(self, method: str, path: str) -> dict[str, Any]:
        if not self._is_configured():
            return {
                "ok": False,
                "message": "Spotify ist nicht konfiguriert.",
                "state": None,
            }

        try:
            response = self._api_request(method, path)
        except HttpError:
            return {"ok": False, "message": _SPOTIFY_DEFAULT_ERROR, "state": None}
        except Exception:  # noqa: BLE001 — token refresh errors bubble here
            return {"ok": False, "message": _SPOTIFY_DEFAULT_ERROR, "state": None}

        if response.status == 401:
            with self._token_lock:
                self._access_token = None
            return {
                "ok": False,
                "message": spotify_status_message(401),
                "state": None,
            }

        if response.status not in {200, 202, 204}:
            return {
                "ok": False,
                "message": spotify_status_message(response.status),
                "state": None,
            }

        # Command worked — pull fresh truth inline so the UI never waits on
        # the next poll tick to reflect play/pause/volume changes.
        try:
            self.refresh()
        except Exception as exc:  # noqa: BLE001 — never let inline refresh break the command
            self.logger.warning("spotify inline refresh failed: %s", exc)

        return {
            "ok": True,
            "message": "ok",
            "state": self.state_store.get_state().spotify.to_dict(),
        }

    # ---- HTTP / auth internals -------------------------------------------

    def _is_configured(self) -> bool:
        return self.config.spotify.enabled and all(
            [
                self.config.spotify.client_id,
                self.config.spotify.client_secret,
                self.config.spotify.refresh_token,
            ]
        )

    def _api_request(self, method: str, path: str) -> HttpResponse:
        token = self._access_token_value()
        url = f"https://api.spotify.com/v1{path}"
        if self.config.spotify.device_id and method in {"PUT", "POST"}:
            query = urllib.parse.urlencode(
                {"device_id": self.config.spotify.device_id}
            )
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{query}"

        body = b"" if method in {"POST", "PUT"} else None
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        return self._http.request(
            method,
            url,
            body=body,
            headers=headers,
            timeout=self.config.spotify.timeout_seconds,
        )

    def _access_token_value(self) -> str:
        with self._token_lock:
            if self._access_token and datetime.now(timezone.utc) < self._token_expiry:
                return self._access_token

            credentials = (
                f"{self.config.spotify.client_id}:{self.config.spotify.client_secret}"
            )
            encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
            response = self._http.post_form(
                "https://accounts.spotify.com/api/token",
                {
                    "grant_type": "refresh_token",
                    "refresh_token": self.config.spotify.refresh_token,
                },
                headers={"Authorization": f"Basic {encoded}"},
                timeout=self.config.spotify.timeout_seconds,
            )
            if not response.ok:
                raise RuntimeError(
                    response.text() or "Spotify token refresh fehlgeschlagen."
                )
            payload = response.json()
            self._access_token = str(payload["access_token"])
            expires_in = int(payload.get("expires_in", 3600))
            self._token_expiry = datetime.now(timezone.utc) + timedelta(
                seconds=max(expires_in - 60, 60)
            )
            return self._access_token
