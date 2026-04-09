from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, request, send_file

from smart_display.i18n import format_initial_clock
from smart_display.models import PhotoManifestEntry
from smart_display.scheduler import DEFAULT_PAUSE_TTL_SECONDS
from smart_display.web.origin_guard import local_only


def create_blueprint() -> Blueprint:
    blueprint = Blueprint("web", __name__)

    @blueprint.get("/")
    def index():
        services = current_app.extensions["smart_display"]
        config = services["config"]
        state = services["state_store"].to_dict()
        # Plan B14: render the hero clock on the server so the cold-reload
        # first frame is correct. JS overwrites these values on its first tick.
        clock_factory = services.get("clock_factory", format_initial_clock)
        initial_clock = clock_factory(config.app.timezone)
        return render_template(
            "index.html",
            app_title="Smart Display",
            ui_config={
                "locale": config.app.locale,
                "timezone": config.app.timezone,
                "idle_timeout_seconds": config.screensaver.idle_timeout_seconds,
                "image_duration_seconds": config.screensaver.image_duration_seconds,
                "poll_interval_seconds": max(
                    min(config.refresh_intervals.spotify_seconds, 30), 5
                ),
            },
            initial_state=state,
            initial_clock=initial_clock,
        )

    @blueprint.get("/api/state")
    def api_state():
        services = current_app.extensions["smart_display"]
        return jsonify(services["state_store"].to_dict())

    @blueprint.get("/api/screensaver/next")
    def next_screensaver_image():
        services = current_app.extensions["smart_display"]
        image_cache = services["image_cache"]
        config = services["config"]
        entry: PhotoManifestEntry | None = image_cache.next_entry(
            include_demo=config.screensaver.demo_images_enabled
        )
        if entry is None:
            return jsonify({"image": None})
        return jsonify({"image": entry.to_dict()})

    @blueprint.post("/api/screensaver/state")
    @local_only
    def screensaver_state():
        """Plan B1: the frontend tells us when the screensaver is visible so
        we can pause the Spotify polling group. Saves one request every 30 s
        whenever the user is away from the panel.

        The pause carries a TTL watchdog (``DEFAULT_PAUSE_TTL_SECONDS``) so
        a crashed frontend cannot strand the Spotify polling forever — the
        pause self-clears well before anyone notices, and a live frontend
        refreshes the timer implicitly via its periodic state POSTs.
        """
        services = current_app.extensions["smart_display"]
        payload = request.get_json(silent=True) or {}
        active = bool(payload.get("active", False))
        scheduler = services.get("scheduler")
        if scheduler is not None:
            if active:
                scheduler.set_paused(
                    "spotify", True, ttl_seconds=DEFAULT_PAUSE_TTL_SECONDS
                )
            else:
                scheduler.set_paused("spotify", False)
        return jsonify({"ok": True, "active": active})

    @blueprint.post("/api/spotify/toggle")
    @local_only
    def spotify_toggle():
        services = current_app.extensions["smart_display"]
        return jsonify(services["spotify_provider"].toggle_playback())

    @blueprint.post("/api/spotify/next")
    @local_only
    def spotify_next():
        services = current_app.extensions["smart_display"]
        return jsonify(services["spotify_provider"].next_track())

    @blueprint.post("/api/spotify/previous")
    @local_only
    def spotify_previous():
        services = current_app.extensions["smart_display"]
        return jsonify(services["spotify_provider"].previous_track())

    @blueprint.post("/api/spotify/volume")
    @local_only
    def spotify_volume():
        services = current_app.extensions["smart_display"]
        payload = request.get_json(silent=True) or {}
        try:
            volume_percent = int(payload["volume_percent"])
        except (KeyError, TypeError, ValueError):
            return jsonify({"ok": False, "message": "volume_percent fehlt oder ist ungültig."}), 400
        return jsonify(services["spotify_provider"].set_volume(volume_percent))

    @blueprint.get("/health")
    def health():
        services = current_app.extensions["smart_display"]
        return jsonify(services["state_store"].health_payload())

    @blueprint.get("/media/screensaver/<path:filename>")
    def screensaver_media(filename: str):
        services = current_app.extensions["smart_display"]
        entry = services["image_cache"].entry_for_filename(filename)
        if entry is None:
            return jsonify({"error": "not found"}), 404
        return send_file(Path(entry.local_path))

    return blueprint
