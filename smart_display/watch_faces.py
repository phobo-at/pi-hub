"""Watch-face helpers shared between server-side initial render and tests.

The hero clock has two visual variants:

* ``classic`` – the familiar large ``HH:MM`` digital clock.
* ``qlocktwo`` – a German word-clock inspired by the QLOCKTWO grid, rounded
  to the nearest five minutes.

Only the QLOCKTWO face needs logic here. The grid is a fixed 11-column,
10-row letter matrix; given a local time we return the set of ``(row, col)``
cells that must be lit. The JavaScript side mirrors this contract so that
the minute tick can toggle classes without re-rendering the tile.

Stdlib-only so it works on the Pi. German umlauts are intentional.
"""
from __future__ import annotations

from typing import Iterable


VALID_WATCH_FACES: frozenset[str] = frozenset({"classic", "qlocktwo", "analog"})
DEFAULT_WATCH_FACE = "classic"


def analog_hand_angles(hour: int, minute: int) -> dict[str, float]:
    """Return the hour/minute hand rotations in degrees for the analog face.

    The hour hand advances continuously with the minute (``hour * 30`` plus
    ``minute * 0.5``) so that e.g. 7:30 sits exactly between 7 and 8. The
    minute hand is a simple ``minute * 6``. Degrees are modulo-360 floats so
    the frontend can ``setAttribute('transform', ...)`` without extra math.
    """
    hour_deg = ((hour % 12) * 30 + minute * 0.5) % 360
    minute_deg = (minute * 6) % 360
    return {"hour": hour_deg, "minute": minute_deg}


# 11 columns × 10 rows. Real umlauts, as required by the project conventions.
QLOCKTWO_GRID: tuple[str, ...] = (
    "ESKISTAFÜNF",
    "ZEHNZWANZIG",
    "DREIVIERTEL",
    "TGNACHVORJM",
    "HALBQZWÖLFP",
    "ZWEINSIEBEN",
    "KDREIRHFÜNF",
    "ELFNEUNVIER",
    "WACHTZEHNRS",
    "BSECHSFMUHR",
)

QLOCKTWO_ROWS = len(QLOCKTWO_GRID)
QLOCKTWO_COLS = len(QLOCKTWO_GRID[0])


# Word positions as ``(row, col, length)``. Reads from the grid above.
_ES = (0, 0, 2)
_IST = (0, 3, 3)
_FUENF_MIN = (0, 7, 4)      # FÜNF used for minutes ("fünf nach")
_ZEHN_MIN = (1, 0, 4)       # ZEHN used for minutes ("zehn nach")
_ZWANZIG_MIN = (1, 4, 7)
_VIERTEL = (2, 4, 7)
_NACH = (3, 2, 4)
_VOR = (3, 6, 3)
_HALB = (4, 0, 4)
_UHR = (9, 8, 3)

# Hour words. "EIN" rather than "EINS" because it is always followed by
# "UHR" or "HALB"/minute context where the short form is idiomatic.
_HOUR_WORDS: dict[int, tuple[int, int, int]] = {
    1: (5, 2, 3),      # EIN  (shares letters with ZWEI)
    2: (5, 0, 4),      # ZWEI
    3: (6, 1, 4),      # DREI
    4: (7, 7, 4),      # VIER
    5: (6, 7, 4),      # FÜNF (hour, distinct from minute-FÜNF in row 0)
    6: (9, 1, 5),      # SECHS
    7: (5, 5, 6),      # SIEBEN
    8: (8, 1, 4),      # ACHT
    9: (7, 3, 4),      # NEUN
    10: (8, 5, 4),     # ZEHN (hour, distinct from minute-ZEHN in row 1)
    11: (7, 0, 3),     # ELF
    12: (4, 5, 5),     # ZWÖLF
}


def normalize_watch_face(value: str | None) -> str:
    """Return a known face name or fall back to the default."""
    if isinstance(value, str) and value in VALID_WATCH_FACES:
        return value
    return DEFAULT_WATCH_FACE


def _expand(word: tuple[int, int, int]) -> Iterable[tuple[int, int]]:
    row, col, length = word
    for i in range(length):
        yield (row, col + i)


def _hour_12(hour_24: int) -> int:
    h = hour_24 % 12
    return 12 if h == 0 else h


def qlocktwo_active_cells(hour: int, minute: int) -> list[list[int]]:
    """Return the active ``[row, col]`` cells for the given local time.

    The minute is rounded down to the nearest five-minute block. After the
    half hour QLOCKTWO names the following hour (``halb acht`` = 7:30),
    which this helper handles via ``_hour_12(hour + 1)``.

    Returns a sorted list of ``[row, col]`` pairs — JSON-friendly so the
    initial state can be rendered server-side without any conversion.
    """
    block = (minute // 5) * 5
    this_hour = _hour_12(hour)
    next_hour = _hour_12(hour + 1)

    words: list[tuple[int, int, int]] = [_ES, _IST]
    if block == 0:
        words += [_HOUR_WORDS[this_hour], _UHR]
    elif block == 5:
        words += [_FUENF_MIN, _NACH, _HOUR_WORDS[this_hour]]
    elif block == 10:
        words += [_ZEHN_MIN, _NACH, _HOUR_WORDS[this_hour]]
    elif block == 15:
        words += [_VIERTEL, _NACH, _HOUR_WORDS[this_hour]]
    elif block == 20:
        words += [_ZWANZIG_MIN, _NACH, _HOUR_WORDS[this_hour]]
    elif block == 25:
        words += [_FUENF_MIN, _VOR, _HALB, _HOUR_WORDS[next_hour]]
    elif block == 30:
        words += [_HALB, _HOUR_WORDS[next_hour]]
    elif block == 35:
        words += [_FUENF_MIN, _NACH, _HALB, _HOUR_WORDS[next_hour]]
    elif block == 40:
        words += [_ZWANZIG_MIN, _VOR, _HOUR_WORDS[next_hour]]
    elif block == 45:
        words += [_VIERTEL, _VOR, _HOUR_WORDS[next_hour]]
    elif block == 50:
        words += [_ZEHN_MIN, _VOR, _HOUR_WORDS[next_hour]]
    elif block == 55:
        words += [_FUENF_MIN, _VOR, _HOUR_WORDS[next_hour]]

    cells: set[tuple[int, int]] = set()
    for word in words:
        cells.update(_expand(word))
    return [[row, col] for row, col in sorted(cells)]


def qlocktwo_phrase(hour: int, minute: int) -> str:
    """Human-readable phrase for the current time — useful for tests/a11y."""
    cells = {(r, c) for r, c in qlocktwo_active_cells(hour, minute)}
    words: list[str] = []
    for row_idx, row in enumerate(QLOCKTWO_GRID):
        current: list[str] = []
        for col_idx, letter in enumerate(row):
            if (row_idx, col_idx) in cells:
                current.append(letter)
            elif current:
                words.append("".join(current))
                current = []
        if current:
            words.append("".join(current))
    return " ".join(words)
