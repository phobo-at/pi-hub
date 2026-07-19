# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
die Versionierung an [Semantic Versioning](https://semver.org/lang/de/).

Dieser Changelog wurde rückwirkend aus der Git-Historie und den Release-Tags
rekonstruiert (Stand v0.4.0). Ältere Einträge fassen daher zusammen, statt jeden
Commit einzeln aufzuführen.

## [Unreleased]

## [0.5.0] - 2026-07-19

### Entfernt

- Die Seitenindikatoren. Sie waren vertikal gestapelt, obwohl horizontal
  geblättert wird, und zeigten nichts, was der Inhalt nicht ohnehin sagt.
  Mit ihnen fällt `--shell-gutter` weg — eine Kopplung an zwei unabhängig
  justierbare Grid-Splits, die zweimal in Folge repariert werden musste.

### Geändert

- Der Wisch startet jetzt überall, auch über Buttons und Karten: Ein
  horizontaler Zug blättert, ein Tipp löst weiterhin das getroffene Element
  aus. Ausgenommen bleiben die Regler, die die horizontale Achse selbst
  brauchen. Vorher blockierte jeder `button` die Geste — deshalb stand im
  README wörtlich „swipe on a non-interactive part".
- `setPointerCapture` auf der Stage entfällt. Pointer-Events blubbern ohnehin
  hoch, und ein Capture auf dem Vorfahren leitet die Compat-Maus-Events um,
  was Taps auf den jetzt wischbaren Buttons verschluckt hätte.

## [0.4.1] - 2026-07-19

### Behoben

- Die Seitenpunkte saßen auf beiden Screens auf einer Kartenkante statt in der
  Spaltenrinne. Ursache: Home (`0.76fr/1.24fr`) und Spotify-Screen
  (`0.78fr/1.22fr`) haben unterschiedliche Aufteilungen, die Punkte hängen aber
  absolut positioniert am gemeinsamen `.screen-stage` — ein einzelner Wert kann
  nicht für beide stimmen. `--shell-gutter` wird jetzt über
  `[data-active-screen]` pro Screen gesetzt (Home 38,1 %, Spotify 39,1 %);
  gemessen sitzen beide exakt mittig in der 12px-Rinne.

## [0.4.0] - 2026-07-18

### Hinzugefügt

- Zweiter Screen: vollflächige Spotify-Steuerung, erreichbar per Wisch oder
  Seitenpunkt. Großes Artwork, Scrubbing, Transport- und Lautstärkeregler
  (synchron mit dem Homescreen) sowie die nächsten vier Titel der Warteschlange.
  Beide Screens liegen im selben Dokument — kein Router, kein zweiter Seitenaufruf.
- `POST /api/spotify/seek` und `GET /api/spotify/queue`, beide loopback-geschützt.
  Die Warteschlange wird nur geladen, solange der Spotify-Screen sichtbar ist, und
  fällt bei Upstream-Fehlern auf das letzte gute Ergebnis zurück — begrenzt durch
  `_QUEUE_STALE_MAX_AGE_SECONDS`, damit keine stundenalten Titel als aktuell gelten.
- Podcast-Unterstützung: `refresh()` sendet `additional_types=episode`. Ohne diesen
  Parameter liefert Spotify `item: null` für Episoden — laufende Podcasts wurden
  dadurch als „Keine aktive Wiedergabe" angezeigt.

### Geändert

- Der Screensaver setzt die UI immer auf den Homescreen zurück.
- `/api/state` wird pro Sektion dedupliziert, statt über den gesamten State — ein
  Spotify-Update baut Wetter und Kalender nicht mehr neu auf.
- `last_good.json` wird kompakt statt eingerückt geschrieben (weniger SD-Karten-Writes).
- Chromium-Kiosk startet mit zusätzlichen Flags gegen Hintergrund-Netzwerkverkehr,
  Erstlauf-Dialoge und Benachrichtigungen.

### Behoben

- Kalender: Das Zeilenbudget wurde nach einem Spotify-Layoutwechsel nicht neu
  gemessen, wodurch Termine hinter ausgeblendeten Scrollbalken verschwanden.
- Kalender ließ sich nicht mehr per Touch scrollen (`touch-action: none` auf dem
  Screen-Container statt `pan-y`).
- Waitress läuft wieder mit vier Threads: Beim Öffnen der Geräteauswahl laufen zwei
  Spotify-Requests parallel, die sich denselben Host-Lock teilen — mit zwei Threads
  blockierten sie den `/api/state`-Poll und die Screensaver-Routen.
- Eine leere zwischengespeicherte Warteschlange zeigte die Statuszeile
  „zuletzt erfolgreich geladen" als Listeninhalt.
- Der Fortschrittsbalken sprang bei jedem Pause-Tap um bis zu ein Poll-Intervall
  zurück; die optimistische Aktualisierung übernimmt jetzt die interpolierte Position.
- Ein Seek wird verworfen, wenn der Titel während des Ziehens wechselt; Skips setzen
  den Seek-Hold zurück.
- Die Klick-Unterdrückung nach einem Wisch schluckte bis zu 500 ms lang echte Taps —
  jetzt einmalig mit 150 ms Rückfallgrenze.
- Fortschrittsanzeige und analoger Sekundenzeiger laufen nur noch auf dem sichtbaren
  Screen.
- Der Seek-Regler übernimmt die Regeln des Lautstärkereglers und damit die
  1024×600-Größen, die ihm fehlten.
- Die Seitenpunkte folgen der Spaltenaufteilung über `--shell-gutter`, statt einem
  fest verdrahteten Prozentwert, der nur zum Kiosk-Breakpoint passte.
- Genau ein `<main>` pro Dokument; die Screen-Container sind einfache `div`s.

## [0.3.1] - 2026-06-02

### Behoben

- Connect-Lautstärke wird schon bei `input` übernommen, nicht erst bei `change` —
  auf dem Touchpanel kam sonst oft gar kein `change` an.

## [0.3.0] - 2026-06-02

### Hinzugefügt

- Wiedergabe lässt sich aus dem Auswahl-Overlay heraus direkt auf einem
  Connect-Lautsprecher starten. Benötigt den Scope `playlist-read-private` —
  bei älteren Refresh-Tokens `scripts/spotify-auth.py` erneut ausführen.

## [0.2.2] - 2026-06-02

### Behoben

- Lautstärkeregler zentriert und bei Smartphone-Ausgabe deaktiviert, weil Spotify
  dort keine Fernsteuerung der Lautstärke erlaubt.

## [0.2.1] - 2026-06-02

### Geändert

- Rechte Spalte neu gewichtet: Termine kürzer, Spotify größer, sobald eine
  steuerbare Session läuft.

## [0.2.0] - 2026-06-02

### Hinzugefügt

- `scripts/spotify-auth.py` als OAuth-Helfer zum Erzeugen des Refresh-Tokens.
- Gehärtetes Pi-Setup: robusterer `install-pi.sh`-Bootstrap und Kiosk-Start.

### Geändert

- UI-Optimierung für 1024×600: kompaktere Kalenderzeilen, überarbeitetes
  Spotify-Layout, angepasste Typografie.
- Der Frontend-Poll ist vom Spotify-Refresh entkoppelt — `/api/state` ist
  prozessintern und damit billig, der Upstream-Refresh bleibt langsam.

## [0.1.0] - 2026-04-08

Erste Version. Nie getaggt; entstanden zwischen dem 2026-04-08 und 2026-04-15.

### Hinzugefügt

- Smart Display für Raspberry Pi Zero 2 W an einem 1024×600-Touchpanel im
  Kioskmodus: einzelner Flask-Prozess, serverseitig gerendertes HTML und
  Vanilla-JS ohne Build-Schritt.
- Provider für Wetter (Open-Meteo), Kalender (CalDAV/ICS), Spotify und
  Lightroom-Screensaver, jeder als eigener `ScheduledJob` mit eigenem Intervall.
- `StateStore` als einzige schreibbare Zustandsquelle, mit `last_good.json` und
  Schema-Versionierung samt Quarantäne bei Mismatch.
- Sechs Hero-Uhren: `flip`, `lcd`, `pulse`, `qlocktwo`, `qlocktwo-ooe` (oberöster-
  reichischer Dialekt) und `analog`. Auswahl persistiert im `localStorage`.
- Screensaver mit Crossfade, Pause-Gruppen im Scheduler und TTL-Watchdog, damit ein
  abgestürztes Frontend das Polling nicht dauerhaft anhält.
- Sicherheitsgrenzen: POSTs nur von Loopback, Waitress fest auf `127.0.0.1`, lauter
  Abbruch bei abweichendem Bind.
- `install-pi.sh` plus systemd-Units für Backend und Chromium-Kiosk.

[Unreleased]: https://github.com/phobo-at/pi-hub/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/phobo-at/pi-hub/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/phobo-at/pi-hub/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/phobo-at/pi-hub/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/phobo-at/pi-hub/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/phobo-at/pi-hub/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/phobo-at/pi-hub/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/phobo-at/pi-hub/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/phobo-at/pi-hub/releases/tag/v0.2.0
[0.1.0]: https://github.com/phobo-at/pi-hub/commits/v0.2.0
