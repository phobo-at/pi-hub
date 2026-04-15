# Smart Display für Raspberry Pi Zero 2 W

Leichtgewichtige Smart-Display-Anwendung für ein `1024x600` Touch-Panel im Kiosk-Betrieb. Die Basis ist bewusst knapp gehalten: ein einzelner Python-Prozess aggregiert Daten, cached Bildquellen und liefert eine kleine servergerenderte Web-UI aus. Der Browser auf dem Pi rendert nur lokale HTML-, CSS- und JavaScript-Dateien.

## Watch Faces

Sechs austauschbare Hero-Uhren, per Touch auf die Hero-Uhr durchschaltbar. Auswahl persistiert im Browser (`localStorage`).

| | | |
|---|---|---|
| ![Flip](docs/screenshots/flip.png) **Flip** (Default) | ![LCD](docs/screenshots/lcd.png) **LCD** | ![Pulse](docs/screenshots/pulse.png) **Pulse** |
| ![QLOCKTWO](docs/screenshots/qlocktwo.png) **QLOCKTWO** | ![QLOCKTWO OÖ](docs/screenshots/qlocktwo-ooe.png) **QLOCKTWO OÖ** | ![Analog](docs/screenshots/analog.png) **Analog** |

Screenshots werden mit `bash scripts/take-screenshots.sh` neu generiert (Headless Chrome gegen den lokalen Demo-Server, 1024×600).

## Architektur

- Backend: `Python 3.11`, `Flask`, `Waitress`
- UI: servergerenderte Shell mit `HTML`, `CSS`, `Vanilla JS`
- Datenfluss: Hintergrundjobs laden Wetter, CalDAV, Spotify und Lightroom periodisch; die UI pollt nur `GET /api/state`
- Persistenz: `data/last_good.json` für den letzten gültigen Dashboard-Zustand, `data/screensaver/manifest.json` plus vorkonvertierte Bilder für den Screensaver
- Betriebsmodell: `smart-display.service` startet das Backend, `smart-display-kiosk.service` startet Chromium im Vollbild

## Warum dieser Stack

- Kein schweres SPA-Framework: deutlich weniger RAM, weniger Re-Render, kein JS-Build zur Laufzeit auf dem Pi
- Python passt gut zu CalDAV, Bildaufbereitung und pragmatischem HTML-Scraping für Lightroom
- Eine lokale Web-UI bleibt leicht deploybar und trennt Datenbeschaffung sauber von Darstellung
- `last known good` und lokaler Bild-Cache sorgen dafür, dass Ausfälle einzelner Dienste die Oberfläche nicht zerlegen

## Projektstruktur

```text
config/                  JSON-kompatible YAML-Defaults
deploy/systemd/          systemd-Units für Backend und Kiosk
deploy/x11/              Kiosk-Startskript für Chromium
smart_display/           App, Provider, Cache, Scheduler, Web-UI
tests/                   kleine Unit-Tests für Kernlogik
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

Optional für eine lokale Demo ohne echte Accounts:

```bash
APP_DEMO_MODE=true python -m smart_display.app
```

Die Anwendung lauscht standardmäßig auf `http://127.0.0.1:8080`.

## Lokaler Testserver

Für Desktop-Tests gibt es jetzt einen getrennten lokalen Demo-Server. Er nutzt `config/local-demo.yaml`, ein eigenes Datenverzeichnis unter `data/local-demo`, Demo-Bilder für den Screensaver und Mock-Daten für Wetter, Termine und Spotify.

Start:

```bash
python -m smart_display.local_server
```

oder nach `pip install -e .`:

```bash
smart-display-local
```

Der lokale Testserver lauscht standardmäßig auf `http://127.0.0.1:8090`.

Optional kannst du `.env.local` aus `.env.local.example` ableiten. Diese Datei wird nach `.env` geladen und überschreibt sie, damit lokale Tests nicht in dieselben Datenpfade oder Provider-Konfigurationen laufen müssen.

## Konfiguration

Die Defaults liegen in `config/default.yaml`. Secrets und gerätespezifische Werte kommen in `.env`.

Wichtige Schlüssel:

- `APP_LOCALE`, `APP_TIMEZONE`
- `APP_WATCH_FACE` — Start-Uhr-Stil (`flip` Default, `lcd`, `pulse`, `qlocktwo`, `qlocktwo-ooe`, `analog`); per Touch auf die Hero-Uhr durchschaltbar, Auswahl persistiert im Browser
- `WEATHER_LATITUDE`, `WEATHER_LONGITUDE`, `WEATHER_LABEL`
- `CALENDAR_URL`, `CALENDAR_USERNAME`, `CALENDAR_PASSWORD`, `CALENDAR_NAME`
- `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REFRESH_TOKEN`, `SPOTIFY_DEVICE_ID`
- `SCREENSAVER_SOURCE_URL`, `SCREENSAVER_IDLE_TIMEOUT_SECONDS`, `SCREENSAVER_REFRESH_INTERVAL_SECONDS`

## Betrieb auf dem Pi

Einfachster Weg auf frischem Raspberry Pi OS Bookworm Lite: Repo clonen und `scripts/install-pi.sh` ausführen. Das Script installiert X11-/Kiosk-Pakete, legt venv an, setzt `Xwrapper.config`, deployt nach `/opt/smart-display` und aktiviert beide systemd-Units.

```bash
sudo bash scripts/install-pi.sh
```

Danach `.env` unter `/opt/smart-display/.env` mit Credentials füllen und rebooten.

Manuelle Schritte (falls nicht über das Script):

1. Raspberry Pi OS Bookworm Lite installieren
2. Minimales X11-/Kiosk-Setup installieren:

```bash
sudo apt install --no-install-recommends xserver-xorg x11-xserver-utils xinit openbox chromium-browser fonts-noto-core
```

3. Projekt nach `/opt/smart-display` deployen, venv anlegen und `pip install -e .`
4. `.env` auf dem Pi ablegen
5. systemd-Units aus `deploy/systemd/smart-display.service` und `deploy/systemd/smart-display-kiosk.service` anpassen und aktivieren
6. `deploy/x11/kiosk-session.sh` ausführbar machen

## Kiosk-Strategie

- Chromium startet mit `--kiosk --app=http://127.0.0.1:8080`
- Touch-Ereignisse setzen den Idle-Timer zurück
- Nach Inaktivität aktiviert sich ein Vollbild-Screensaver
- Die Bildquelle wird ausschließlich aus lokal gecachten Bildern oder Demo-Assets gelesen

## Failure Modes

- Wetter, CalDAV und Spotify setzen bei Fehlern nur ihre jeweilige Kachel auf `Cache` oder `Fehler`
- Screensaver bleibt bei Lightroom-Problemen auf bestehendem lokalen Cache oder Demo-Bildern
- Ohne verfügbare Fotos zeigt der Screensaver einen ruhigen Uhr-Fallback statt einer leeren Fläche

## Bekannte Grenzen

- Spotify benötigt Premium und ein erreichbares Connect-Ziel
- CalDAV-Parsing basiert auf `caldav` und `icalendar`; unterschiedliche Server können leichte Anpassungen nötig machen
- Lightroom-Sharing ist absichtlich pragmatisch implementiert und hängt von öffentlichen Bild-URLs im HTML ab
- Die Demo-Bilder sind Platzhalter für den Erststart und kein Ersatz für einen echten Foto-Feed
