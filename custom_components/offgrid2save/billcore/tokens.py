"""Find and parse Italian-formatted values inside a line of bill text."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
import re
import unicodedata

MONTHS = {
    "gennaio": 1, "gen": 1,
    "febbraio": 2, "feb": 2,
    "marzo": 3, "mar": 3,
    "aprile": 4, "apr": 4,
    "maggio": 5, "mag": 5,
    "giugno": 6, "giu": 6,
    "luglio": 7, "lug": 7,
    "agosto": 8, "ago": 8,
    "settembre": 9, "set": 9,
    "ottobre": 10, "ott": 10,
    "novembre": 11, "nov": 11,
    "dicembre": 12, "dic": 12,
}
_MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))

_NUMERIC_DATE = re.compile(r"(?<![\d/.\-])(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4}|\d{2})(?![\d/.\-])")
_LONG_DATE = re.compile(rf"(?<!\w)(\d{{1,2}})\s+({_MONTH_ALT})\.?\s+(\d{{4}})(?!\d)", re.I)
_MONTH_YEAR = re.compile(rf"(?<!\w)({_MONTH_ALT})\.?\s+(\d{{4}})(?!\d)", re.I)

# Comma is always the decimal mark on Italian bills, a dot followed by three
# digits is a thousands separator. A dot with other decimals is tolerated
# because some suppliers export machine-formatted totals.
_NUMBER = re.compile(
    r"(?<![\w.,/])"
    r"(-\s*)?"
    r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+,\d+|\d+\.\d{1,2}(?!\d)|\d+)"
    r"(-(?=\s|$))?"
    r"(?![\w/]|[.,]\d)"
)
_KWH_AFTER = re.compile(r"\s*kwh\b", re.I)


@dataclass(frozen=True)
class Token:
    """A value found on a line, with its character span."""

    value: object
    start: int
    end: int


def normalize(text: str) -> str:
    """Lowercase, strip accents and unify typographic punctuation."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("’", "'").replace("`", "'")
    return text.lower()


def parse_number(raw: str) -> float | None:
    """Parse a number written with Italian separators."""
    cleaned = raw.strip().replace("€", "").replace(" ", "")
    negative = cleaned.startswith("-") or cleaned.endswith("-")
    cleaned = cleaned.strip("-")
    if not cleaned:
        return None
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", cleaned):
        cleaned = cleaned.replace(".", "")
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return -number if negative else number


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _month_bound(year: int, month: int, *, end_of_month: bool) -> date:
    day = calendar.monthrange(year, month)[1] if end_of_month else 1
    return date(year, month, day)


def find_dates(line: str, *, end_of_month: bool = False) -> list[Token]:
    """Return dates on a line.

    A bare "marzo 2026" resolves to the first or last day of the month, which
    is what a billing period written in months means.
    """
    found: list[Token] = []
    taken: list[tuple[int, int]] = []

    def free(start: int, end: int) -> bool:
        return all(end <= a or start >= b for a, b in taken)

    for match in _NUMERIC_DATE.finditer(line):
        day, month, year = (int(g) for g in match.groups())
        if year < 100:
            year += 2000
        parsed = _safe_date(year, month, day)
        if parsed:
            found.append(Token(parsed, match.start(), match.end()))
            taken.append(match.span())
    for match in _LONG_DATE.finditer(line):
        if not free(*match.span()):
            continue
        parsed = _safe_date(
            int(match.group(3)), MONTHS[match.group(2).lower()], int(match.group(1))
        )
        if parsed:
            found.append(Token(parsed, match.start(), match.end()))
            taken.append(match.span())
    for match in _MONTH_YEAR.finditer(line):
        if not free(*match.span()):
            continue
        parsed = _month_bound(
            int(match.group(2)), MONTHS[match.group(1).lower()], end_of_month=end_of_month
        )
        found.append(Token(parsed, match.start(), match.end()))
    return sorted(found, key=lambda token: token.start)


def _masked(line: str) -> str:
    """Blank out dates so their digits are not read as numbers."""
    chars = list(line)
    for token in find_dates(line):
        chars[token.start : token.end] = " " * (token.end - token.start)
    return "".join(chars)


def find_numbers(line: str) -> list[Token]:
    """Return every standalone number on a line, ignoring dates and codes."""
    tokens: list[Token] = []
    for match in _NUMBER.finditer(_masked(line)):
        number = parse_number(match.group(0))
        if number is not None:
            tokens.append(Token(number, match.start(), match.end()))
    return tokens


def find_amounts(line: str) -> list[Token]:
    """Return money amounts: numbers with two decimals, or marked with a euro sign."""
    tokens: list[Token] = []
    for token in find_numbers(line):
        raw = line[token.start : token.end]
        before = line[max(0, token.start - 3) : token.start]
        after = line[token.end : token.end + 3]
        two_decimals = bool(re.search(r"[.,]\d{2}-?$", raw))
        has_euro = "€" in before or "€" in after or "euro" in normalize(line[token.end : token.end + 6])
        if two_decimals or has_euro:
            tokens.append(token)
    return tokens


def find_kwh(line: str) -> list[Token]:
    """Return energy values, preferring those explicitly followed by kWh."""
    tokens = find_numbers(line)
    marked = [t for t in tokens if _KWH_AFTER.match(line, t.end)]
    return marked or tokens


_CODE = re.compile(r"(?<![\w/\-])(?=[A-Z0-9/\-]*\d)[A-Z0-9][A-Z0-9/\-]{3,}(?![\w/\-])")


def find_codes(line: str) -> list[Token]:
    """Return document-number style codes."""
    return [Token(m.group(0), m.start(), m.end()) for m in _CODE.finditer(_masked(line))]
