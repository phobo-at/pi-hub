from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from smart_display.config import AppConfig
from smart_display.models import (
    CalendarEventItem,
    CalendarState,
    SpotifyState,
    WeatherForecastItem,
    WeatherState,
)
from smart_display.providers.caldav_provider import build_calendar_sections
from smart_display.providers.base import BaseProvider
from smart_display.state_store import StateStore


class MockProvider(BaseProvider):
    section_name = "mock"
    source_name = "demo"

    def __init__(self, config: AppConfig, state_store: StateStore):
        super().__init__(60)
        self.config = config
        self.state_store = state_store

    def refresh(self) -> None:
        if not self.config.app.demo_mode:
            return

        if not self.config.weather.enabled:
            self.state_store.update_section(
                "weather",
                WeatherState(
                    snapshot=self.snapshot(status="ok"),
                    location_label="Demo Zuhause",
                    temperature_c=21.4,
                    apparent_temperature_c=20.8,
                    condition="Leicht bewölkt",
                    condition_code=2,
                    forecast=[
                        WeatherForecastItem("Heute", "Leicht bewölkt", 2, 23, 14),
                        WeatherForecastItem("Morgen", "Klar", 0, 24, 13),
                        WeatherForecastItem("Fr.", "Regen", 63, 18, 12),
                    ],
                ),
            )

        if not self.config.calendar.enabled:
            now = datetime.now(ZoneInfo(self.config.app.timezone)).replace(
                minute=0, second=0, microsecond=0
            )
            tomorrow = now + timedelta(days=1)
            day_after_tomorrow = now + timedelta(days=2)
            items = [
                CalendarEventItem(
                    title="Stand-up",
                    starts_at=now.isoformat(),
                    ends_at=(now + timedelta(minutes=30)).isoformat(),
                    time_label=f"{now:%H:%M}–{(now + timedelta(minutes=30)):%H:%M}",
                ),
                CalendarEventItem(
                    title="Abendessen",
                    starts_at=(now + timedelta(hours=3)).isoformat(),
                    ends_at=(now + timedelta(hours=5)).isoformat(),
                    time_label=f"{(now + timedelta(hours=3)):%H:%M}–{(now + timedelta(hours=5)):%H:%M}",
                ),
                CalendarEventItem(
                    title="Fokusblock",
                    starts_at=tomorrow.replace(hour=9).isoformat(),
                    ends_at=tomorrow.replace(hour=10, minute=30).isoformat(),
                    time_label=f"{tomorrow.replace(hour=9):%H:%M}–{tomorrow.replace(hour=10, minute=30):%H:%M}",
                ),
                CalendarEventItem(
                    title="Lieferung",
                    starts_at=day_after_tomorrow.replace(hour=0, minute=0).isoformat(),
                    ends_at=day_after_tomorrow.replace(hour=23, minute=59).isoformat(),
                    time_label="Ganztägig",
                    all_day=True,
                ),
            ]
            self.state_store.update_section(
                "calendar",
                CalendarState(
                    snapshot=self.snapshot(status="ok"),
                    items=items,
                    sections=build_calendar_sections(
                        items,
                        timezone_name=self.config.app.timezone,
                        base_date=now.date(),
                        days=3,
                    ),
                ),
            )

        if not self.config.spotify.enabled:
            self.state_store.update_section(
                "spotify",
                SpotifyState(
                    snapshot=self.snapshot(status="ok"),
                    connected=True,
                    is_playing=True,
                    track_title="Everything In Its Right Place",
                    artist_name="Radiohead",
                    album_name="Kid A",
                    can_control=True,
                    device_name="Wohnzimmer",
                    device_type="Speaker",
                    volume_percent=42,
                    supports_volume=True,
                ),
            )
