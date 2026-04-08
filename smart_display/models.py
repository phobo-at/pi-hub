from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class ProviderSnapshot:
    status: str = "empty"
    updated_at: str | None = None
    stale_after_seconds: int = 0
    error_message: str | None = None
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "updated_at": self.updated_at,
            "stale_after_seconds": self.stale_after_seconds,
            "error_message": self.error_message,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ProviderSnapshot":
        data = data or {}
        return cls(
            status=str(data.get("status", "empty")),
            updated_at=data.get("updated_at"),
            stale_after_seconds=int(data.get("stale_after_seconds", 0) or 0),
            error_message=data.get("error_message"),
            source=data.get("source"),
        )


@dataclass(slots=True)
class WeatherForecastItem:
    day_label: str
    condition: str
    condition_code: int | None = None
    temperature_max_c: float | None = None
    temperature_min_c: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "day_label": self.day_label,
            "condition": self.condition,
            "condition_code": self.condition_code,
            "temperature_max_c": self.temperature_max_c,
            "temperature_min_c": self.temperature_min_c,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WeatherForecastItem":
        return cls(
            day_label=str(data.get("day_label", "")),
            condition=str(data.get("condition", "")),
            condition_code=(
                int(data.get("condition_code"))
                if data.get("condition_code") is not None
                else None
            ),
            temperature_max_c=data.get("temperature_max_c"),
            temperature_min_c=data.get("temperature_min_c"),
        )


