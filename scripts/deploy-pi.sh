#!/usr/bin/env bash
# deploy-pi.sh — Pushes the current working tree onto the running Pi.
#
# This is the *update* path, not the install path. `install-pi.sh` provisions a
# fresh machine (apt packages, venv, systemd units) and is the wrong tool for
# shipping a code change: it reinstalls the world for what is usually a handful
# of static files. This script only syncs the code and restarts the two units.
#
# Safe by construction: the rsync excludes everything that lives *only* on the
# device — credentials (.env, .kiosk.env), the state cache and screensaver
# images (data/), the venv, and the editable-install egg-info. Nothing here
# recreates those, so deleting them would take the device down until the full
# installer is run again.
#
# Aufruf:
#   bash scripts/deploy-pi.sh              # deploy + restart + health check
#   bash scripts/deploy-pi.sh --dry-run    # zeigt nur, was sich ändern würde
#
# Konfiguration:
#   PI_HOST=pi@192.168.178.22   Zielgerät (user@host)
#   PI_DIR=/opt/smart-display   Installationsverzeichnis auf dem Pi
#
set -euo pipefail

cd "$(dirname "$0")/.."

PI_HOST="${PI_HOST:-pi@192.168.178.22}"
PI_DIR="${PI_DIR:-/opt/smart-display}"
HEALTH_URL="http://127.0.0.1:8080/health"
DRY_RUN=false

if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
elif [[ -n "${1:-}" ]]; then
    echo "Unbekanntes Argument: $1 (erlaubt: --dry-run)" >&2
    exit 1
fi

# Keep these in sync with the exclude list in install-pi.sh — anything the
# device owns and the repo does not.
RSYNC_EXCLUDES=(
    --exclude '.venv'
    --exclude 'data'
    --exclude '.env'
    --exclude '.env.local'
    --exclude '.kiosk.env'
    --exclude '__pycache__'
    --exclude '.git'
    --exclude '*.egg-info'
    --exclude '.claude'
)

if [[ -n "$(git status --porcelain)" ]]; then
    echo "Hinweis: Working Tree ist nicht sauber — es wird der Arbeitsstand"
    echo "         deployed, nicht der letzte Commit."
fi

echo "=== 1/3  Code nach ${PI_HOST}:${PI_DIR} synchronisieren ==="
rsync_args=(-a --delete --itemize-changes "${RSYNC_EXCLUDES[@]}")
if [[ "$DRY_RUN" == "true" ]]; then
    rsync_args+=(--dry-run)
fi
rsync "${rsync_args[@]}" ./ "${PI_HOST}:${PI_DIR}/"

if [[ "$DRY_RUN" == "true" ]]; then
    echo
    echo "Dry-Run — nichts verändert, keine Dienste neu gestartet."
    exit 0
fi

# Backend first, then the browser: restarting the kiosk is what reloads the
# page, so doing it last means the panel comes back on the new code rather than
# on a page it fetched mid-restart.
echo "=== 2/3  Dienste neu starten ==="
ssh "$PI_HOST" "sudo systemctl restart smart-display"
ssh "$PI_HOST" "
    for _ in \$(seq 1 30); do
        curl -fs -o /dev/null '$HEALTH_URL' && exit 0
        sleep 1
    done
    echo 'Backend meldet sich nicht auf $HEALTH_URL' >&2
    exit 1
"
ssh "$PI_HOST" "sudo systemctl restart smart-display-kiosk"

echo "=== 3/3  Prüfen ==="
ssh "$PI_HOST" "
    sleep 5
    printf '  Version:  %s\n' \"\$(sed -n 's/^__version__ = \"\(.*\)\"/\1/p' '$PI_DIR/smart_display/__init__.py')\"
    printf '  Backend:  %s\n' \"\$(systemctl is-active smart-display)\"
    printf '  Kiosk:    %s (Restarts: %s)\n' \\
        \"\$(systemctl is-active smart-display-kiosk)\" \\
        \"\$(systemctl show smart-display-kiosk -p NRestarts --value)\"
    curl -fs -o /dev/null -w '  Health:   %{http_code}\n' '$HEALTH_URL'
"

echo
echo "Deployed. Das Panel lässt sich nicht per Screenshot prüfen — Cog rendert"
echo "direkt auf DRM. Kontrolle nur mit einem Blick aufs Gerät."
