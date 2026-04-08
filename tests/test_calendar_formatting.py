from __future__ import annotations

import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from smart_display.providers import caldav_provider
from smart_display.providers.caldav_provider import (
    _collect_calendar_items,
    build_calendar_item,
    build_calendar_sections,
    calendar_window,
    normalize_calendar_name,
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
    def __init__(
        self,
        name: str,
        events: list[_FakeEvent],
        *,
        url: str | None = None,
    ) -> None:
        self.name = name
        self.url = url
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


class SelectedNamesNormalizationTest(unittest.TestCase):
    """Plan B12: calendar filters must be case-/unicode-/whitespace-insensitive
    so typos like "arbeit" vs "Arbeit " don't silently return an empty list."""

    def setUp(self) -> None:
        # Clear the module-level "warned once" set so each test runs fresh.
        caldav_provider._warned_name_mismatches.clear()

    def _collect(self, calendars: list[_FakeCalendar], selected: list[str]):
        zone = ZoneInfo("Europe/Vienna")
        return _collect_calendar_items(
            calendars=calendars,
            start=datetime(2026, 4, 8, 0, 0, tzinfo=zone),
            end=datetime(2026, 4, 11, 0, 0, tzinfo=zone),
            timezone_name="Europe/Vienna",
            selected_names=selected,
            calendar_parser=None,
        )

    def _cal(self, name: str, url: str | None = None) -> _FakeCalendar:
        return _FakeCalendar(
            name,
            [
                _FakeEvent([
                    _FakeComponent(summary="Event", dtstart=date(2026, 4, 9))
                ])
            ],
            url=url,
        )

    def test_normalize_handles_case_and_whitespace(self) -> None:
        self.assertEqual(normalize_calendar_name("Arbeit"), "arbeit")
        self.assertEqual(normalize_calendar_name("  Arbeit  "), "arbeit")
        self.assertEqual(normalize_calendar_name("ARBEIT"), "arbeit")
        self.assertEqual(normalize_calendar_name(""), "")

    def test_selected_names_match_case_insensitively(self) -> None:
        items = self._collect([self._cal("Arbeit")], ["arbeit"])
        self.assertEqual(len(items), 1)

    def test_selected_names_match_displayname_with_whitespace(self) -> None:
        items = self._collect([self._cal("Arbeit")], ["  Arbeit "])
        self.assertEqual(len(items), 1)

    def test_selected_names_falls_back_to_url_basename(self) -> None:
        # Some CalDAV servers don't expose a human name, only a URL path.
        calendar = _FakeCalendar(
            "",
            [
                _FakeEvent([
                    _FakeComponent(summary="E", dtstart=date(2026, 4, 9))
                ])
            ],
            url="https://dav.example.com/arbeit/",
        )
        items = self._collect([calendar], ["arbeit"])
        self.assertEqual(len(items), 1)

    def test_empty_match_logs_once(self) -> None:
        # Two ticks with the same mismatch should produce only one warning.
        with self.assertLogs("smart_display.providers.caldav_provider", level="WARNING") as ctx:
            self._collect([self._cal("Privat")], ["arbeit"])
            self._collect([self._cal("Privat")], ["arbeit"])
        self.assertEqual(
            len([line for line in ctx.output if "matched no calendars" in line]), 1
        )


if __name__ == "__main__":
    unittest.main()