@dataclass(slots=True)
class WeatherState:
    snapshot: ProviderSnapshot = field(default_factory=ProviderSnapshot)
    location_label: str = ""
    temperature_c: float | None = None
    apparent_temperature_c: float | None = None
    condition: str = ""
    condition_code: int | None = None
    forecast: list[WeatherForecastItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot": self.snapshot.to_dict(),
            "location_label": self.location_label,
            "temperature_c": self.temperature_c,
            "apparent_temperature_c": self.apparent_temperature_c,
            "condition": self.condition,
            "condition_code": self.condition_code,
            "forecast": [item.to_dict() for item in self.forecast],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "WeatherState":
        data = data or {}
        return cls(
            snapshot=ProviderSnapshot.from_dict(data.get("snapshot")),
            location_label=str(data.get("location_label", "")),
            temperature_c=data.get("temperature_c"),
            apparent_temperature_c=data.get("apparent_temperature_c"),
            condition=str(data.get("condition", "")),
            condition_code=(
                int(data.get("condition_code"))
                if data.get("condition_code") is not None
                else None
            ),
            forecast=[
                WeatherForecastItem.from_dict(item)
                for item in data.get("forecast", []) or []
            ],
        )


@dataclass(slots=True)
class CalendarEventItem:
    title: str
    starts_at: str
    ends_at: str | None
    time_label: str
    all_day: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "starts_at": self.starts_at,
            "ends_at": self.ends_at,
            "time_label": self.time_label,
            "all_day": self.all_day,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CalendarEventItem":
        return cls(
            title=str(data.get("title", "")),
            starts_at=str(data.get("starts_at", "")),
            ends_at=data.get("ends_at"),
            time_label=str(data.get("time_label", "")),
            all_day=bool(data.get("all_day", False)),
        )


@dataclass(slots=True)
class CalendarDaySection:
    day_key: str
    day_label: str
    items: list[CalendarEventItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "day_key": self.day_key,
            "day_label": self.day_label,
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CalendarDaySection":
        return cls(
            day_key=str(data.get("day_key", "")),
            day_label=str(data.get("day_label", "")),
            items=[
                CalendarEventItem.from_dict(item)
                for item in data.get("items", []) or []
            ],
        )


@dataclass(slots=True)
class CalendarState:
    snapshot: ProviderSnapshot = field(default_factory=ProviderSnapshot)
    items: list[CalendarEventItem] = field(default_factory=list)
    sections: list[CalendarDaySection] = field(default_factory=list)
    empty_message: str = "Keine Termine heute."

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot": self.snapshot.to_dict(),
            "items": [item.to_dict() for item in self.items],
            "sections": [section.to_dict() for section in self.sections],
            "empty_message": self.empty_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CalendarState":
        data = data or {}
        return cls(
            snapshot=ProviderSnapshot.from_dict(data.get("snapshot")),
            items=[
                CalendarEventItem.from_dict(item) for item in data.get("items", []) or []
            ],
            sections=[
                CalendarDaySection.from_dict(item)
                for item in data.get("sections", []) or []
            ],
            empty_message=str(data.get("empty_message", "Keine Termine heute.")),
        )


@dataclass(slots=True)
class SpotifyState:
    snapshot: ProviderSnapshot = field(default_factory=ProviderSnapshot)
    connected: bool = False
    is_playing: bool = False
    track_title: str = ""
    artist_name: str = ""
    album_name: str = ""
    album_art_url: str | None = None
    device_name: str | None = None
    device_type: str | None = None
    volume_percent: int | None = None
    supports_volume: bool = False
    can_control: bool = False
    empty_message: str = "Derzeit keine Wiedergabe."

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot": self.snapshot.to_dict(),
            "connected": self.connected,
            "is_playing": self.is_playing,
            "track_title": self.track_title,
            "artist_name": self.artist_name,
            "album_name": self.album_name,
            "album_art_url": self.album_art_url,
            "device_name": self.device_name,
            "device_type": self.device_type,
            "volume_percent": self.volume_percent,
            "supports_volume": self.supports_volume,
            "can_control": self.can_control,
            "empty_message": self.empty_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SpotifyState":
        data = data or {}
        return cls(
            snapshot=ProviderSnapshot.from_dict(data.get("snapshot")),
            connected=bool(data.get("connected", False)),
            is_playing=bool(data.get("is_playing", False)),
            track_title=str(data.get("track_title", "")),
            artist_name=str(data.get("artist_name", "")),
            album_name=str(data.get("album_name", "")),
            album_art_url=data.get("album_art_url"),
            device_name=data.get("device_name"),
            device_type=data.get("device_type"),
            volume_percent=(
                int(data.get("volume_percent"))
                if data.get("volume_percent") is not None
                else None
            ),
            supports_volume=bool(data.get("supports_volume", False)),
            can_control=bool(data.get("can_control", False)),
            empty_message=str(data.get("empty_message", "Derzeit keine Wiedergabe.")),
        )


@dataclass(slots=True)
class SystemState:
    locale: str
    timezone: str
    idle_timeout_seconds: int
    screensaver_interval_seconds: int
    generated_at: str = field(default_factory=utcnow_iso)
    screensaver_photo_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "locale": self.locale,
            "timezone": self.timezone,
            "idle_timeout_seconds": self.idle_timeout_seconds,
            "screensaver_interval_seconds": self.screensaver_interval_seconds,
            "generated_at": self.generated_at,
            "screensaver_photo_count": self.screensaver_photo_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SystemState":
        data = data or {}
        return cls(
            locale=str(data.get("locale", "de-AT")),
            timezone=str(data.get("timezone", "Europe/Vienna")),
            idle_timeout_seconds=int(data.get("idle_timeout_seconds", 120)),
            screensaver_interval_seconds=int(
                data.get("screensaver_interval_seconds", 15)
            ),
            generated_at=str(data.get("generated_at", utcnow_iso())),
            screensaver_photo_count=int(data.get("screensaver_photo_count", 0)),
        )


@dataclass(slots=True)
class PhotoManifestEntry:
    id: str
    source_url: str
    local_path: str
    public_path: str
    width: int = 1024
    height: int = 600
    content_hash: str | None = None
    etag: str | None = None
    last_modified: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_url": self.source_url,
            "local_path": self.local_path,
            "public_path": self.public_path,
            "width": self.width,
            "height": self.height,
            "content_hash": self.content_hash,
            "etag": self.etag,
            "last_modified": self.last_modified,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PhotoManifestEntry":
        return cls(
            id=str(data.get("id", "")),
            source_url=str(data.get("source_url", "")),
            local_path=str(data.get("local_path", "")),
            public_path=str(data.get("public_path", "")),
            width=int(data.get("width", 1024)),
            height=int(data.get("height", 600)),
            content_hash=data.get("content_hash"),
            etag=data.get("etag"),
            last_modified=data.get("last_modified"),
        )


@dataclass(slots=True)
class DashboardState:
    weather: WeatherState
    calendar: CalendarState
    spotify: SpotifyState
    system: SystemState

    def to_dict(self) -> dict[str, Any]:
        return {
            "weather": self.weather.to_dict(),
            "calendar": self.calendar.to_dict(),
            "spotify": self.spotify.to_dict(),
            "system": self.system.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "DashboardState":
        data = data or {}
        return cls(
            weather=WeatherState.from_dict(data.get("weather")),
            calendar=CalendarState.from_dict(data.get("calendar")),
            spotify=SpotifyState.from_dict(data.get("spotify")),
            system=SystemState.from_dict(data.get("system")),
        )
