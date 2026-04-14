from __future__ import annotations

import unittest

from smart_display.watch_faces import (
    DEFAULT_WATCH_FACE,
    QLOCKTWO_COLS,
    QLOCKTWO_GRID,
    QLOCKTWO_ROWS,
    VALID_WATCH_FACES,
    analog_hand_angles,
    normalize_watch_face,
    qlocktwo_active_cells,
    qlocktwo_phrase,
)


class NormalizeWatchFaceTest(unittest.TestCase):
    def test_accepts_known_values(self) -> None:
        self.assertEqual(normalize_watch_face("classic"), "classic")
        self.assertEqual(normalize_watch_face("qlocktwo"), "qlocktwo")
        self.assertEqual(normalize_watch_face("analog"), "analog")

    def test_falls_back_for_unknown_or_missing(self) -> None:
        self.assertEqual(normalize_watch_face(None), DEFAULT_WATCH_FACE)
        self.assertEqual(normalize_watch_face(""), DEFAULT_WATCH_FACE)
        self.assertEqual(normalize_watch_face("retro-flip"), DEFAULT_WATCH_FACE)

    def test_default_face_is_registered(self) -> None:
        self.assertIn(DEFAULT_WATCH_FACE, VALID_WATCH_FACES)


class QlocktwoGridShapeTest(unittest.TestCase):
    def test_grid_is_rectangular(self) -> None:
        self.assertEqual(QLOCKTWO_ROWS, 10)
        self.assertEqual(QLOCKTWO_COLS, 11)
        for row in QLOCKTWO_GRID:
            self.assertEqual(len(row), QLOCKTWO_COLS)

    def test_grid_uses_real_umlauts(self) -> None:
        # Regression guard: the project requires real umlauts in German UI.
        joined = "".join(QLOCKTWO_GRID)
        self.assertIn("Ü", joined)
        self.assertIn("Ö", joined)


class QlocktwoActiveCellsTest(unittest.TestCase):
    """The phrase helper is the human-readable projection of the active
    cells — if the phrases come out right, the coordinates are right."""

    def test_full_hour_reads_es_ist_hour_uhr(self) -> None:
        self.assertEqual(qlocktwo_phrase(12, 0), "ES IST ZWÖLF UHR")
        self.assertEqual(qlocktwo_phrase(7, 0), "ES IST SIEBEN UHR")
        self.assertEqual(qlocktwo_phrase(1, 0), "ES IST EIN UHR")

    def test_hour_one_uses_eins_outside_of_uhr(self) -> None:
        # Only "1:00" drops the S ("ein Uhr"). Every other phrase referring to
        # the one o'clock hour must say "eins".
        self.assertEqual(qlocktwo_phrase(12, 45), "ES IST VIERTEL VOR EINS")
        self.assertEqual(qlocktwo_phrase(12, 30), "ES IST HALB EINS")
        self.assertEqual(qlocktwo_phrase(1, 15), "ES IST VIERTEL NACH EINS")
        self.assertEqual(qlocktwo_phrase(1, 30), "ES IST HALB ZWEI")

    def test_midnight_is_zwoelf(self) -> None:
        # 24h zero hour must fold to 12 for the word clock.
        self.assertEqual(qlocktwo_phrase(0, 0), "ES IST ZWÖLF UHR")

    def test_afternoon_folds_to_12h(self) -> None:
        # 13:30 is "halb zwei", not "halb vierzehn".
        self.assertEqual(qlocktwo_phrase(13, 30), "ES IST HALB ZWEI")

    def test_minute_blocks_round_down_to_five(self) -> None:
        # 07:32 and 07:34 both read as 07:30.
        self.assertEqual(qlocktwo_phrase(7, 32), "ES IST HALB ACHT")
        self.assertEqual(qlocktwo_phrase(7, 34), "ES IST HALB ACHT")

    def test_five_minute_phrases_around_seven(self) -> None:
        self.assertEqual(qlocktwo_phrase(7, 5), "ES IST FÜNF NACH SIEBEN")
        self.assertEqual(qlocktwo_phrase(7, 10), "ES IST ZEHN NACH SIEBEN")
        self.assertEqual(qlocktwo_phrase(7, 15), "ES IST VIERTEL NACH SIEBEN")
        self.assertEqual(qlocktwo_phrase(7, 20), "ES IST ZWANZIG NACH SIEBEN")
        self.assertEqual(qlocktwo_phrase(7, 25), "ES IST FÜNF VOR HALB ACHT")
        self.assertEqual(qlocktwo_phrase(7, 30), "ES IST HALB ACHT")
        self.assertEqual(qlocktwo_phrase(7, 35), "ES IST FÜNF NACH HALB ACHT")
        self.assertEqual(qlocktwo_phrase(7, 40), "ES IST ZWANZIG VOR ACHT")
        self.assertEqual(qlocktwo_phrase(7, 45), "ES IST VIERTEL VOR ACHT")
        self.assertEqual(qlocktwo_phrase(7, 50), "ES IST ZEHN VOR ACHT")
        self.assertEqual(qlocktwo_phrase(7, 55), "ES IST FÜNF VOR ACHT")

    def test_cells_are_unique_and_in_range(self) -> None:
        for hour in range(24):
            for minute in (0, 5, 15, 25, 30, 45, 55):
                cells = qlocktwo_active_cells(hour, minute)
                seen: set[tuple[int, int]] = set()
                for row, col in cells:
                    self.assertTrue(0 <= row < QLOCKTWO_ROWS)
                    self.assertTrue(0 <= col < QLOCKTWO_COLS)
                    seen.add((row, col))
                # No duplicates even when ZWEI/EIN share letters.
                self.assertEqual(len(seen), len(cells))

    def test_returns_json_friendly_lists(self) -> None:
        cells = qlocktwo_active_cells(12, 0)
        self.assertTrue(cells)
        for entry in cells:
            self.assertIsInstance(entry, list)
            self.assertEqual(len(entry), 2)
            self.assertIsInstance(entry[0], int)
            self.assertIsInstance(entry[1], int)


