"""Small defensive helpers used by providers (Plan S5).

Open-Meteo, CalDAV, and Spotify all hand us payloads we did not author. A
single ``int(None)`` or ``list[42]`` can kill a whole refresh loop. These
helpers eliminate that entire failure class by falling back to defaults
instead of raising, and by cleanly handling partial / missing fields.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


def safe_int(value: Any, default: int | None = None) -> int | None:
    """Return ``value`` coerced to ``int``, or ``default`` on any failure."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float | None = None) -> float | None:
    """Return ``value`` coerced to ``float``, or ``default`` on any failure."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_index(seq: Any, idx: int, default: Any = None) -> Any:
    """Return ``seq[idx]`` if possible, else ``default``.

    Accepts a non-sequence (returns default), a too-short sequence (returns
    default), and negative indices (caller beware — treated literally)."""
    if not isinstance(seq, (list, tuple, Sequence)) or isinstance(seq, (str, bytes)):
        return default
    try:
        return seq[idx]
    except (IndexError, TypeError):
        return default


def safe_get(mapping: Any, *keys: str, default: Any = None) -> Any:
    """Walk a nested mapping safely. Any non-dict intermediate returns default."""
    current: Any = mapping
    for key in keys:
        if not isinstance(current, Mapping):
            return default
        current = current.get(key, default)
    return current
