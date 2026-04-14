#!/usr/bin/env bash
# install-pi.sh — Deploys smart-display onto a fresh Raspberry Pi OS Bookworm Lite.
#
# Voraussetzungen:
#   - SD-Karte geflasht mit RPi OS Bookworm Lite (64-bit empfohlen)
#   - SSH, WLAN und User "pi" im Imager konfiguriert
#   - Dieses Repo ist bereits auf den Pi kopiert (git clone oder scp)
#
# Aufruf:
#   sudo bash scripts/install-pi.sh
#
set -euo pipefail

INSTALL_DIR="/opt/smart-display"
SERVICE_USER="pi"
SERVICE_GROUP="pi"

# --- Preflight ---------------------------------------------------------------

if [[ $EUID -ne 0 ]]; then
    echo "Fehler: als root ausführen → sudo bash $0" >&2
    exit 1
fi

if ! id "$SERVICE_USER" &>/dev/null; then
    echo "Fehler: User '$SERVICE_USER' existiert nicht."
    echo "Erstelle ihn im Raspberry Pi Imager oder mit: sudo adduser $SERVICE_USER" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [[ ! -f "$SCRIPT_DIR/pyproject.toml" ]]; then
    echo "Fehler: Script muss aus dem Repository-Root ausgeführt werden." >&2
    exit 1
fi

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Smart Display — Pi Installation        ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# --- 1. System-Pakete --------------------------------------------------------

echo "=== 1/7  System-Pakete installieren ==="
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3-venv \
    python3-dev \
    git \
    xserver-xorg \
    x11-xserver-utils \
    xinit \
    openbox \
    chromium-browser \
    fonts-noto-core \
    libopenjp2-7 \
    libtiff6 \
    libjpeg62-turbo
echo "  OK"

# --- 2. Projekt deployen -----------------------------------------------------

echo "=== 2/7  Projekt nach $INSTALL_DIR deployen ==="
if [[ "$(realpath "$SCRIPT_DIR")" != "$(realpath "$INSTALL_DIR")" ]]; then
    mkdir -p "$INSTALL_DIR"
    rsync -a --delete \
        --exclude '.venv' \
        --exclude 'data' \
        --exclude '.env' \
        --exclude '.env.local' \
        --exclude '__pycache__' \
        "$SCRIPT_DIR/" "$INSTALL_DIR/"
    echo "  Kopiert von $SCRIPT_DIR"
else
    echo "  Repo ist bereits in $INSTALL_DIR"
fi
chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$INSTALL_DIR"

# --- 3. Python venv + Dependencies -------------------------------------------

echo "=== 3/7  Python-Umgebung einrichten ==="
sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/.venv"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip --quiet
sudo -u "$SERVICE_USER" "$INSTALL_DIR/.venv/bin/pip" install -e "$INSTALL_DIR" --quiet
echo "  OK"

# --- 4. .env ------------------------------------------------------------------

echo "=== 4/7  Konfiguration ==="
if [[ ! -f "$INSTALL_DIR/.env" ]]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    chown "$SERVICE_USER":"$SERVICE_GROUP" "$INSTALL_DIR/.env"
    chmod 600 "$INSTALL_DIR/.env"
    echo "  .env angelegt (aus .env.example) — Credentials müssen noch eingetragen werden!"
else
    echo "  .env existiert bereits — wird nicht überschrieben."
fi

# --- 5. Datenverzeichnis -----------------------------------------------------

echo "=== 5/7  Datenverzeichnis ==="
DATA_DIR="$INSTALL_DIR/data"
mkdir -p "$DATA_DIR/screensaver"
chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$DATA_DIR"
echo "  $DATA_DIR bereit"

# --- 6. X11 / Kiosk ----------------------------------------------------------

echo "=== 6/7  Kiosk vorbereiten ==="
chmod +x "$INSTALL_DIR/deploy/x11/kiosk-session.sh"

# xinit braucht diese Einstellung damit ein non-root User X starten darf
XWRAPPER="/etc/X11/Xwrapper.config"
if [[ ! -f "$XWRAPPER" ]] || ! grep -q "allowed_users=anybody" "$XWRAPPER"; then
    mkdir -p /etc/X11
    echo "allowed_users=anybody" > "$XWRAPPER"
    echo "  Xwrapper.config: allowed_users=anybody gesetzt"
fi

# Console-Autologin deaktivieren falls aktiv — systemd managed den Kiosk
echo "  OK"

# --- 7. Systemd ---------------------------------------------------------------

echo "=== 7/7  Systemd-Services ==="
cp "$INSTALL_DIR/deploy/systemd/smart-display.service" /etc/systemd/system/
cp "$INSTALL_DIR/deploy/systemd/smart-display-kiosk.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable smart-display.service smart-display-kiosk.service
echo "  Services aktiviert (starten beim nächsten Boot)"

# --- Fertig -------------------------------------------------------------------

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Installation abgeschlossen!            ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Nächste Schritte:"
echo ""
echo "  1. Credentials eintragen:"
echo "     nano $INSTALL_DIR/.env"
echo ""
echo "  2. Backend starten + Logs prüfen:"
echo "     sudo systemctl start smart-display"
echo "     journalctl -u smart-display -f"
echo ""
echo "  3. Kiosk starten (Display muss angeschlossen sein):"
echo "     sudo systemctl start smart-display-kiosk"
echo "     journalctl -u smart-display-kiosk -f"
echo ""
echo "  4. Oder einfach rebooten — beide Services starten automatisch:"
echo "     sudo reboot"
echo ""
