"""Calendar label helpers.

Pure functions that map a section's ISO date plus the current "today" to a
human label ("Heute"/"Morgen"/"Übermorgen"/"Mittwoch"…). The equivalent JS
implementation lives in ``smart_display/web/static/js/app.js``
(``computeDayLabel``); keep them in sync — Python is the source of truth
for tests.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

from smart_display.models import CalendarDaySection


GERMAN_WEEKDAYS_LONG = [
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag",
]


def compute_day_label(section_date_iso: str, today_iso: str) -> str:
    """Return the German label for a calendar section date.

    Rules:
    - ``section_date == today`` → "Heute"
    - ``section_date == today + 1`` → "Morgen"
    - ``section_date == today + 2`` → "Übermorgen"
    - anything else (future or past/stale) → full German weekday name

    Invalid ISO dates return an empty string; the caller decides how to render
    that (we don't want to crash the UI over a malformed cache payload).
    """
    try:
        section_date = date.fromisoformat(section_date_iso)
        today = date.fromisoformat(today_iso)
    except ValueError:
        return ""
    diff = (section_date - today).days
    if diff == 0:
        return "Heute"
    if diff == 1:
        return "Morgen"
    if diff == 2:
        return "Übermorgen"
    return GERMAN_WEEKDAYS_LONG[section_date.weekday()]


def apply_day_labels(
    sections: Iterable[CalendarDaySection], today_iso: str
) -> list[tuple[CalendarDaySection, str]]:
    """Pair each section with its computed label without mutating the section.

    Kept pure so tests can simulate midnight rollovers by just changing
    ``today_iso`` without having to rebuild the sections.
    """
    return [
        (section, compute_day_label(section.section_date, today_iso))
        for section in sections
    ]
