from __future__ import annotations

import unittest

from smart_display.calendar_layout import (
    GERMAN_WEEKDAYS_LONG,
    apply_day_labels,
    compute_day_label,
)
from smart_display.models import CalendarDaySection, CalendarEventItem


def _section(section_date: str, *titles: str) -> CalendarDaySection:
    items = [
        CalendarEventItem(
            title=title,
            starts_at=f"{section_date}T09:00:00+02:00",
            ends_at=f"{section_date}T10:00:00+02:00",
            time_label="09:00–10:00",
        )
        for title in titles
    ]
    return CalendarDaySection(day_key="generic", section_date=section_date, items=items)


class ComputeDayLabelTest(unittest.TestCase):
    def test_today(self) -> None:
        self.assertEqual(compute_day_label("2026-04-08", "2026-04-08"), "Heute")

    def test_tomorrow(self) -> None:
        self.assertEqual(compute_day_label("2026-04-09", "2026-04-08"), "Morgen")

    def test_day_after_tomorrow(self) -> None:
        self.assertEqual(compute_day_label("2026-04-10", "2026-04-08"), "Übermorgen")

    def test_further_future_uses_weekday(self) -> None:
        # 2026-04-13 is a Monday
        self.assertEqual(compute_day_label("2026-04-13", "2026-04-08"), "Montag")

    def test_past_date_uses_weekday_for_stale_offline_state(self) -> None:
        # 2026-04-07 is a Tuesday — stale data kept after a power-cycle should
        # not suddenly become "Heute" because the client clock moved on.
        self.assertEqual(compute_day_label("2026-04-07", "2026-04-08"), "Dienstag")

    def test_invalid_iso_returns_empty_string(self) -> None:
        self.assertEqual(compute_day_label("nonsense", "2026-04-08"), "")
        self.assertEqual(compute_day_label("2026-04-08", ""), "")

    def test_weekday_list_is_complete(self) -> None:
        self.assertEqual(len(GERMAN_WEEKDAYS_LONG), 7)
        self.assertEqual(GERMAN_WEEKDAYS_LONG[0], "Montag")
        self.assertEqual(GERMAN_WEEKDAYS_LONG[6], "Sonntag")


class ApplyDayLabelsAcrossMidnightTest(unittest.TestCase):
    def test_labels_shift_when_today_rolls_over(self) -> None:
        # Backend-emitted sections for the next three days, stable ISO dates.
        sections = [
            _section("2026-04-08", "Standup"),
            _section("2026-04-09", "Abgabe"),
            _section("2026-04-10", "Lieferung"),
        ]

        before = [label for _section_ignored, label in apply_day_labels(sections, "2026-04-08")]
        self.assertEqual(before, ["Heute", "Morgen", "Übermorgen"])

        # Simulate the client waking past midnight without a fresh /api/state poll.
        after = [label for _section_ignored, label in apply_day_labels(sections, "2026-04-09")]
        self.assertEqual(after, ["Mittwoch", "Heute", "Morgen"])

    def test_offline_stale_events_keep_weekday_label(self) -> None:
        # App has been offline for two days; the cached sections are stale but
        # should still render with weekday names rather than ever being
        # mislabeled as "Heute".
        sections = [
            _section("2026-04-08", "Staler Eintrag"),
        ]
        labels = [label for _section_ignored, label in apply_day_labels(sections, "2026-04-10")]
        self.assertEqual(labels, ["Mittwoch"])


if __name__ == "__main__":
    unittest.main()
