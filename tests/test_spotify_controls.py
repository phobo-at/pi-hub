from __future__ import annotations

import unittest

from smart_display.models import ProviderSnapshot
from smart_display.providers.spotify_provider import build_spotify_state_from_payload


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



if __name__ == "__main__":
    unittest.main()
