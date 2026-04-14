"""Stdlib-only test helpers shared across tests.

No pytest, no external fixtures — just things we reach for again and again:

- FakeClock: deterministic wall + monotonic clock that tests can advance.
- FakeHttpClient: drop-in replacement for smart_display.http_client.HttpClient
  with canned responses and call recording. Same method names/signatures so
  production code can depend on HttpClient and tests inject FakeHttpClient.
- make_app_config / make_state_store: minimal constructors pointing at a
  tmp directory so each test is fully isolated.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from smart_display.config import (
    AppConfig,
    AppSection,
    CalendarConfig,
    RefreshIntervalsConfig,
    ScreensaverConfig,
    SpotifyConfig,
    WeatherConfig,
)
from smart_display.http_client import HttpError, HttpResponse
from smart_display.state_store import StateStore


# ---- Clock -----------------------------------------------------------------


class FakeClock:
    """A deterministic clock. Wall time is a datetime; monotonic is float seconds."""

    def __init__(
        self,
        *,
        wall: datetime | None = None,
        monotonic: float = 0.0,
    ) -> None:
        self._wall = wall or datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)
        self._monotonic = float(monotonic)

    def now(self) -> datetime:
        return self._wall

    def monotonic(self) -> float:
        return self._monotonic

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self._monotonic += float(seconds)
        self._wall = self._wall + timedelta(seconds=float(seconds))

    def set_wall(self, wall: datetime) -> None:
        self._wall = wall


# ---- HTTP ------------------------------------------------------------------


@dataclass(slots=True)
class RecordedCall:
    method: str
    url: str
    body: bytes | None
    headers: dict[str, str]
    timeout: float | None
    max_bytes: int | None


@dataclass
class _Route:
    responses: deque[HttpResponse] = field(default_factory=deque)
    sticky: HttpResponse | None = None
    error: HttpError | None = None


class FakeHttpClient:
    """In-memory HttpClient stand-in.

    Register responses per (METHOD, url) via ``add_response`` or ``queue``.
    - ``add_response(method, url, response)`` sets a sticky answer reused for
      every subsequent matching call.
    - ``queue(method, url, response)`` enqueues single-use answers in order;
      once exhausted the route falls back to the sticky answer (if any) or
      raises AssertionError.
    - ``add_error(method, url, HttpError(...))`` makes matching calls raise.

    Recorded calls are available via ``self.calls``.
    """

    def __init__(self) -> None:
        self._routes: dict[tuple[str, str], _Route] = {}
        self.calls: list[RecordedCall] = []

    # registration ----------------------------------------------------------

    def add_response(
        self,
        method: str,
        url: str,
        *,
        status: int = 200,
        body: bytes | str | dict | list | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        route = self._route(method, url)
        route.sticky = _build_response(method, url, status=status, body=body, headers=headers)

    def queue(
        self,
        method: str,
        url: str,
        *,
        status: int = 200,
        body: bytes | str | dict | list | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        route = self._route(method, url)
        route.responses.append(
            _build_response(method, url, status=status, body=body, headers=headers)
        )

    def add_error(self, method: str, url: str, error: HttpError) -> None:
        route = self._route(method, url)
        route.error = error

    # HttpClient-compatible API --------------------------------------------

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> HttpResponse:
        return self.request("GET", url, headers=headers, timeout=timeout, max_bytes=max_bytes)

    def post_form(
        self,
        url: str,
        data: Mapping[str, Any],
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> HttpResponse:
        import urllib.parse

        body = urllib.parse.urlencode(data).encode("utf-8")
        merged = {"Content-Type": "application/x-www-form-urlencoded", **(dict(headers) if headers else {})}
        return self.request("POST", url, body=body, headers=merged, timeout=timeout, max_bytes=max_bytes)

    def post_json(
        self,
        url: str,
        payload: Any,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> HttpResponse:
        import json as _json

        body = _json.dumps(payload).encode("utf-8")
        merged = {"Content-Type": "application/json", **(dict(headers) if headers else {})}
        return self.request("POST", url, body=body, headers=merged, timeout=timeout, max_bytes=max_bytes)

    def request(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> HttpResponse:
        normalized = method.upper()
        self.calls.append(
            RecordedCall(
                method=normalized,
                url=url,
                body=body,
                headers=dict(headers) if headers else {},
                timeout=timeout,
                max_bytes=max_bytes,
            )
        )
        route = self._routes.get((normalized, url))
        if route is None:
            raise AssertionError(
                f"FakeHttpClient: no response registered for {normalized} {url}"
            )
        if route.error is not None:
            raise route.error
        if route.responses:
            return route.responses.popleft()
        if route.sticky is not None:
            return route.sticky
        raise AssertionError(
            f"FakeHttpClient: queued responses exhausted for {normalized} {url}"
        )

    def close(self) -> None:
        pass

    def calls_matching(self, method: str, url: str) -> list[RecordedCall]:
        normalized = method.upper()
        return [c for c in self.calls if c.method == normalized and c.url == url]

    # internals -------------------------------------------------------------

    def _route(self, method: str, url: str) -> _Route:
        key = (method.upper(), url)
        route = self._routes.get(key)
        if route is None:
            route = _Route()
            self._routes[key] = route
        return route


def _build_response(
    method: str,
    url: str,
    *,
    status: int,
    body: bytes | str | dict | list | None,
    headers: Mapping[str, str] | None,
) -> HttpResponse:
    import json as _json

    if body is None:
        payload = b""
    elif isinstance(body, bytes):
        payload = body
    elif isinstance(body, str):
        payload = body.encode("utf-8")
    else:
        payload = _json.dumps(body).encode("utf-8")
    merged_headers = {k.lower(): v for k, v in (headers or {}).items()}
    return HttpResponse(status=status, headers=merged_headers, body=payload, url=url)


# ---- AppConfig / StateStore factories --------------------------------------


def make_app_config(
    tmp_dir: Path,
    *,
    timezone_name: str = "Europe/Vienna",
    locale: str = "de-AT",
    spotify_enabled: bool = False,
    spotify_client_id: str = "",
    spotify_client_secret: str = "",
    spotify_refresh_token: str = "",
    calendar_enabled: bool = False,
    weather_enabled: bool = False,
) -> AppConfig:
    data_dir = Path(tmp_dir) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return AppConfig(
        root_dir=Path(tmp_dir),
        app=AppSection(
            host="127.0.0.1",
            port=8080,
            locale=locale,
            timezone=timezone_name,
            data_dir=data_dir,
            log_level="INFO",
            demo_mode=False,
            watch_face="classic",
        ),
        weather=WeatherConfig(
            enabled=weather_enabled,
            provider="openmeteo",
            label="Zuhause",
            latitude=48.2082,
            longitude=16.3738,
            api_key=None,
            timeout_seconds=10,
        ),
        calendar=CalendarConfig(
            enabled=calendar_enabled,
            url="",
            username="",
            password="",
            calendar_names=[],
            timeout_seconds=10,
        ),
        spotify=SpotifyConfig(
            enabled=spotify_enabled,
            client_id=spotify_client_id,
            client_secret=spotify_client_secret,
            refresh_token=spotify_refresh_token,
            device_id="",
            market="AT",
            timeout_seconds=10,
        ),
        screensaver=ScreensaverConfig(
            enabled=True,
            idle_timeout_seconds=120,
            image_duration_seconds=15,
            refresh_interval_seconds=1800,
            source_url="",
            cache_dir="screensaver",
            demo_images_enabled=True,
            timeout_seconds=15,
        ),
        refresh_intervals=RefreshIntervalsConfig(
            weather_seconds=900,
            calendar_seconds=300,
            spotify_seconds=30,
            lightroom_seconds=1800,
        ),
    )


def make_state_store(tmp_dir: Path, **overrides: Any) -> StateStore:
    config = make_app_config(tmp_dir, **overrides)
    return StateStore(config)


def drain_responses(routes: Iterable[_Route]) -> None:  # pragma: no cover - debug only
    for route in routes:
        route.responses.clear()
