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


VALID_WATCH_FACES: frozenset[str] = frozenset(
    {"flip", "lcd", "pulse", "qlocktwo", "qlocktwo-ooe", "analog"}
)
DEFAULT_WATCH_FACE = "flip"


# Seven-segment mapping for the LCD face. Keys are digit characters, values
# are the set of segments (a..g) that must be lit. Layout:
#
#      aaa
#     f   b
#     f   b
#      ggg
#     e   c
#     e   c
#      ddd
#
# Kept as frozensets so the mapping is hashable and cheap to pass around.
LCD_SEGMENT_MAP: dict[str, frozenset[str]] = {
    "0": frozenset("abcdef"),
    "1": frozenset("bc"),
    "2": frozenset("abdeg"),
    "3": frozenset("abcdg"),
    "4": frozenset("bcfg"),
    "5": frozenset("acdfg"),
    "6": frozenset("acdefg"),
    "7": frozenset("abc"),
    "8": frozenset("abcdefg"),
    "9": frozenset("abcdfg"),
}


def lcd_segments_for(digit: str) -> frozenset[str]:
    """Return the active segments for a single digit character."""
    return LCD_SEGMENT_MAP.get(digit, frozenset())


def analog_hand_angles(hour: int, minute: int, second: int = 0) -> dict[str, float]:
    """Return the hour/minute/second hand rotations in degrees.

    The hour hand advances continuously with the minute (``hour * 30`` plus
    ``minute * 0.5``) so that e.g. 7:30 sits exactly between 7 and 8. The
    minute hand is a simple ``minute * 6``, and the second hand ``second *
    6``. Degrees are modulo-360 floats so the frontend can
    ``setAttribute('transform', ...)`` without extra math. ``second``
    defaults to ``0`` so the server-rendered initial frame stays stable
    across a render even if the wall clock advances mid-response.
    """
    hour_deg = ((hour % 12) * 30 + minute * 0.5) % 360
    minute_deg = (minute * 6) % 360
    second_deg = (second * 6) % 360
    return {"hour": hour_deg, "minute": minute_deg, "second": second_deg}


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

