# Smart Display fuer Raspberry Pi Zero 2 W

Leichtgewichtige Smart-Display-Anwendung fuer ein `1024x600` Touch-Panel im Kiosk-Betrieb. Die Basis ist bewusst knapp gehalten: ein einzelner Python-Prozess aggregiert Daten, cached Bildquellen und liefert eine kleine servergerenderte Web-UI aus. Der Browser auf dem Pi rendert nur lokale HTML-, CSS- und JavaScript-Dateien.

## Architektur

- Backend: `Python 3.11`, `Flask`, `Waitress`
- UI: servergerenderte Shell mit `HTML`, `CSS`, `Vanilla JS`
- Datenfluss: Hintergrundjobs laden Wetter, CalDAV, Spotify und Lightroom periodisch; die UI pollt nur `GET /api/state`
- Persistenz: `data/last_good.json` fuer den letzten gueltigen Dashboard-Zustand, `data/screensaver/manifest.json` plus vorkonvertierte Bilder fuer den Screensaver
- Betriebsmodell: `smart-display.service` startet das Backend, `smart-display-kiosk.service` startet Chromium im Vollbild

## Warum dieser Stack

- Kein schweres SPA-Framework: deutlich weniger RAM, weniger Re-Render, kein JS-Build zur Laufzeit auf dem Pi
- Python passt gut zu CalDAV, Bildaufbereitung und pragmatischem HTML-Scraping fuer Lightroom
- Eine lokale Web-UI bleibt leicht deploybar und trennt Datenbeschaffung sauber von Darstellung
- `last known good` und lokaler Bild-Cache sorgen dafuer, dass Ausfaelle einzelner Dienste die Oberflaeche nicht zerlegen

## Projektstruktur

```text
config/                  JSON-kompatible YAML-Defaults
deploy/systemd/          systemd-Units fuer Backend und Kiosk
deploy/x11/              Kiosk-Startskript fuer Chromium
smart_display/           App, Provider, Cache, Scheduler, Web-UI
tests/                   kleine Unit-Tests fuer Kernlogik
data/                    Laufzeitdaten und lokaler Screensaver-Cache
```

## Lokaler Start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.example .env
python -m smart_display.app
```

Optional fuer eine lokale Demo ohne echte Accounts:

```bash
APP_DEMO_MODE=true python -m smart_display.app
```

Die Anwendung lauscht standardmaessig auf `http://127.0.0.1:8080`.

## Lokaler Testserver

Fuer Desktop-Tests gibt es jetzt einen getrennten lokalen Demo-Server. Er nutzt `config/local-demo.yaml`, ein eigenes Datenverzeichnis unter `data/local-demo`, Demo-Bilder fuer den Screensaver und Mock-Daten fuer Wetter, Termine und Spotify.

Start:

```bash
python -m smart_display.local_server
```

oder nach `pip install -e .`:

```bash
smart-display-local
```

Der lokale Testserver lauscht standardmaessig auf `http://127.0.0.1:8090`.

Optional kannst du `.env.local` aus `.env.local.example` ableiten. Diese Datei wird nach `.env` geladen und ueberschreibt sie, damit lokale Tests nicht in dieselben Datenpfade oder Provider-Konfigurationen laufen muessen.

## Konfiguration

Die Defaults liegen in `config/default.yaml`. Secrets und geraetespezifische Werte kommen in `.env`.

Wichtige Schluessel:

- `APP_LOCALE`, `APP_TIMEZONE`
- `WEATHER_LATITUDE`, `WEATHER_LONGITUDE`, `WEATHER_LABEL`
- `CALENDAR_URL`, `CALENDAR_USERNAME`, `CALENDAR_PASSWORD`, `CALENDAR_NAME`
- `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REFRESH_TOKEN`, `SPOTIFY_DEVICE_ID`
- `SCREENSAVER_SOURCE_URL`, `SCREENSAVER_IDLE_TIMEOUT_SECONDS`, `SCREENSAVER_REFRESH_INTERVAL_SECONDS`

## Betrieb auf dem Pi

1. Raspberry Pi OS Bookworm Lite installieren
2. Minimales X11-/Kiosk-Setup installieren:

```bash
sudo apt install --no-install-recommends xserver-xorg x11-xserver-utils xinit openbox chromium-browser fonts-noto-core
```

3. Projekt nach `/opt/smart-display` deployen, venv anlegen und `pip install -e .`
4. `.env` auf dem Pi ablegen
5. systemd-Units aus `deploy/systemd/smart-display.service` und `deploy/systemd/smart-display-kiosk.service` anpassen und aktivieren
6. `deploy/x11/kiosk-session.sh` ausfuehrbar machen

## Kiosk-Strategie

- Chromium startet mit `--kiosk --app=http://127.0.0.1:8080`
- Touch-Ereignisse setzen den Idle-Timer zurueck
- Nach Inaktivitaet aktiviert sich ein Vollbild-Screensaver
- Die Bildquelle wird ausschliesslich aus lokal gecachten Bildern oder Demo-Assets gelesen

## Failure Modes

- Wetter, CalDAV und Spotify setzen bei Fehlern nur ihre jeweilige Kachel auf `Cache` oder `Fehler`
- Screensaver bleibt bei Lightroom-Problemen auf bestehendem lokalen Cache oder Demo-Bildern
- Ohne verfügbare Fotos zeigt der Screensaver einen ruhigen Uhr-Fallback statt einer leeren Flaeche

## Bekannte Grenzen

- Spotify benoetigt Premium und ein erreichbares Connect-Ziel
- CalDAV-Parsing basiert auf `caldav` und `icalendar`; unterschiedliche Server koennen leichte Anpassungen noetig machen
- Lightroom-Sharing ist absichtlich pragmatisch implementiert und haengt von oeffentlichen Bild-URLs im HTML ab
- Die Demo-Bilder sind Platzhalter fuer den Erststart und kein Ersatz fuer einen echten Foto-Feed

## Naechste Schritte

### V1

- Reale Konten anschliessen und Provider am Zielgeraet verifizieren
- Layout auf dem physischen 7-Zoll-Panel feinjustieren
- Logging und systemd-Units auf reale Pi-Pfade haerten

### V1.1

- Kleine Wetterprognose mit feineren Symbolen
- Subtilere Stale-/Offline-Hinweise
- Foto-Auswahl mit Gewichtung gegen direkte Wiederholungen

### V2

- Nachtmodus und Helligkeitslogik
- Optionaler lokaler Foto-Manifest-Generator als Lightroom-Fallback
- Layout-Varianten fuer mehr oder weniger Termine
