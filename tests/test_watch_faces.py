from __future__ import annotations

import unittest

from smart_display.watch_faces import (
    DEFAULT_WATCH_FACE,
    QLOCKTWO_COLS,
    QLOCKTWO_GRID,
    QLOCKTWO_OOE_COLS,
    QLOCKTWO_OOE_GRID,
    QLOCKTWO_OOE_ROWS,
    QLOCKTWO_ROWS,
    VALID_WATCH_FACES,
    analog_hand_angles,
    normalize_watch_face,
    qlocktwo_active_cells,
    qlocktwo_ooe_active_cells,
    qlocktwo_ooe_phrase,
    qlocktwo_phrase,
)


class NormalizeWatchFaceTest(unittest.TestCase):
    def test_accepts_known_values(self) -> None:
        self.assertEqual(normalize_watch_face("flip"), "flip")
        self.assertEqual(normalize_watch_face("lcd"), "lcd")
        self.assertEqual(normalize_watch_face("pulse"), "pulse")
        self.assertEqual(normalize_watch_face("qlocktwo"), "qlocktwo")
        self.assertEqual(normalize_watch_face("qlocktwo-ooe"), "qlocktwo-ooe")
        self.assertEqual(normalize_watch_face("analog"), "analog")

    def test_falls_back_for_unknown_or_missing(self) -> None:
        self.assertEqual(normalize_watch_face(None), DEFAULT_WATCH_FACE)
        self.assertEqual(normalize_watch_face(""), DEFAULT_WATCH_FACE)
        # Legacy face name from before the 2026-04 refresh maps to default.
        self.assertEqual(normalize_watch_face("classic"), DEFAULT_WATCH_FACE)
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


class QlocktwoOoeGridShapeTest(unittest.TestCase):
    def test_grid_is_rectangular(self) -> None:
        self.assertEqual(QLOCKTWO_OOE_ROWS, 10)
        self.assertEqual(QLOCKTWO_OOE_COLS, 11)
        for row in QLOCKTWO_OOE_GRID:
            self.assertEqual(len(row), QLOCKTWO_OOE_COLS)

    def test_grid_uses_real_umlauts(self) -> None:
        joined = "".join(QLOCKTWO_OOE_GRID)
        self.assertIn("Ü", joined)
        self.assertIn("Ö", joined)


class QlocktwoOoeActiveCellsTest(unittest.TestCase):
    """Dialect phrases. Matches the 'Standard Viertel nach' scheme:
    13:15 → VIERTL NOCH OANS, 13:45 → VIERTL VOR ZWA. UHR is dropped."""

    def test_full_hour_reads_es_is_hour(self) -> None:
        self.assertEqual(qlocktwo_ooe_phrase(12, 0), "ES IS ZWÖFE")
        self.assertEqual(qlocktwo_ooe_phrase(1, 0), "ES IS OANS")
        self.assertEqual(qlocktwo_ooe_phrase(7, 0), "ES IS SIEBNE")
        self.assertEqual(qlocktwo_ooe_phrase(4, 0), "ES IS VIERE")
        self.assertEqual(qlocktwo_ooe_phrase(9, 0), "ES IS NEINE")
        self.assertEqual(qlocktwo_ooe_phrase(11, 0), "ES IS ELF")

    def test_five_minute_phrases_around_one(self) -> None:
        self.assertEqual(qlocktwo_ooe_phrase(13, 5), "ES IS FÜMF NOCH OANS")
        self.assertEqual(qlocktwo_ooe_phrase(13, 10), "ES IS ZEHN NOCH OANS")
        self.assertEqual(qlocktwo_ooe_phrase(13, 15), "ES IS VIERTL NOCH OANS")
        self.assertEqual(qlocktwo_ooe_phrase(13, 20), "ES IS ZWANZG NOCH OANS")
        self.assertEqual(qlocktwo_ooe_phrase(13, 25), "ES IS FÜMF VOR HOIBE ZWOA")
        self.assertEqual(qlocktwo_ooe_phrase(13, 30), "ES IS HOIBE ZWOA")
        self.assertEqual(qlocktwo_ooe_phrase(13, 35), "ES IS FÜMF NOCH HOIBE ZWOA")
        self.assertEqual(qlocktwo_ooe_phrase(13, 40), "ES IS ZWANZG VOR ZWOA")
        self.assertEqual(qlocktwo_ooe_phrase(13, 45), "ES IS VIERTL VOR ZWOA")
        self.assertEqual(qlocktwo_ooe_phrase(13, 50), "ES IS ZEHN VOR ZWOA")
        self.assertEqual(qlocktwo_ooe_phrase(13, 55), "ES IS FÜMF VOR ZWOA")

    def test_drei_hour_does_not_collide_with_viertl(self) -> None:
        # Regression: DREI used to live on row 2 next to VIERTL, which at
        # 3:15 produced the misleading "DREIVIERTL" run on one line. DREI
        # now lives on row 7, safely after NOCH/VOR in reading order.
        self.assertEqual(qlocktwo_ooe_phrase(3, 15), "ES IS VIERTL NOCH DREI")
        self.assertEqual(qlocktwo_ooe_phrase(3, 45), "ES IS VIERTL VOR VIERE")
        self.assertNotIn("DREIVIERTL", qlocktwo_ooe_phrase(3, 15))

    def test_midnight_folds_to_zwoefe(self) -> None:
        self.assertEqual(qlocktwo_ooe_phrase(0, 0), "ES IS ZWÖFE")

    def test_half_past_rolls_hour_forward(self) -> None:
        # 12:30 → "halb eins" → HOIBE OANS
        self.assertEqual(qlocktwo_ooe_phrase(12, 30), "ES IS HOIBE OANS")
        # 7:30 → HOIBE OCHT
        self.assertEqual(qlocktwo_ooe_phrase(7, 30), "ES IS HOIBE OCHT")

    def test_minute_blocks_round_down_to_five(self) -> None:
        self.assertEqual(qlocktwo_ooe_phrase(7, 32), "ES IS HOIBE OCHT")
        self.assertEqual(qlocktwo_ooe_phrase(7, 34), "ES IS HOIBE OCHT")

    def test_no_uhr_at_full_hour(self) -> None:
        # Regression guard: UHR is deliberately absent from the OÖ grid.
        self.assertNotIn("UHR", qlocktwo_ooe_phrase(12, 0))
        self.assertNotIn("UHR", qlocktwo_ooe_phrase(1, 0))

    def test_all_twelve_hours_have_unique_coords(self) -> None:
        # Sanity: every hour from 1..12 maps to a distinct set of cells so the
        # grid cannot accidentally light the wrong hour word.
        signatures: set[tuple[tuple[int, int], ...]] = set()
        for hour in range(1, 13):
            cells = qlocktwo_ooe_active_cells(hour, 0)
            # Drop ES / IS — they are constant across hours.
            trimmed = tuple(
                sorted((r, c) for r, c in cells if (r, c) not in {
                    (0, 0), (0, 1), (0, 3), (0, 4),
                })
            )
            signatures.add(trimmed)
        self.assertEqual(len(signatures), 12)

    def test_cells_are_unique_and_in_range(self) -> None:
        for hour in range(24):
            for minute in (0, 5, 15, 25, 30, 45, 55):
                cells = qlocktwo_ooe_active_cells(hour, minute)
                seen: set[tuple[int, int]] = set()
                for row, col in cells:
                    self.assertTrue(0 <= row < QLOCKTWO_OOE_ROWS)
                    self.assertTrue(0 <= col < QLOCKTWO_OOE_COLS)
                    seen.add((row, col))
                self.assertEqual(len(seen), len(cells))


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
