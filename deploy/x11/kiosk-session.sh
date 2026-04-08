#!/usr/bin/env bash
set -euo pipefail

xset -dpms
xset s off
xset s noblank

openbox-session &
sleep 2

chromium-browser \
  --kiosk \
  --app=http://127.0.0.1:8080 \
  --incognito \
  --disable-infobars \
  --disable-pinch \
  --noerrdialogs \
  --overscroll-history-navigation=0 \
  --touch-events=enabled \
  --check-for-update-interval=31536000

