#!/usr/bin/env bash
set -euo pipefail

xset -dpms
xset s off
xset s noblank

openbox-session &
sleep 2

CHROMIUM_BIN="${CHROMIUM_BIN:-}"
if [[ -z "$CHROMIUM_BIN" ]]; then
  if command -v chromium-browser >/dev/null 2>&1; then
    CHROMIUM_BIN="chromium-browser"
  elif command -v chromium >/dev/null 2>&1; then
    CHROMIUM_BIN="chromium"
  else
    echo "Fehler: Chromium nicht gefunden (chromium-browser/chromium)." >&2
    exit 1
  fi
fi

exec "$CHROMIUM_BIN" \
  --kiosk \
  --app=http://127.0.0.1:8080 \
  --incognito \
  --disable-infobars \
  --disable-pinch \
  --noerrdialogs \
  --overscroll-history-navigation=0 \
  --touch-events=enabled \
  --check-for-update-interval=31536000
