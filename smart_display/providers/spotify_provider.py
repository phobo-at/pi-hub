from __future__ import annotations

import base64
import json
import threading
import urllib.parse
from datetime import datetime, timedelta, timezone
from urllib import error as urllib_error
from urllib import request as urllib_request

from smart_display.config import AppConfig
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


class SpotifyProvider(BaseProvider):
    section_name = "spotify"
    source_name = "spotify"

    def __init__(self, config: AppConfig, state_store: StateStore):
        super().__init__(config.refresh_intervals.spotify_seconds)
        self.config = config
        self.state_store = state_store
        self._token_lock = threading.Lock()
        self._access_token: str | None = None
        self._token_expiry = datetime.now(timezone.utc)

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
            payload, status_code = self._api_request("GET", "/me/player")
        except Exception as exc:
            self.logger.exception("spotify refresh failed")
            self.state_store.mark_error(
                self.section_name,
                error_message=str(exc),
                stale_after_seconds=self.refresh_interval_seconds * 2,
                source=self.source_name,
            )
            return

        if status_code in {204, 202, 404} or not payload:
            self.state_store.update_section(
                self.section_name,
                SpotifyState(
                    snapshot=self.snapshot(status="empty"),
                    connected=True,
                    empty_message="Keine aktive Wiedergabe.",
                ),
            )
            return

        self.state_store.update_section(
            self.section_name,
            build_spotify_state_from_payload(payload, self.snapshot(status="ok")),
        )

    def toggle_playback(self) -> dict[str, object]:
        state = self.state_store.get_state().spotify
        endpoint = "/me/player/pause" if state.is_playing else "/me/player/play"
        return self._send_command("PUT", endpoint)

    def next_track(self) -> dict[str, object]:
        return self._send_command("POST", "/me/player/next")

    def previous_track(self) -> dict[str, object]:
        return self._send_command("POST", "/me/player/previous")

    def set_volume(self, volume_percent: int) -> dict[str, object]:
        value = max(0, min(int(volume_percent), 100))
        return self._send_command(
            "PUT",
            f"/me/player/volume?{urllib.parse.urlencode({'volume_percent': value})}",
        )

    def _send_command(self, method: str, path: str) -> dict[str, object]:
        if not self._is_configured():
            return {"ok": False, "message": "Spotify ist nicht konfiguriert."}

        try:
            _, status_code = self._api_request(method, path, expect_json=False)
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

        if status_code not in {200, 202, 204}:
            return {"ok": False, "message": f"Spotify antwortete mit {status_code}."}

        return {"ok": True, "message": "ok"}

    def _is_configured(self) -> bool:
        return self.config.spotify.enabled and all(
            [
                self.config.spotify.client_id,
                self.config.spotify.client_secret,
                self.config.spotify.refresh_token,
            ]
        )

    def _api_request(
        self,
        method: str,
        path: str,
        *,
        expect_json: bool = True,
    ) -> tuple[dict | None, int]:
        token = self._access_token_value()
        url = f"https://api.spotify.com/v1{path}"
        if self.config.spotify.device_id and method in {"PUT", "POST"}:
            query = urllib.parse.urlencode({"device_id": self.config.spotify.device_id})
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{query}"

        request = urllib_request.Request(
            url,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "pi-hub-smart-display/0.1",
                "Content-Type": "application/json",
            },
            data=b"" if method in {"POST", "PUT"} else None,
        )
        try:
            with urllib_request.urlopen(
                request, timeout=self.config.spotify.timeout_seconds
            ) as response:
                status_code = response.getcode()
                body = response.read().decode("utf-8") if expect_json else ""
                return (json.loads(body) if body else None, status_code)
        except urllib_error.HTTPError as exc:
            if exc.code == 204:
                return None, 204
            if exc.code in {401, 404}:
                body = exc.read().decode("utf-8")
                if exc.code == 401:
                    with self._token_lock:
                        self._access_token = None
                    raise RuntimeError("Spotify-Authentifizierung fehlgeschlagen.") from exc
                raise RuntimeError(body or "Kein aktives Spotify-Gerät.") from exc
            raise RuntimeError(exc.read().decode("utf-8") or str(exc)) from exc

    def _access_token_value(self) -> str:
        with self._token_lock:
            if self._access_token and datetime.now(timezone.utc) < self._token_expiry:
                return self._access_token

            credentials = f"{self.config.spotify.client_id}:{self.config.spotify.client_secret}"
            encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
            body = urllib.parse.urlencode(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": self.config.spotify.refresh_token,
                }
            ).encode("utf-8")
            request = urllib_request.Request(
                "https://accounts.spotify.com/api/token",
                method="POST",
                data=body,
                headers={
                    "Authorization": f"Basic {encoded}",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "pi-hub-smart-display/0.1",
                },
            )
            try:
                with urllib_request.urlopen(
                    request, timeout=self.config.spotify.timeout_seconds
                ) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except urllib_error.HTTPError as exc:
                raise RuntimeError(
                    exc.read().decode("utf-8") or "Spotify token refresh fehlgeschlagen."
                ) from exc

            self._access_token = str(payload["access_token"])
            expires_in = int(payload.get("expires_in", 3600))
            self._token_expiry = datetime.now(timezone.utc) + timedelta(
                seconds=max(expires_in - 60, 60)
            )
            return self._access_token
