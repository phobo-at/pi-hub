# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

Smart Display for a Raspberry Pi Zero 2 W driving a 1024x600 touch panel in kiosk mode. **Hard constraints:** 512 MB RAM target, ARM, always-on, no client-side framework, no JS build step on the device. Every change must be justifiable against this hardware.

The full product brief — UI hierarchy, failure-mode rules, what NOT to regress — is in `AGENTS.md`. Read it before making non-trivial UI or provider changes; the hierarchy decisions there are deliberate and several have been re-litigated already.

User-facing strings are German and must use real umlauts.

## Common commands

```bash
# Run the production app (loads .env, uses config/default.yaml, port 8080)
python -m smart_display.app

# Run the local demo server (config/local-demo.yaml, mocks, port 8090, separate data dir)
python -m smart_display.local_server         # or: smart-display-local

# Demo mode without real accounts on the production entrypoint
APP_DEMO_MODE=true python -m smart_display.app

# Pre-merge checks (from AGENTS.md)
python3 -m compileall smart_display tests
python3 -m unittest discover -s tests

# Run a single test
python3 -m unittest tests.test_calendar_formatting
python3 -m unittest tests.test_calendar_formatting.TestClass.test_method
```

There is no linter or formatter wired up, and no `dev` extras installed — `pyproject.toml`'s `[project.optional-dependencies].dev` is empty. Don't introduce one without asking.

When changing layout, typography, or any visible state, **also validate visually at 1024x600** — not just logically.

## Architecture

Single Flask process. The UI is server-rendered HTML + vanilla JS that polls one endpoint. There is no SPA, no bundler, no client state framework.

**Data flow (one direction):**

```
Scheduler threads → Providers → StateStore (+ DiskCache) → /api/state → app.js poll → DOM
```

- `smart_display/app.py` — `create_app()` wires config, the `StateStore`, the `ImageCache`, all providers, and the `Scheduler`. Each provider is registered as a `ScheduledJob` with its own refresh interval. `serve_app()` runs Waitress and **refuses to start** on anything other than `127.0.0.1`, `::1`, or `localhost` — a misconfigured `APP_HOST` is a loud `RuntimeError`, never a silent coerce.
- `smart_display/scheduler.py` — one daemon thread per job, runs `task()` immediately then on a fixed interval. Exceptions are logged, never raised — a failing provider must not take down the loop. Jobs can belong to a `pause_group`; the screensaver overlay pauses the `spotify` group via `POST /api/screensaver/state` with a TTL watchdog (`DEFAULT_PAUSE_TTL_SECONDS`) so a crashed frontend can't strand the polling. The frontend refreshes the TTL every 5 min while the screensaver is visible.
- `smart_display/state_store.py` — the **only** writable state. Thread-safe (single `Lock`). Every mutation calls `_persist_locked()` which writes `data/last_good.json` via `DiskCache`. On startup, the store rehydrates from `last_good.json` so the UI never boots empty after a power cycle. The payload carries `DASHBOARD_SCHEMA_VERSION`: any breaking change to the `DashboardState` shape **must bump** this constant, otherwise the next boot silently quarantines the stale cache as `last_good.json.corrupt-<ts>` and starts empty.
- `smart_display/providers/` — `BaseProvider` defines the contract: each provider owns one section name, fetches from its source, and either calls `state_store.update_section(...)` on success or `state_store.mark_error(...)` on failure. Provider failures degrade their own tile to `stale`/`error` and **must not** affect other tiles. This is a load-bearing invariant — see `AGENTS.md` "Failure-Mode-Denken".
- `smart_display/cache/` — `DiskCache` is a tiny atomic JSON writer. `ImageCache` downloads screensaver images, normalizes them to 1024x600 with Pillow, writes a manifest, and falls back to bundled demo images when the manifest is empty (`demo_images_enabled`).
- `smart_display/web/routes.py` — small Flask blueprint. Read endpoints: `GET /` (renders `templates/index.html` with `initial_state`), `GET /api/state`, `GET /api/screensaver/next`, `GET /health`, `GET /media/screensaver/<filename>`. Spotify is the only backend-interactive surface: `POST /api/spotify/{toggle,next,previous,volume}` proxies through to `SpotifyProvider`. The hero-clock watch-face toggle is purely client-side (`localStorage`), so it does not hit the backend.
- `smart_display/watch_faces.py` — stdlib-only helpers for the six hero-clock variants (`flip` split-flap digital [default], `lcd` seven-segment, `pulse` minimal digital with seconds, `qlocktwo` German word-clock grid, `qlocktwo-ooe` Upper-Austrian dialect, `analog` SVG). Exposes `qlocktwo_active_cells()`, `qlocktwo_ooe_active_cells()`, `analog_hand_angles()`, and `lcd_segments_for()` for server-side initial render; the same logic is mirrored in `app.js` for subsequent ticks. If you change a QLOCKTWO grid, word coordinates, or the LCD segment map, update **both** sides or tests will drift from the UI.
- `smart_display/web/static/js/app.js` and `static/css/app.css` — the entire frontend. Polling interval is derived from `refresh_intervals.spotify_seconds` clamped to `[5, 30]` and passed in via `ui_config`.
- `smart_display/local_server.py` — a thin wrapper that forces `config/local-demo.yaml`, layers `.env` then `.env.local`, and uses a separate `data/local-demo` directory so desktop testing can't pollute the real cache.

**Config layering** (`smart_display/config.py`, `load_config`):

1. `config/default.yaml` (JSON-compatible)
2. Optional alternate config (`SMART_DISPLAY_CONFIG` env or explicit path) — deep-merged
3. `.env` values
4. `os.environ` — last write wins

Env-var → config-key mapping lives in `_apply_env_overrides`. `CALENDAR_NAME` is comma-split into a list. To add a new config key, extend both the dataclass in `config.py` and the env mapping.

## Conventions worth knowing

- Provider error path: never raise out of `refresh()`. Use `self.snapshot(status=..., error_message=...)` and `state_store.mark_error(...)`. A provider that has been `ok` and now fails should go to `stale`, not `error` — the store does this transition automatically the first time.
- The state shape returned by `/api/state` is what `app.js` consumes; changing field names there is a frontend break. `DashboardState.to_dict()` / `from_dict()` are the source of truth and must round-trip cleanly because `last_good.json` is loaded back through `from_dict`.
- Spotify control endpoints return `{"ok": bool, "message": ...}` so the frontend can show transient errors without re-rendering the whole tile.
- Status badges are hidden in the normal `ok` state by design — don't reintroduce them. Same for the removed "Startbildschirm" heading, the standalone weather card on the right, and the decorative timezone label that used to sit under the hero date (dropped to free vertical space on 1024×600). See `AGENTS.md` "Aktueller UI-Maßstab".
- When adding a new scheduled job, register it in `create_app()` *and* add a refresh interval in `RefreshIntervalsConfig` + `default.yaml` + the env mapping. Don't hardcode an interval at the call site.

## Deployment shape

The Pi runs two systemd units from `deploy/systemd/`: `smart-display.service` (the Waitress backend) and `smart-display-kiosk.service` (Chromium in `--kiosk --app=...` via `deploy/x11/kiosk-session.sh`). Anything that breaks unattended startup, idle behavior, or the screensaver fallback is a release blocker.
