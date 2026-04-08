from __future__ import annotations

import unittest

from smart_display.providers.weather_openmeteo import _short_day_label, weather_icon_key


class WeatherIconTest(unittest.TestCase):
    def test_icon_mapping_uses_expected_groups(self) -> None:
        self.assertEqual(weather_icon_key(0), "clear")
        self.assertEqual(weather_icon_key(2), "partly-cloudy")
        self.assertEqual(weather_icon_key(63), "rain")
        self.assertEqual(weather_icon_key(73), "snow")
        self.assertEqual(weather_icon_key(95), "storm")
        self.assertEqual(weather_icon_key(45), "fog")

    def test_short_day_label_uses_compact_german_weekday(self) -> None:
        self.assertEqual(_short_day_label(0, "2026-04-08"), "Heute")
        self.assertEqual(_short_day_label(1, "2026-04-09"), "Morgen")
        self.assertEqual(_short_day_label(2, "2026-04-10"), "Fr.")


if __name__ == "__main__":
    unittest.main()