# Hour words. For hour 1 we carry two variants: the short "EIN" used only
# in the literal "EIN UHR" phrase at the full hour, and the long "EINS"
# used everywhere else ("halb eins", "viertel vor eins"). German grammar —
# not a stylistic choice.
_EIN = (5, 2, 3)      # EIN  (shares letters with ZWEI / SIEBEN row)
_EINS = (5, 2, 4)     # EINS (extends EIN into the first letter of SIEBEN)
_HOUR_WORDS: dict[int, tuple[int, int, int]] = {
    1: _EINS,          # default form; overridden to _EIN when paired with UHR
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


def _hour_word(hour_12: int, with_uhr: bool) -> tuple[int, int, int]:
    if hour_12 == 1 and with_uhr:
        return _EIN
    return _HOUR_WORDS[hour_12]


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
        words += [_hour_word(this_hour, with_uhr=True), _UHR]
    elif block == 5:
        words += [_FUENF_MIN, _NACH, _hour_word(this_hour, with_uhr=False)]
    elif block == 10:
        words += [_ZEHN_MIN, _NACH, _hour_word(this_hour, with_uhr=False)]
    elif block == 15:
        words += [_VIERTEL, _NACH, _hour_word(this_hour, with_uhr=False)]
    elif block == 20:
        words += [_ZWANZIG_MIN, _NACH, _hour_word(this_hour, with_uhr=False)]
    elif block == 25:
        words += [_FUENF_MIN, _VOR, _HALB, _hour_word(next_hour, with_uhr=False)]
    elif block == 30:
        words += [_HALB, _hour_word(next_hour, with_uhr=False)]
    elif block == 35:
        words += [_FUENF_MIN, _NACH, _HALB, _hour_word(next_hour, with_uhr=False)]
    elif block == 40:
        words += [_ZWANZIG_MIN, _VOR, _hour_word(next_hour, with_uhr=False)]
    elif block == 45:
        words += [_VIERTEL, _VOR, _hour_word(next_hour, with_uhr=False)]
    elif block == 50:
        words += [_ZEHN_MIN, _VOR, _hour_word(next_hour, with_uhr=False)]
    elif block == 55:
        words += [_FUENF_MIN, _VOR, _hour_word(next_hour, with_uhr=False)]

    cells: set[tuple[int, int]] = set()
    for word in words:
        cells.update(_expand(word))
    return [[row, col] for row, col in sorted(cells)]


def qlocktwo_phrase(hour: int, minute: int) -> str:
    """Human-readable phrase for the current time — useful for tests/a11y."""
    return _phrase_from_grid(
        QLOCKTWO_GRID, qlocktwo_active_cells(hour, minute)
    )


# ---------------------------------------------------------------------------
# Oberösterreich dialect variant.
#
# Same 10×11 layout as the High-German grid so the CSS geometry can be shared.
# Vocabulary: ES IS / FÜMF / ZEHN / VIERTL / ZWANZG / NOCH / VOR / HOIBE, plus
# dialect hour names (OANS, ZWA, DREI, VIA, FÜMF, SECHSE, SIEMA, OCHT, NEIN,
# ZEHNE, ELFE, ZWÖFE). No UHR — in OÖ it's essentially never spoken at the
# full hour, so the grid skips it and so does the phrasing logic.
QLOCKTWO_OOE_GRID: tuple[str, ...] = (
    "ESKISTAFÜMF",
    "ZEHNAZWANZG",
    "DREIVIERTLE",
    "TGNOCHSVORM",
    "HOIBEZWÖFEN",
    "DREIKNEINEP",
    "SIEBNEKFÜMF",
    "OANSZWOAELF",
    "WOCHTZEHNER",
    "SECHSEVIERE",
)

QLOCKTWO_OOE_ROWS = len(QLOCKTWO_OOE_GRID)
QLOCKTWO_OOE_COLS = len(QLOCKTWO_OOE_GRID[0])


# Prefix / connector words.
_OOE_ES = (0, 0, 2)
_OOE_IS = (0, 3, 2)
_OOE_FUEMF_MIN = (0, 7, 4)
_OOE_ZEHN_MIN = (1, 0, 4)
_OOE_ZWANZG_MIN = (1, 5, 6)
_OOE_VIERTL = (2, 4, 6)
_OOE_NOCH = (3, 2, 4)
_OOE_VOR = (3, 7, 3)
_OOE_HOIBE = (4, 0, 5)

# Hour words. Unlike the Hochdeutsch grid there is no EIN/EINS split — OANS
# is always 4 letters because we drop UHR entirely ("es is oans"). DREI sits
# on row 5 (not row 2), otherwise "DREI" + "VIERTL" at 3:15 would run into
# the visually misleading "DREIVIERTL" on a single row. NEINE (not NEIN) is
# the dialect spelling; it shares row 5 with DREI to free row 7 for the
# OANS/ZWOA/ELF trio.
_OOE_HOUR_WORDS: dict[int, tuple[int, int, int]] = {
    1: (7, 0, 4),      # OANS
    2: (7, 4, 4),      # ZWOA
    3: (5, 0, 4),      # DREI
    4: (9, 6, 5),      # VIERE
    5: (6, 7, 4),      # FÜMF (hour)
    6: (9, 0, 6),      # SECHSE
    7: (6, 0, 6),      # SIEBNE
    8: (8, 1, 4),      # OCHT
    9: (5, 5, 5),      # NEINE
    10: (8, 5, 5),     # ZEHNE
    11: (7, 8, 3),     # ELF
    12: (4, 5, 5),     # ZWÖFE
}


def qlocktwo_ooe_active_cells(hour: int, minute: int) -> list[list[int]]:
    """OÖ dialect variant of :func:`qlocktwo_active_cells`.

    Same five-minute rounding and hour-rollover-after-30 rules, but with
    dialect vocabulary and without UHR. At the full hour the phrase reads
    "ES IS <hour>" (e.g. 13:00 → "ES IS OANS").
    """
    block = (minute // 5) * 5
    this_hour = _hour_12(hour)
    next_hour = _hour_12(hour + 1)

    words: list[tuple[int, int, int]] = [_OOE_ES, _OOE_IS]
    if block == 0:
        words += [_OOE_HOUR_WORDS[this_hour]]
    elif block == 5:
        words += [_OOE_FUEMF_MIN, _OOE_NOCH, _OOE_HOUR_WORDS[this_hour]]
    elif block == 10:
        words += [_OOE_ZEHN_MIN, _OOE_NOCH, _OOE_HOUR_WORDS[this_hour]]
    elif block == 15:
        words += [_OOE_VIERTL, _OOE_NOCH, _OOE_HOUR_WORDS[this_hour]]
    elif block == 20:
        words += [_OOE_ZWANZG_MIN, _OOE_NOCH, _OOE_HOUR_WORDS[this_hour]]
    elif block == 25:
        words += [_OOE_FUEMF_MIN, _OOE_VOR, _OOE_HOIBE, _OOE_HOUR_WORDS[next_hour]]
    elif block == 30:
        words += [_OOE_HOIBE, _OOE_HOUR_WORDS[next_hour]]
    elif block == 35:
        words += [_OOE_FUEMF_MIN, _OOE_NOCH, _OOE_HOIBE, _OOE_HOUR_WORDS[next_hour]]
    elif block == 40:
        words += [_OOE_ZWANZG_MIN, _OOE_VOR, _OOE_HOUR_WORDS[next_hour]]
    elif block == 45:
        words += [_OOE_VIERTL, _OOE_VOR, _OOE_HOUR_WORDS[next_hour]]
    elif block == 50:
        words += [_OOE_ZEHN_MIN, _OOE_VOR, _OOE_HOUR_WORDS[next_hour]]
    elif block == 55:
        words += [_OOE_FUEMF_MIN, _OOE_VOR, _OOE_HOUR_WORDS[next_hour]]

    cells: set[tuple[int, int]] = set()
    for word in words:
        cells.update(_expand(word))
    return [[row, col] for row, col in sorted(cells)]


def qlocktwo_ooe_phrase(hour: int, minute: int) -> str:
    """Human-readable dialect phrase — useful for tests."""
    return _phrase_from_grid(
        QLOCKTWO_OOE_GRID, qlocktwo_ooe_active_cells(hour, minute)
    )


def _phrase_from_grid(
    grid: tuple[str, ...], cells: list[list[int]]
) -> str:
    active = {(r, c) for r, c in cells}
    words: list[str] = []
    for row_idx, row in enumerate(grid):
        current: list[str] = []
        for col_idx, letter in enumerate(row):
            if (row_idx, col_idx) in active:
                current.append(letter)
            elif current:
                words.append("".join(current))
                current = []
        if current:
            words.append("".join(current))
    return " ".join(words)
