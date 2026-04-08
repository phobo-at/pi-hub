"""Thin stdlib HTTP wrapper with connection reuse and bounded reads.

Built on http.client because the target runs on a Pi Zero 2 W and every
external dependency costs RAM and CPU. Connection reuse per host keeps TLS
handshakes off the hot path; bounded reads protect the Pi from runaway
responses (Spotify errors that bleed a stack trace, HTML dumps from
Lightroom pages).

Design notes:
- Non-2xx responses are returned as HttpResponse, not raised. Callers decide.
- Network-level failures raise HttpError so refresh() paths can mark the
  section stale via state_store.mark_error.
- Accept-Encoding: identity on purpose — decompression wastes Pi CPU.
- Connection: keep-alive + one pooled connection per host. On BadStatusLine,
  RemoteDisconnected, timeout, or ConnectionError the connection is rebuilt
  once and the request retried.
- max_bytes defaults to 2 MB. Image downloads pass a larger cap.
"""

from __future__ import annotations

import http.client
import json as _json
import socket
import threading
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


DEFAULT_USER_AGENT = "pi-hub-smart-display/1.0"
DEFAULT_TIMEOUT = 8.0
DEFAULT_MAX_BYTES = 2_000_000
_CHUNK_SIZE = 64 * 1024


class HttpError(Exception):
    """Raised for network-level failures (DNS, connection, timeout, oversized)."""


@dataclass(slots=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes
    url: str

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def text(self, encoding: str = "utf-8") -> str:
        return self.body.decode(encoding, errors="replace")

    def json(self) -> Any:
        if not self.body:
            return None
        return _json.loads(self.body.decode("utf-8"))


@dataclass
class _HostConnection:
    scheme: str
    host: str
    port: int | None
    connection: http.client.HTTPConnection | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class HttpClient:
    """Minimal HTTP(S) client. Thread-safe via per-host locks."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        default_timeout: float = DEFAULT_TIMEOUT,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self._user_agent = user_agent
        self._default_timeout = default_timeout
        self._max_bytes = max_bytes
        self._pool: dict[tuple[str, str, int | None], _HostConnection] = {}
        self._pool_lock = threading.Lock()

    # ---- public API -------------------------------------------------------

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> HttpResponse:
        return self.request("GET", url, headers=headers, timeout=timeout, max_bytes=max_bytes)

    def post_form(
        self,
        url: str,
        data: Mapping[str, Any],
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> HttpResponse:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        merged = {
            "Content-Type": "application/x-www-form-urlencoded",
            **(dict(headers) if headers else {}),
        }
        return self.request(
            "POST",
            url,
            body=encoded,
            headers=merged,
            timeout=timeout,
            max_bytes=max_bytes,
        )

    def post_json(
        self,
        url: str,
        payload: Any,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> HttpResponse:
        body = _json.dumps(payload).encode("utf-8")
        merged = {
            "Content-Type": "application/json",
            **(dict(headers) if headers else {}),
        }
        return self.request(
            "POST",
            url,
            body=body,
            headers=merged,
            timeout=timeout,
            max_bytes=max_bytes,
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> HttpResponse:
        parsed = urllib.parse.urlsplit(url)
        scheme = parsed.scheme or "https"
        if scheme not in {"http", "https"}:
            raise HttpError(f"unsupported scheme: {scheme}")
        host = parsed.hostname or ""
        if not host:
            raise HttpError(f"missing host: {url}")
        port = parsed.port
        path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))

        merged_headers = {
            "Host": parsed.netloc,
            "User-Agent": self._user_agent,
            "Accept-Encoding": "identity",
            "Connection": "keep-alive",
        }
        if headers:
            for key, value in headers.items():
                merged_headers[key] = value
        if body is not None and "Content-Length" not in merged_headers:
            merged_headers["Content-Length"] = str(len(body))

        cap = max_bytes if max_bytes is not None else self._max_bytes
        effective_timeout = timeout if timeout is not None else self._default_timeout
        host_conn = self._get_host_connection(scheme, host, port)

        with host_conn.lock:
            attempts = 0
            while True:
                attempts += 1
                try:
                    conn = self._ensure_connection(host_conn, effective_timeout)
                    conn.request(method.upper(), path, body=body, headers=merged_headers)
                    raw = conn.getresponse()
                    status = raw.status
                    response_headers = {k.lower(): v for k, v in raw.getheaders()}
                    payload = self._read_bounded(raw, response_headers, cap)
                    return HttpResponse(
                        status=status,
                        headers=response_headers,
                        body=payload,
                        url=url,
                    )
                except (
                    http.client.BadStatusLine,
                    http.client.RemoteDisconnected,
                    ConnectionError,
                    TimeoutError,
                    socket.timeout,
                    OSError,
                ) as exc:
                    self._drop_connection(host_conn)
                    if attempts >= 2:
                        raise HttpError(f"{method} {url} failed: {exc}") from exc

    def close(self) -> None:
        with self._pool_lock:
            for host_conn in self._pool.values():
                with host_conn.lock:
                    self._drop_connection(host_conn)
            self._pool.clear()

    # ---- internals --------------------------------------------------------

    def _get_host_connection(
        self, scheme: str, host: str, port: int | None
    ) -> _HostConnection:
        key = (scheme, host, port)
        with self._pool_lock:
            host_conn = self._pool.get(key)
            if host_conn is None:
                host_conn = _HostConnection(scheme=scheme, host=host, port=port)
                self._pool[key] = host_conn
            return host_conn

    def _ensure_connection(
        self, host_conn: _HostConnection, timeout: float
    ) -> http.client.HTTPConnection:
        conn = host_conn.connection
        if conn is not None:
            return conn
        if host_conn.scheme == "https":
            conn = http.client.HTTPSConnection(
                host_conn.host, port=host_conn.port, timeout=timeout
            )
        else:
            conn = http.client.HTTPConnection(
                host_conn.host, port=host_conn.port, timeout=timeout
            )
        host_conn.connection = conn
        return conn

    def _drop_connection(self, host_conn: _HostConnection) -> None:
        conn = host_conn.connection
        host_conn.connection = None
        if conn is None:
            return
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    def _read_bounded(
        self,
        raw: http.client.HTTPResponse,
        response_headers: Mapping[str, str],
        cap: int,
    ) -> bytes:
        content_length_header = response_headers.get("content-length")
        if content_length_header is not None:
            try:
                declared = int(content_length_header)
            except ValueError:
                declared = -1
            if declared > cap:
                raise HttpError(
                    f"payload too large: {declared} bytes (cap {cap})"
                )
            if declared >= 0:
                return raw.read(declared)

        # No usable Content-Length: read in chunks up to cap + 1 so we can
        # detect oversize without silently truncating.
        buffer = bytearray()
        while len(buffer) <= cap:
            chunk = raw.read(_CHUNK_SIZE)
            if not chunk:
                return bytes(buffer)
            buffer.extend(chunk)
            if len(buffer) > cap:
                raise HttpError(f"payload too large: exceeds {cap} bytes")
        return bytes(buffer)


def iter_query(params: Iterable[tuple[str, Any]]) -> str:
    """Small helper: stable query-string encoding for callers that want a URL."""
    return urllib.parse.urlencode(list(params))
