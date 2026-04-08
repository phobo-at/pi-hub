from __future__ import annotations

import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from smart_display.providers.caldav_provider import (
    build_calendar_item,
    build_calendar_sections,
    calendar_window,
    today_window,
)


class CalendarFormattingTest(unittest.TestCase):
    def test_all_day_event_renders_ganztagig(self) -> None:
        item = build_calendar_item("Feiertag", date(2026, 4, 8), None, "Europe/Vienna")
        self.assertTrue(item.all_day)
        self.assertEqual(item.time_label, "Ganztägig")

    def test_timed_event_renders_window(self) -> None:
        item = build_calendar_item(
            "Meeting",
            datetime(2026, 4, 8, 9, 30, tzinfo=ZoneInfo("Europe/Vienna")),
            datetime(2026, 4, 8, 10, 15, tzinfo=ZoneInfo("Europe/Vienna")),
            "Europe/Vienna",
        )
        self.assertEqual(item.time_label, "09:30–10:15")

    def test_today_window_uses_local_midnight(self) -> None:
        start, end = today_window(
            "Europe/Vienna",
            now=datetime(2026, 4, 8, 23, 50, tzinfo=ZoneInfo("UTC")),
        )
        self.assertEqual(start.hour, 0)
        self.assertEqual((end - start).days, 1)

    def test_calendar_window_supports_three_day_range(self) -> None:
        start, end = calendar_window(
            "Europe/Vienna",
            days=3,
            now=datetime(2026, 4, 8, 23, 50, tzinfo=ZoneInfo("UTC")),
        )
        self.assertEqual(start.hour, 0)
        self.assertEqual((end - start).days, 3)

    def test_build_calendar_sections_groups_next_three_days(self) -> None:
        items = [
            build_calendar_item(
                "Heute",
                datetime(2026, 4, 8, 9, 0, tzinfo=ZoneInfo("Europe/Vienna")),
                datetime(2026, 4, 8, 9, 30, tzinfo=ZoneInfo("Europe/Vienna")),
                "Europe/Vienna",
            ),
            build_calendar_item(
                "Morgen",
                datetime(2026, 4, 9, 10, 0, tzinfo=ZoneInfo("Europe/Vienna")),
                datetime(2026, 4, 9, 11, 0, tzinfo=ZoneInfo("Europe/Vienna")),
                "Europe/Vienna",
            ),
            build_calendar_item(
                "Übermorgen",
                date(2026, 4, 10),
                None,
                "Europe/Vienna",
            ),
        ]

        sections = build_calendar_sections(
            items,
            timezone_name="Europe/Vienna",
            base_date=date(2026, 4, 8),
            days=3,
        )

        self.assertEqual(
            [section.section_date for section in sections],
            ["2026-04-08", "2026-04-09", "2026-04-10"],
        )
        self.assertEqual([section.day_key for section in sections], ["today", "tomorrow", "day_after_tomorrow"])
        self.assertEqual([section.items[0].title for section in sections], ["Heute", "Morgen", "Übermorgen"])


if __name__ == "__main__":
    unittest.main()
