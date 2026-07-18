#!/usr/bin/env bash
set -euo pipefail

KIOSK_ENV_FILE="${KIOSK_ENV_FILE:-/opt/smart-display/.kiosk.env}"
if [[ -f "$KIOSK_ENV_FILE" ]]; then
  set -a
  # shellcheck source=/opt/smart-display/.kiosk.env
  source "$KIOSK_ENV_FILE"
  set +a
fi

KIOSK_BROWSER="${KIOSK_BROWSER:-chromium}"
KIOSK_URL="${KIOSK_URL:-http://127.0.0.1:8080}"

xset -dpms
xset s off
xset s noblank

openbox-session &
sleep 2

find_command() {
  local candidate
  for candidate in "$@"; do
    if command -v "$candidate" >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

launch_chromium() {
  local chromium_bin
  chromium_bin="${CHROMIUM_BIN:-}"
  if [[ -z "$chromium_bin" ]]; then
    chromium_bin="$(find_command chromium-browser chromium)" || {
      echo "Fehler: Chromium nicht gefunden (chromium-browser/chromium)." >&2
      exit 1
    }
  fi

  exec "$chromium_bin" \
    --no-memcheck \
    --kiosk \
    --app="$KIOSK_URL" \
    --incognito \
    --disable-infobars \
    --disable-pinch \
    --noerrdialogs \
    --overscroll-history-navigation=0 \
    --touch-events=enabled \
    --check-for-update-interval=31536000 \
    --no-first-run \
    --disable-background-networking \
    --disable-default-apps \
    --disable-extensions \
    --disable-notifications \
    --disable-sync \
    --disable-component-update \
    --disable-domain-reliability \
    --disable-features=AutofillServerCommunication,InterestFeedContentSuggestions,MediaRouter,OptimizationHints,Translate
}

launch_cog() {
  local cog_bin
  local args=()
  cog_bin="${COG_BIN:-}"
  if [[ -z "$cog_bin" ]]; then
    cog_bin="$(find_command cog)" || {
      echo "Fehler: cog nicht gefunden." >&2
      exit 1
    }
  fi

  if [[ -n "${KIOSK_COG_PLATFORM:-}" ]]; then
    args+=("-P" "$KIOSK_COG_PLATFORM")
  fi
  if [[ -n "${KIOSK_COG_ARGS:-}" ]]; then
    # Kiosk config is local and admin-controlled; keep this simple for flags.
    read -r -a extra_args <<< "$KIOSK_COG_ARGS"
    args+=("${extra_args[@]}")
  fi

  exec "$cog_bin" "${args[@]}" "$KIOSK_URL"
}

case "$KIOSK_BROWSER" in
  chromium | chromium-browser)
    launch_chromium
    ;;
  cog)
    launch_cog
    ;;
  *)
    echo "Fehler: unbekannter Kiosk-Browser '$KIOSK_BROWSER'." >&2
    exit 1
    ;;
esac
