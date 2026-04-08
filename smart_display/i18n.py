"""German label helpers for server-rendered UI (Plan B14).

Everything here is stdlib-only. The Pi may not ship a de_DE.UTF-8 locale, so
we hardcode the handful of labels we actually need instead of relying on
``locale.setlocale`` at runtime.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from smart_display.calendar_layout import GERMAN_WEEKDAYS_LONG


GERMAN_MONTHS_LONG = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]


# IANA zone → human German display name. Only populated for zones we care
# about so far; unknown zones fall back to the raw IANA id.
IANA_LABELS: dict[str, str] = {
    "Europe/Vienna": "Mitteleuropäische Zeit",
    "Europe/Berlin": "Mitteleuropäische Zeit",
    "Europe/Zurich": "Mitteleuropäische Zeit",
    "Europe/London": "Britische Zeit",
    "UTC": "Weltzeit (UTC)",
}


def german_timezone_label(iana_name: str) -> str:
    """Return the long German display name for a zone, falling back to the id."""
    return IANA_LABELS.get(iana_name, iana_name)


def format_initial_clock(
    iana_name: str, *, now: datetime | None = None
) -> dict[str, str]:
    """Return the values needed to server-render the hero clock.

    ``now`` is injectable so tests can freeze time. All strings are German
    with real umlauts — no ``--:--`` placeholder, no raw ``Europe/Vienna``.
    """
    zone = ZoneInfo(iana_name)
    current = (now or datetime.now()).astimezone(zone)
    weekday = GERMAN_WEEKDAYS_LONG[current.weekday()]
    month = GERMAN_MONTHS_LONG[current.month - 1]
    return {
        "time": current.strftime("%H:%M"),
        "date": f"{weekday}, {current.day}. {month}",
        "timezone_label": german_timezone_label(iana_name),
    }
