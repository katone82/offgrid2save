"""Apply a supplier template to the text of a bill.

A rule locates a value relative to a printed label:

    {"label": "totale da pagare", "where": "after", "occurrence": 0}

``where`` is one of:
    after   the value follows the label on the same line, or on the next
            ``lookahead`` lines if that line holds no value
    before  the value precedes the label on the same line
    below   the label is a column header, the value sits under it
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import re
import unicodedata

from .fields import FIELDS
from .tokens import Token, find_amounts, find_codes, find_dates, find_kwh, normalize

DEFAULT_LOOKAHEAD = 2
COLUMN_TOLERANCE = 24


@dataclass(frozen=True)
class Found:
    """A field value and where it came from."""

    value: object
    line: int
    rule: dict


def split_lines(text: str) -> list[str]:
    """Split extracted text into non-empty lines.

    NFKC expands ligatures such as the "fi" in "costi fissi" up front. Later
    steps compare positions between a line and its normalized form, which only
    works if normalizing keeps every character at its place.
    """
    lines = unicodedata.normalize("NFKC", text).splitlines()
    return [line.rstrip() for line in lines if line.strip()]


def label_regex(label: str) -> re.Pattern[str]:
    """Compile a label, tolerating the spacing noise PDF extraction produces.

    Text extraction both inserts extra spaces between words and glues words
    together, and suppliers punctuate labels differently ("Competenza: dal"),
    so anything that is not a letter or digit may separate the words.
    """
    parts = [re.escape(word) for word in normalize(label).split()]
    return re.compile(r"\W*".join(parts))


def tokens_for(field_key: str, line: str) -> list[Token]:
    """Return the tokens of the right kind for a field."""
    kind = FIELDS[field_key].kind
    if kind == "amount":
        return find_amounts(line)
    if kind == "kwh":
        return find_kwh(line)
    if kind == "date":
        return find_dates(line, end_of_month=field_key == "period_end")
    return find_codes(line)


def _pick(tokens: list[Token], occurrence: int) -> Token | None:
    """Return a token by position. Negative counts from the end, as for a row's total."""
    return tokens[occurrence] if -len(tokens) <= occurrence < len(tokens) else None


def apply_rule(field_key: str, rule: dict, lines: list[str]) -> Found | None:
    """Return the value a rule finds, or None."""
    pattern = label_regex(rule["label"])
    where = rule.get("where", "after")
    occurrence = int(rule.get("occurrence", 0))
    lookahead = int(rule.get("lookahead", DEFAULT_LOOKAHEAD))
    skip = int(rule.get("skip_matches", 0))

    seen = 0
    for index, line in enumerate(lines):
        match = pattern.search(normalize(line))
        if not match:
            continue
        if seen < skip:
            seen += 1
            continue

        if where == "before":
            tokens = [t for t in tokens_for(field_key, line) if t.end <= match.start()]
            token = _pick(list(reversed(tokens)), occurrence)
            if token:
                return Found(token.value, index, rule)
            continue

        if where == "below":
            center = (match.start() + match.end()) / 2
            for below in range(index + 1, min(index + 1 + max(lookahead, 3), len(lines))):
                nearby = [
                    t
                    for t in tokens_for(field_key, lines[below])
                    if abs((t.start + t.end) / 2 - center) <= COLUMN_TOLERANCE
                ]
                if nearby:
                    best = min(nearby, key=lambda t: abs((t.start + t.end) / 2 - center))
                    return Found(best.value, below, rule)
            continue

        tokens = [t for t in tokens_for(field_key, line) if t.start >= match.end()]
        token = _pick(tokens, occurrence)
        if token:
            return Found(token.value, index, rule)
        for below in range(index + 1, min(index + 1 + lookahead, len(lines))):
            token = _pick(tokens_for(field_key, lines[below]), occurrence)
            if token:
                return Found(token.value, below, rule)
    return None


def extract_fields(
    template: dict,
    lines: list[str],
    *,
    accept: Callable[[str, Found], bool] | None = None,
) -> dict[str, Found]:
    """Run every rule of a template, the first that finds a value wins."""
    results: dict[str, Found] = {}
    for key, rules in template.get("fields", {}).items():
        if key not in FIELDS:
            continue
        for rule in rules:
            found = apply_rule(key, rule, lines)
            if found and (accept is None or accept(key, found)):
                results[key] = found
                break
    return results


def _contains(needle: str, text: str) -> bool:
    return label_regex(needle).search(text) is not None


def match_score(template: dict, text: str) -> int:
    """Score how well a template's fingerprint fits a document, 0 means no match."""
    match = template.get("match") or {}
    normalized = normalize(text)
    if any(_contains(item, normalized) for item in match.get("none", [])):
        return 0
    required = match.get("all", [])
    if not all(_contains(item, normalized) for item in required):
        return 0
    hits = sum(_contains(item, normalized) for item in match.get("any", []))
    if match.get("any") and not hits:
        return 0
    return hits + len(required)


def best_template(templates: Iterable[dict], text: str) -> dict | None:
    """Pick the template that fits best, learned templates win ties."""
    best: dict | None = None
    best_rank = (0, False)
    for template in templates:
        score = match_score(template, text)
        if not score:
            continue
        rank = (score, bool(template.get("learned")))
        if rank > best_rank:
            best, best_rank = template, rank
    return best


_GAS_HINTS = re.compile(r"\bsmc\b|\bpdr\b|gas naturale")
_POWER_HINTS = re.compile(r"\bkwh\b|\bpod\b")


def is_gas_only(text: str) -> bool:
    """Detect gas bills, whose consumption has no meaning for this comparison."""
    normalized = normalize(text)
    return bool(_GAS_HINTS.search(normalized)) and not _POWER_HINTS.search(normalized)
