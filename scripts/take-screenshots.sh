#!/usr/bin/env bash
# Capture a 1024x600 screenshot for every watch face variant.
# Starts the local demo server once per face with APP_WATCH_FACE set,
# waits for it to come up, then renders the index via headless Chrome.
# Output: docs/screenshots/<face>.png

set -euo pipefail

cd "$(dirname "$0")/.."

FACES=(flip lcd pulse qlocktwo qlocktwo-ooe analog)
PORT=8090
URL="http://127.0.0.1:${PORT}/"
OUT_DIR="docs/screenshots"
PYTHON_BIN="${PYTHON_BIN:-python3}"
CHROME_BIN="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"

if [[ ! -x "${CHROME_BIN}" ]]; then
  echo "Chrome binary not found at ${CHROME_BIN}. Set CHROME_BIN to override." >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"

kill_existing() {
  # Kill any process still listening on the demo port from a previous run.
  if lsof -ti tcp:"${PORT}" >/dev/null 2>&1; then
    lsof -ti tcp:"${PORT}" | xargs kill -9 >/dev/null 2>&1 || true
    sleep 0.3
  fi
}

wait_for_server() {
  for _ in $(seq 1 60); do
    if curl -fs "${URL}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  echo "Server at ${URL} did not come up in time." >&2
  return 1
}

for face in "${FACES[@]}"; do
  echo "→ ${face}"
  kill_existing

  APP_WATCH_FACE="${face}" "${PYTHON_BIN}" -m smart_display.local_server \
    >"/tmp/smart-display-${face}.log" 2>&1 &
  SERVER_PID=$!

  if ! wait_for_server; then
    kill -9 "${SERVER_PID}" >/dev/null 2>&1 || true
    exit 1
  fi

  tmp_profile="$(mktemp -d)"
  # Chrome's headless sometimes hangs after writing the PNG; a 20 s cap is
  # plenty for a single-page screenshot and guarantees forward progress.
  /usr/bin/perl -e 'alarm 20; exec @ARGV' -- "${CHROME_BIN}" \
    --headless=new \
    --disable-gpu \
    --hide-scrollbars \
    --no-sandbox \
    --user-data-dir="${tmp_profile}" \
    --window-size=1024,600 \
    --virtual-time-budget=2500 \
    --screenshot="${PWD}/${OUT_DIR}/${face}.png" \
    "${URL}" >/dev/null 2>&1 || true

  rm -rf "${tmp_profile}"
  kill -9 "${SERVER_PID}" >/dev/null 2>&1 || true
  wait "${SERVER_PID}" 2>/dev/null || true
done

kill_existing
echo "Done. Screenshots in ${OUT_DIR}/"