class AnalogHandAnglesTest(unittest.TestCase):
    def test_twelve_oclock_points_up(self) -> None:
        angles = analog_hand_angles(12, 0)
        self.assertAlmostEqual(angles["hour"], 0.0)
        self.assertAlmostEqual(angles["minute"], 0.0)
        self.assertAlmostEqual(angles["second"], 0.0)
        # Midnight (24h hour = 0) must also fold to the top.
        angles = analog_hand_angles(0, 0)
        self.assertAlmostEqual(angles["hour"], 0.0)

    def test_second_hand_advances_six_degrees_per_second(self) -> None:
        self.assertAlmostEqual(analog_hand_angles(12, 0, 0)["second"], 0.0)
        self.assertAlmostEqual(analog_hand_angles(12, 0, 15)["second"], 90.0)
        self.assertAlmostEqual(analog_hand_angles(12, 0, 30)["second"], 180.0)
        self.assertAlmostEqual(analog_hand_angles(12, 0, 59)["second"], 354.0)
        # Default second=0 keeps back-compat for callers that don't track it.
        self.assertAlmostEqual(analog_hand_angles(12, 0)["second"], 0.0)

    def test_three_oclock_points_right(self) -> None:
        angles = analog_hand_angles(3, 0)
        self.assertAlmostEqual(angles["hour"], 90.0)
        self.assertAlmostEqual(angles["minute"], 0.0)

    def test_six_thirty_hour_hand_between_six_and_seven(self) -> None:
        # 6:30 → hour hand at 6*30 + 30*0.5 = 195°. Minute hand at 180°.
        angles = analog_hand_angles(6, 30)
        self.assertAlmostEqual(angles["hour"], 195.0)
        self.assertAlmostEqual(angles["minute"], 180.0)

    def test_afternoon_folds_to_12h(self) -> None:
        # 15:00 should behave like 3:00 on the dial.
        afternoon = analog_hand_angles(15, 0)
        morning = analog_hand_angles(3, 0)
        self.assertAlmostEqual(afternoon["hour"], morning["hour"])
        self.assertAlmostEqual(afternoon["minute"], morning["minute"])

    def test_angles_are_bounded(self) -> None:
        for hour in range(24):
            for minute in range(60):
                angles = analog_hand_angles(hour, minute)
                self.assertGreaterEqual(angles["hour"], 0.0)
                self.assertLess(angles["hour"], 360.0)
                self.assertGreaterEqual(angles["minute"], 0.0)
                self.assertLess(angles["minute"], 360.0)


if __name__ == "__main__":
    unittest.main()
