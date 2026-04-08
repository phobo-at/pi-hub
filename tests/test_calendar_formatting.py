from __future__ import annotations

import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from smart_display.providers.caldav_provider import (
    _collect_calendar_items,
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


class _FakeComponent(dict):
    """Minimal stand-in for an icalendar VEVENT component."""

    def __init__(self, *, summary: str, dtstart, dtend=None) -> None:
        super().__init__()
        self["summary"] = summary
        self["dtstart"] = dtstart
        if dtend is not None:
            self["dtend"] = dtend

    def decoded(self, key: str):
        return self[key]


class _FakeIcal:
    def __init__(self, components: list[_FakeComponent]) -> None:
        self._components = components

    def walk(self, name: str) -> list[_FakeComponent]:
        assert name == "VEVENT"
        return self._components


class _FakeEvent:
    def __init__(self, components: list[_FakeComponent]) -> None:
        self.icalendar_instance = _FakeIcal(components)


class _FakeCalendar:
    def __init__(self, name: str, events: list[_FakeEvent]) -> None:
        self.name = name
        self._events = events

    def date_search(self, *, start, end, expand: bool = True):  # noqa: ARG002
        return self._events


class AllDayWindowLeakTest(unittest.TestCase):
    """Plan B11: the previous ``or item.all_day`` short-circuit let every
    all-day event through, even ones outside the visible 3-day window.
    All-day events must still be bounded by the window."""

    def _collect(self, components: list[_FakeComponent]):
        zone = ZoneInfo("Europe/Vienna")
        start = datetime(2026, 4, 8, 0, 0, tzinfo=zone)
        end = datetime(2026, 4, 11, 0, 0, tzinfo=zone)
        return _collect_calendar_items(
            calendars=[_FakeCalendar("cal", [_FakeEvent(components)])],
            start=start,
            end=end,
            timezone_name="Europe/Vienna",
            selected_names=[],
            calendar_parser=None,
        )

    def test_all_day_event_inside_window_included(self) -> None:
        items = self._collect([
            _FakeComponent(summary="Feiertag", dtstart=date(2026, 4, 9)),
        ])
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0].all_day)
        self.assertEqual(items[0].title, "Feiertag")

    def test_all_day_event_outside_window_excluded(self) -> None:
        items = self._collect([
            _FakeComponent(summary="LetzteWoche", dtstart=date(2026, 4, 1)),
            _FakeComponent(summary="NaechsteWoche", dtstart=date(2026, 4, 15)),
            # Sanity: one inside so the path still produces results.
            _FakeComponent(summary="Heute", dtstart=date(2026, 4, 8)),
        ])
        self.assertEqual([item.title for item in items], ["Heute"])

    def test_timed_event_inside_window_included(self) -> None:
        zone = ZoneInfo("Europe/Vienna")
        items = self._collect([
            _FakeComponent(
                summary="Meeting",
                dtstart=datetime(2026, 4, 9, 10, 0, tzinfo=zone),
                dtend=datetime(2026, 4, 9, 11, 0, tzinfo=zone),
            ),
        ])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].time_label, "10:00–11:00")

    def test_timed_event_outside_window_excluded(self) -> None:
        zone = ZoneInfo("Europe/Vienna")
        items = self._collect([
            _FakeComponent(
                summary="NaechsteWoche",
                dtstart=datetime(2026, 4, 15, 10, 0, tzinfo=zone),
                dtend=datetime(2026, 4, 15, 11, 0, tzinfo=zone),
            ),
        ])
        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()
