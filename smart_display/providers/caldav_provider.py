from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from smart_display.config import AppConfig
from smart_display.models import CalendarDaySection, CalendarEventItem, CalendarState
from smart_display.providers.base import BaseProvider
from smart_display.state_store import StateStore


def today_window(
    timezone_name: str, *, now: datetime | None = None
) -> tuple[datetime, datetime]:
    return calendar_window(timezone_name, days=1, now=now)


def calendar_window(
    timezone_name: str, *, days: int = 1, now: datetime | None = None
) -> tuple[datetime, datetime]:
    zone = ZoneInfo(timezone_name)
    current = now.astimezone(zone) if now else datetime.now(zone)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=days)


def build_calendar_item(
    title: str, starts_at: date | datetime, ends_at: date | datetime | None, timezone_name: str
) -> CalendarEventItem:
    zone = ZoneInfo(timezone_name)
    all_day = isinstance(starts_at, date) and not isinstance(starts_at, datetime)
    start_dt = _coerce_datetime(starts_at, zone)
    end_dt = _coerce_datetime(ends_at, zone) if ends_at else None

    if all_day:
        time_label = "Ganztägig"
    elif end_dt:
        time_label = f"{start_dt:%H:%M}–{end_dt:%H:%M}"
    else:
        time_label = f"{start_dt:%H:%M}"

    return CalendarEventItem(
        title=title or "Termin",
        starts_at=start_dt.isoformat(),
        ends_at=end_dt.isoformat() if end_dt else None,
        time_label=time_label,
        all_day=all_day,
    )


def _coerce_datetime(value: date | datetime, zone: ZoneInfo) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=zone)
        return value.astimezone(zone)
    return datetime.combine(value, time.min, tzinfo=zone)


def day_key_for_offset(offset: int) -> str:
    if offset == 0:
        return "today"
    if offset == 1:
        return "tomorrow"
    if offset == 2:
        return "day_after_tomorrow"
    return f"day_{offset}"


def build_calendar_sections(
    items: list[CalendarEventItem],
    *,
    timezone_name: str,
    base_date: date,
    days: int = 3,
) -> list[CalendarDaySection]:
    """Group events into per-day sections, emitting only the ISO section_date.

    Day labels ("Heute"/"Morgen"/…) are deliberately NOT baked in here — the
    client computes them from section_date against its own "today" so the UI
    stays correct across midnight without a server refresh. See
    ``smart_display/calendar_layout.compute_day_label``.
    """
    zone = ZoneInfo(timezone_name)
    buckets: dict[date, list[CalendarEventItem]] = {
        base_date + timedelta(days=offset): [] for offset in range(days)
    }

    for item in items:
        starts_at = datetime.fromisoformat(item.starts_at)
        event_date = (
            starts_at.astimezone(zone).date()
            if starts_at.tzinfo is not None
            else starts_at.date()
        )
        if event_date in buckets:
            buckets[event_date].append(item)

    sections: list[CalendarDaySection] = []
    for offset in range(days):
        current_date = base_date + timedelta(days=offset)
        section_items = sorted(
            buckets[current_date],
            key=lambda current_item: (
                current_item.all_day,
                current_item.starts_at,
                current_item.title.lower(),
            ),
        )
        if not section_items:
            continue
        sections.append(
            CalendarDaySection(
                day_key=day_key_for_offset(offset),
                section_date=current_date.isoformat(),
                items=section_items,
            )
        )

    return sections


class CalDAVProvider(BaseProvider):
    section_name = "calendar"
    source_name = "caldav"

    def __init__(self, config: AppConfig, state_store: StateStore):
        super().__init__(config.refresh_intervals.calendar_seconds)
        self.config = config
        self.state_store = state_store

    def refresh(self) -> None:
        if self.config.app.demo_mode and not self.config.calendar.enabled:
            return

        if not self.config.calendar.enabled or not all(
            [
                self.config.calendar.url,
                self.config.calendar.username,
                self.config.calendar.password,
            ]
        ):
            self.state_store.update_section(
                self.section_name,
                CalendarState(
                    snapshot=self.snapshot(status="empty"),
                    empty_message="Kalender nicht verbunden.",
                ),
            )
            return

        try:
            from caldav import DAVClient  # type: ignore
            from icalendar import Calendar  # type: ignore
        except ImportError as exc:  # pragma: no cover
            self.state_store.mark_error(
                self.section_name,
                error_message=f"CalDAV dependencies fehlen: {exc}",
                stale_after_seconds=self.refresh_interval_seconds * 2,
                source=self.source_name,
            )
            return

        start, end = calendar_window(self.config.app.timezone, days=3)
        items: list[CalendarEventItem] = []

        try:
            with DAVClient(
                url=self.config.calendar.url,
                username=self.config.calendar.username,
                password=self.config.calendar.password,
                timeout=self.config.calendar.timeout_seconds,
            ) as client:
                principal = client.principal()
                calendars = principal.calendars()
                items = _collect_calendar_items(
                    calendars=calendars,
                    start=start,
                    end=end,
                    timezone_name=self.config.app.timezone,
                    selected_names=self.config.calendar.calendar_names,
                    calendar_parser=Calendar,
                )
        except Exception as exc:
            self.logger.exception("calendar refresh failed")
            self.state_store.mark_error(
                self.section_name,
                error_message=str(exc),
                stale_after_seconds=self.refresh_interval_seconds * 2,
                source=self.source_name,
            )
            return

        sections = build_calendar_sections(
            items,
            timezone_name=self.config.app.timezone,
            base_date=start.date(),
            days=3,
        )
        snapshot = self.snapshot(status="ok" if items else "empty")
        state = CalendarState(
            snapshot=snapshot,
            items=items,
            sections=sections,
            empty_message="Keine Termine in den nächsten drei Tagen." if not items else "",
        )
        self.state_store.update_section(self.section_name, state)


def _collect_calendar_items(
    *,
    calendars: list,
    start: datetime,
    end: datetime,
    timezone_name: str,
    selected_names: list[str],
    calendar_parser,
) -> list[CalendarEventItem]:
    selected = {name.strip() for name in selected_names if name.strip()}
    results: list[CalendarEventItem] = []
    seen: set[tuple[str, str]] = set()

    for calendar in calendars:
        display_name = getattr(calendar, "name", "") or getattr(
            calendar, "url", "calendar"
        )
        if selected and str(display_name) not in selected:
            continue

        for event in calendar.date_search(start=start, end=end, expand=True):
            ical = getattr(event, "icalendar_instance", None)
            if ical is None:
                raw_data = getattr(event, "data", None)
                if raw_data:
                    ical = calendar_parser.from_ical(raw_data)
            if ical is None:
                continue

            for component in ical.walk("VEVENT"):
                title = str(component.get("summary", "Termin"))
                starts_at = component.decoded("dtstart")
                ends_at = (
                    component.decoded("dtend") if component.get("dtend") is not None else None
                )
                item = build_calendar_item(title, starts_at, ends_at, timezone_name)
                key = (item.starts_at, item.title)
                if key in seen:
                    continue
                seen.add(key)
                # Plan B11: drop the unconditional ``or item.all_day`` — an
                # all-day event must still fall inside the [start, end)
                # window (``_coerce_datetime`` normalises date → midnight in
                # the configured zone so the same bounds check works).
                event_start = _coerce_datetime(starts_at, ZoneInfo(timezone_name))
                if start <= event_start < end:
                    results.append(item)

    return sorted(results, key=lambda item: (item.starts_at, item.title.lower()))
