"""Loopback-only guard for POST endpoints.

Plan B10: the smart display's POST surface (Spotify controls, screensaver
pause state) is meant to be driven exclusively by the kiosk browser that
runs on the same Pi. Waitress is already pinned to ``127.0.0.1`` in
``config/default.yaml`` + ``smart_display/app.py`` so a remote client
*cannot* reach these routes over TCP — this decorator is the belt that
goes with that suspenders, so a mis-reverse-proxy or an accidental bind
to ``0.0.0.0`` does not silently turn the device into an open controller.

The rules:
- ``request.remote_addr`` must be a loopback literal.
- When the browser sent an ``Origin`` or ``Referer`` header (every modern
  browser does for POSTs), the host part must also be loopback — this
  blocks CSRF-style cross-origin POSTs from a malicious page even if the
  attacker somehow reached the server via another route.

We use a Flask-level decorator instead of ``before_request`` so that only
the mutating endpoints are checked; GETs remain trivially reachable by
``http://127.0.0.1:8080`` which is all we need.
"""

from __future__ import annotations

from functools import wraps
from typing import Callable
from urllib.parse import urlparse

from flask import Response, jsonify, request


_LOOPBACK_ADDRS = frozenset({"127.0.0.1", "::1", "localhost"})


def _is_loopback_host(host: str) -> bool:
    if not host:
        return False
    host = host.strip().lower()
    if host in _LOOPBACK_ADDRS:
        return True
    # Accept any 127.0.0.0/8 literal (rare but valid loopback).
    return host.startswith("127.")


def assert_local_origin() -> tuple[Response, int] | None:
    """Return a 403 response if the current request is not loopback-only.

    Returning ``None`` means "allowed"; returning a ``(response, status)``
    tuple means the caller should short-circuit with that.
    """
    remote = (request.remote_addr or "").strip()
    if remote not in _LOOPBACK_ADDRS:
        return (
            jsonify({"ok": False, "message": "Nur lokal erreichbar."}),
            403,
        )

    for header_name in ("Origin", "Referer"):
        value = request.headers.get(header_name)
        if not value:
            continue
        parsed = urlparse(value)
        if not _is_loopback_host(parsed.hostname or ""):
            return (
                jsonify({"ok": False, "message": "Nur lokal erreichbar."}),
                403,
            )
    return None


def local_only(func: Callable) -> Callable:
    """Decorator variant of :func:`assert_local_origin`.

    Use this on Flask view functions so each POST endpoint is independently
    annotated (grep-friendly) rather than hiding the check in a blanket
    ``before_request``.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        rejection = assert_local_origin()
        if rejection is not None:
            return rejection
        return func(*args, **kwargs)

    return wrapper
