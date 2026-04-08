from __future__ import annotations

import atexit
import logging

from flask import Flask

from smart_display.cache.image_cache import ImageCache
from smart_display.config import AppConfig, load_config
from smart_display.providers.caldav_provider import CalDAVProvider
from smart_display.providers.lightroom_source import LightroomSourceProvider
from smart_display.providers.mock_provider import MockProvider
from smart_display.providers.spotify_provider import SpotifyProvider
from smart_display.providers.weather_openmeteo import OpenMeteoProvider
from smart_display.scheduler import ScheduledJob, Scheduler
from smart_display.state_store import StateStore
from smart_display.web.routes import create_blueprint


def create_app(
    config: AppConfig | None = None, *, start_scheduler: bool = True
) -> Flask:
    app_config = config or load_config()
    _configure_logging(app_config)
    app_config.app.data_dir.mkdir(parents=True, exist_ok=True)
    app_config.screensaver_cache_dir.mkdir(parents=True, exist_ok=True)

    state_store = StateStore(app_config)
    image_cache = ImageCache(
        cache_dir=app_config.screensaver_cache_dir,
        manifest_path=app_config.screensaver_manifest_path,
        demo_dir=app_config.root_dir / "smart_display" / "web" / "static" / "images" / "demo-screensaver",
    )

    weather_provider = OpenMeteoProvider(app_config, state_store)
    calendar_provider = CalDAVProvider(app_config, state_store)
    spotify_provider = SpotifyProvider(app_config, state_store)
    screensaver_provider = LightroomSourceProvider(app_config, state_store, image_cache)
    mock_provider = MockProvider(app_config, state_store)

    app = Flask(
        __name__,
        template_folder="web/templates",
        static_folder="web/static",
    )
    app.json.sort_keys = False
    app.extensions["smart_display"] = {
        "config": app_config,
        "state_store": state_store,
        "image_cache": image_cache,
        "spotify_provider": spotify_provider,
    }
    app.register_blueprint(create_blueprint())

    if start_scheduler:
        scheduler = Scheduler()
        # Plan B2: stagger the boot fan-out so the Pi Zero doesn't hammer four
        # upstream APIs in the first second after `systemctl start`. Jitter
        # ±1 s on every subsequent interval spreads refreshes over long uptimes.
        scheduler.start(
            [
                ScheduledJob(
                    name="weather",
                    interval_seconds=app_config.refresh_intervals.weather_seconds,
                    task=weather_provider.refresh,
                    startup_delay_seconds=0.0,
                    jitter_seconds=1.0,
                ),
                ScheduledJob(
                    name="calendar",
                    interval_seconds=app_config.refresh_intervals.calendar_seconds,
                    task=calendar_provider.refresh,
                    startup_delay_seconds=2.0,
                    jitter_seconds=1.0,
                ),
                ScheduledJob(
                    name="spotify",
                    interval_seconds=app_config.refresh_intervals.spotify_seconds,
                    task=spotify_provider.refresh,
                    startup_delay_seconds=4.0,
                    jitter_seconds=1.0,
                    pause_group="spotify",
                ),
                ScheduledJob(
                    name="screensaver",
                    interval_seconds=app_config.refresh_intervals.lightroom_seconds,
                    task=screensaver_provider.refresh,
                    startup_delay_seconds=6.0,
                    jitter_seconds=1.0,
                ),
                ScheduledJob(
                    name="mock",
                    interval_seconds=60,
                    task=mock_provider.refresh,
                    startup_delay_seconds=1.0,
                    jitter_seconds=1.0,
                ),
            ]
        )
        app.extensions["smart_display"]["scheduler"] = scheduler
        atexit.register(scheduler.stop)

    return app


def main() -> None:
    app = create_app()
    serve_app(app)


def serve_app(app: Flask) -> None:
    config: AppConfig = app.extensions["smart_display"]["config"]
    try:
        from waitress import serve
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("waitress is required to run the production server.") from exc

    serve(app, host=config.app.host, port=config.app.port)


def _configure_logging(config: AppConfig) -> None:
    logging.basicConfig(
        level=getattr(logging, config.app.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


if __name__ == "__main__":  # pragma: no cover
    main()
