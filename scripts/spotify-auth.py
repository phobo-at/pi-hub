#!/usr/bin/env python3
"""One-off helper to mint a Spotify refresh token for the smart display.

Run this on a machine with a browser (e.g. the Mac, NOT the Pi). It starts a
tiny loopback web server, opens the Spotify consent screen, catches the
redirect, and exchanges the code for a long-lived refresh token.

Usage:
    python3 scripts/spotify-auth.py --client-id <ID> --client-secret <SECRET>

Prerequisite in the Spotify developer dashboard
(https://developer.spotify.com/dashboard):
    Add this exact Redirect URI to your app's settings:
        http://127.0.0.1:8888/callback

The scopes requested match what smart_display.providers.spotify_provider needs:
read playback state + control playback (play/pause/next/previous/volume) +
read the user's own playlists so the picker overlay can start music on a
chosen Spotify Connect speaker.

NOTE: ``playlist-read-private`` was added for the Connect picker. If you minted
your refresh token before that, re-run this helper and replace
``SPOTIFY_REFRESH_TOKEN`` — otherwise ``GET /me/playlists`` returns 403 and the
playlist list stays empty.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import sys
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = (
    "user-read-playback-state user-modify-playback-state "
    "user-read-currently-playing playlist-read-private "
    "playlist-read-collaborative"
)
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"

_result: dict[str, str] = {}


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 — http.server API
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = dict(urllib.parse.parse_qsl(parsed.query))
        _result.update(params)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if "code" in params:
            body = "<h1>Fertig.</h1><p>Du kannst dieses Fenster schließen.</p>"
        else:
            body = f"<h1>Fehler</h1><pre>{params}</pre>"
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *_args) -> None:  # silence the default stderr logging
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-id", default=os.environ.get("SPOTIFY_CLIENT_ID"))
    parser.add_argument(
        "--client-secret", default=os.environ.get("SPOTIFY_CLIENT_SECRET")
    )
    args = parser.parse_args()
    if not args.client_id or not args.client_secret:
        parser.error(
            "Client ID/Secret fehlen — entweder --client-id/--client-secret übergeben "
            "oder SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET in der Umgebung setzen."
        )

    state = secrets.token_urlsafe(16)
    query = urllib.parse.urlencode(
        {
            "client_id": args.client_id,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "state": state,
            "show_dialog": "true",
        }
    )
    authorize = f"{AUTH_URL}?{query}"

    print("Öffne den Browser für die Spotify-Freigabe …")
    print(f"Falls sich nichts öffnet, diese URL manuell aufrufen:\n{authorize}\n")
    webbrowser.open(authorize)

    server = HTTPServer(("127.0.0.1", 8888), _CallbackHandler)
    print("Warte auf Redirect von Spotify (127.0.0.1:8888) …")
    while "code" not in _result and "error" not in _result:
        server.handle_request()

    if "error" in _result:
        print(f"Spotify meldete einen Fehler: {_result['error']}", file=sys.stderr)
        return 1
    if _result.get("state") != state:
        print("State stimmt nicht überein — Abbruch (CSRF-Schutz).", file=sys.stderr)
        return 1

    auth_header = base64.b64encode(
        f"{args.client_id}:{args.client_secret}".encode()
    ).decode()
    data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": _result["code"],
            "redirect_uri": REDIRECT_URI,
        }
    ).encode()
    request = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # noqa: PERF203
        print(f"Token-Exchange fehlgeschlagen: {exc.read().decode()}", file=sys.stderr)
        return 1

    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        print(f"Kein refresh_token erhalten: {payload}", file=sys.stderr)
        return 1

    print("\n=== Erfolg ===")
    print("Trage diese Werte in /opt/smart-display/.env ein:\n")
    print(f"SPOTIFY_CLIENT_ID={args.client_id}")
    print(f"SPOTIFY_CLIENT_SECRET={args.client_secret}")
    print(f"SPOTIFY_REFRESH_TOKEN={refresh_token}")
    print("SPOTIFY_ENABLED=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
