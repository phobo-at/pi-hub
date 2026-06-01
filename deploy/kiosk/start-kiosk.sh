#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${SMART_DISPLAY_INSTALL_DIR:-/opt/smart-display}"
KIOSK_ENV_FILE="${KIOSK_ENV_FILE:-$INSTALL_DIR/.kiosk.env}"

if [[ -f "$KIOSK_ENV_FILE" ]]; then
  set -a
  # shellcheck source=/opt/smart-display/.kiosk.env
  source "$KIOSK_ENV_FILE"
  set +a
fi

KIOSK_BROWSER="${KIOSK_BROWSER:-chromium}"
KIOSK_URL="${KIOSK_URL:-http://127.0.0.1:8080}"
KIOSK_HEALTH_URL="${KIOSK_HEALTH_URL:-${KIOSK_URL%/}/health}"
KIOSK_WAIT_TIMEOUT_SECONDS="${KIOSK_WAIT_TIMEOUT_SECONDS:-45}"

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
  exec /usr/bin/xinit "$INSTALL_DIR/deploy/x11/kiosk-session.sh" -- :0 vt1 -nolisten tcp
}

wait_for_backend() {
  local started_at
  local now

  if ! command -v python3 >/dev/null 2>&1; then
    echo "Warnung: python3 nicht gefunden; überspringe Backend-Wait." >&2
    return 0
  fi

  started_at="$(date +%s)"
  while true; do
    if python3 - "$KIOSK_HEALTH_URL" <<'PY'
import json
import sys
import urllib.request

url = sys.argv[1]
try:
    with urllib.request.urlopen(url, timeout=1.5) as response:
        payload = json.loads(response.read().decode("utf-8"))
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if payload.get("status") == "ok" else 1)
PY
    then
      return 0
    fi

    now="$(date +%s)"
    if (( now - started_at >= KIOSK_WAIT_TIMEOUT_SECONDS )); then
      echo "Warnung: Backend unter $KIOSK_HEALTH_URL nach ${KIOSK_WAIT_TIMEOUT_SECONDS}s nicht bereit; starte Kiosk trotzdem." >&2
      return 0
    fi
    sleep 1
  done
}

launch_cog() {
  local cog_bin
  local platform
  local args=()

  cog_bin="${COG_BIN:-}"
  if [[ -z "$cog_bin" ]]; then
    cog_bin="$(find_command cog)" || {
      echo "Fehler: cog nicht gefunden." >&2
      exit 1
    }
  fi

  platform="${KIOSK_COG_PLATFORM:-drm}"
  args+=("-P" "$platform")
  args+=("--doc-viewer" "--webprocess-failure=restart" "--bg-color=#000000ff")
  if [[ -n "${KIOSK_COG_ARGS:-}" ]]; then
    # Kiosk config is local and admin-controlled; keep this simple for flags.
    read -r -a extra_args <<< "$KIOSK_COG_ARGS"
    args+=("${extra_args[@]}")
  fi

  exec "$cog_bin" "${args[@]}" "$KIOSK_URL"
}

wait_for_backend

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
