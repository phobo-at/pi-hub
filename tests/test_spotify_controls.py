from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from smart_display.http_client import HttpError
from smart_display.models import ProviderSnapshot
from smart_display.providers.spotify_provider import (
    SpotifyProvider,
    build_spotify_state_from_payload,
)
from tests._support import FakeHttpClient, make_app_config, make_state_store


PLAYING_PAYLOAD = {
    "is_playing": True,
    "device": {
        "name": "Wohnzimmer",
        "type": "Speaker",
        "is_restricted": False,
        "volume_percent": 42,
        "supports_volume": True,
    },
    "item": {
        "name": "Everything In Its Right Place",
        "artists": [{"name": "Radiohead"}],
        "album": {"name": "Kid A", "images": [{"url": "https://example.com/kida.jpg"}]},
    },
}

PAUSED_PAYLOAD = {
    **PLAYING_PAYLOAD,
    "is_playing": False,
}


def _configured_provider(tmp_dir: Path) -> tuple[SpotifyProvider, FakeHttpClient]:
    config = make_app_config(
        tmp_dir,
        spotify_enabled=True,
        spotify_client_id="id",
        spotify_client_secret="secret",
        spotify_refresh_token="refresh",
    )
    store = make_state_store(
        tmp_dir,
        spotify_enabled=True,
        spotify_client_id="id",
        spotify_client_secret="secret",
        spotify_refresh_token="refresh",
    )
    fake = FakeHttpClient()
    provider = SpotifyProvider(config, store, http_client=fake)
    # Pre-seed the cached access token so tests don't need to mock the
    # OAuth refresh endpoint on every call.
    provider._access_token = "seeded-token"
    provider._token_expiry = datetime.now(timezone.utc) + timedelta(minutes=30)
    return provider, fake


class SpotifyStateTest(unittest.TestCase):
    def test_build_spotify_state_sets_control_flag(self) -> None:
        payload = {
            "is_playing": True,
            "device": {
                "name": "Wohnzimmer",
                "type": "Speaker",
                "is_restricted": False,
                "volume_percent": 37,
                "supports_volume": True,
            },
            "item": {
                "name": "Track",
                "artists": [{"name": "Artist"}],
                "album": {"name": "Album", "images": [{"url": "https://example.com/cover.jpg"}]},
            },
        }

        state = build_spotify_state_from_payload(
            payload,
            ProviderSnapshot(status="ok", updated_at="2026-04-08T09:00:00+00:00"),
        )

        self.assertTrue(state.can_control)
        self.assertTrue(state.is_playing)
        self.assertEqual(state.artist_name, "Artist")
        self.assertEqual(state.device_type, "Speaker")
        self.assertEqual(state.volume_percent, 37)
        self.assertTrue(state.supports_volume)

    def test_restricted_device_disables_controls(self) -> None:
        payload = {
            "is_playing": False,
            "device": {"name": "TV", "type": "TV", "is_restricted": True, "volume_percent": 14},
            "item": {"name": "Track", "artists": [], "album": {"images": []}},
        }
        state = build_spotify_state_from_payload(payload, ProviderSnapshot(status="ok"))
        self.assertFalse(state.can_control)
        self.assertFalse(state.supports_volume)


class SpotifyControlFlowTest(unittest.TestCase):
    """Covers the A1 release-blocker: control commands must reflect fresh
    truth synchronously so the UI doesn't fight a stale poll."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.provider, self.fake = _configured_provider(Path(self._tmp.name))
        # Seed the store with a "playing" state so toggle goes to pause.
        self.provider.state_store.update_section(
            "spotify",
            build_spotify_state_from_payload(
                PLAYING_PAYLOAD, ProviderSnapshot(status="ok")
            ),
        )

    def test_toggle_returns_fresh_state_on_success(self) -> None:
        # Command endpoint → 204, inline refresh → paused payload.
        self.fake.add_response("PUT", "https://api.spotify.com/v1/me/player/pause", status=204)
        self.fake.add_response(
            "GET", "https://api.spotify.com/v1/me/player", status=200, body=PAUSED_PAYLOAD
        )

        result = self.provider.toggle_playback()

        self.assertTrue(result["ok"])
        self.assertIsNotNone(result["state"])
        self.assertFalse(result["state"]["is_playing"])
        self.assertEqual(result["state"]["snapshot"]["status"], "ok")
        # Exactly one command + one refresh call — no extra round-trips.
        self.assertEqual(len(self.fake.calls_matching("PUT", "https://api.spotify.com/v1/me/player/pause")), 1)
        self.assertEqual(len(self.fake.calls_matching("GET", "https://api.spotify.com/v1/me/player")), 1)

    def test_toggle_propagates_error_message_on_401(self) -> None:
        self.fake.add_response(
            "PUT", "https://api.spotify.com/v1/me/player/pause", status=401, body={"error": "expired"}
        )

        result = self.provider.toggle_playback()

        self.assertFalse(result["ok"])
        self.assertIn("Spotify", result["message"])
        self.assertIsNone(result["state"])
        # 401 path must invalidate the cached token so the next call re-auths.
        self.assertIsNone(self.provider._access_token)

    def test_toggle_propagates_error_message_on_network_failure(self) -> None:
        self.fake.add_error(
            "PUT",
            "https://api.spotify.com/v1/me/player/pause",
            HttpError("connection reset"),
        )

        result = self.provider.toggle_playback()

        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "connection reset")
        self.assertIsNone(result["state"])

    def test_toggle_propagates_error_message_on_generic_5xx(self) -> None:
        self.fake.add_response(
            "PUT",
            "https://api.spotify.com/v1/me/player/pause",
            status=502,
            body=b"bad gateway",
        )

        result = self.provider.toggle_playback()

        self.assertFalse(result["ok"])
        self.assertIn("502", result["message"])
        self.assertIsNone(result["state"])

    def test_volume_command_refreshes_inline(self) -> None:
        self.fake.add_response(
            "PUT",
            "https://api.spotify.com/v1/me/player/volume?volume_percent=55",
            status=204,
        )
        updated_payload = {
            **PLAYING_PAYLOAD,
            "device": {**PLAYING_PAYLOAD["device"], "volume_percent": 55},
        }
        self.fake.add_response(
            "GET",
            "https://api.spotify.com/v1/me/player",
            status=200,
            body=updated_payload,
        )

        result = self.provider.set_volume(55)

        self.assertTrue(result["ok"])
        self.assertEqual(result["state"]["volume_percent"], 55)
        # Refresh fired exactly once — the UI does not need to poll again.
        self.assertEqual(
            len(self.fake.calls_matching("GET", "https://api.spotify.com/v1/me/player")), 1
        )

    def test_next_track_returns_fresh_state(self) -> None:
        self.fake.add_response(
            "POST", "https://api.spotify.com/v1/me/player/next", status=204
        )
        self.fake.add_response(
            "GET",
            "https://api.spotify.com/v1/me/player",
            status=200,
            body=PLAYING_PAYLOAD,
        )

        result = self.provider.next_track()

        self.assertTrue(result["ok"])
        self.assertEqual(result["state"]["track_title"], "Everything In Its Right Place")

    def test_not_configured_returns_ok_false_without_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_app_config(Path(tmp))  # spotify disabled
            store = make_state_store(Path(tmp))
            fake = FakeHttpClient()
            provider = SpotifyProvider(config, store, http_client=fake)

            result = provider.toggle_playback()

            self.assertFalse(result["ok"])
            self.assertEqual(result["message"], "Spotify ist nicht konfiguriert.")
            self.assertEqual(fake.calls, [])


if __name__ == "__main__":
    unittest.main()
