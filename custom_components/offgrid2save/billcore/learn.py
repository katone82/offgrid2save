"""Derive template rules from values a person confirmed on a real bill."""

from __future__ import annotations

from datetime import datetime, timezone
import re

from .extract import apply_rule, label_regex, match_score, split_lines, tokens_for
from .fields import FIELDS, from_storable
from .tokens import normalize

MAX_RULES_PER_FIELD = 5
MAX_LABEL_WORDS = 5
_WORD = re.compile(r"[^\W_]+")
_BAND = re.compile(r"f[123]")
_NOISE = {"euro", "eur", "kwh", "kw", "dal", "del", "al", "di", "da", "n", "nr", "the"}

# Words that make a label likely to be the real one, per field. They only rank
# candidates: a rule is still accepted only if it reproduces the confirmed value.
FIELD_HINTS: dict[str, tuple[str, ...]] = {
    "period_start": ("periodo", "fatturazione", "riferimento", "dal"),
    "period_end": ("periodo", "fatturazione", "riferimento", "al"),
    "total_cost": ("totale", "pagare", "importo"),
    "consumption_kwh": ("consumo", "consumi", "fatturato", "periodo", "energia"),
    "bill_number": ("bolletta", "fattura", "numero", "documento"),
    "issue_date": ("emissione", "emessa", "data", "fattura", "bolletta"),
    "consumption_f1": ("f1",),
    "consumption_f2": ("f2",),
    "consumption_f3": ("f3",),
    "cost_energy": ("materia", "energia", "vendita"),
    "cost_transport": ("trasporto", "contatore", "gestione"),
    "cost_system": ("oneri", "sistema"),
    "cost_variable": ("variabili", "variabile", "consumi"),
    "cost_fixed": ("fissi", "fissa", "fisso"),
    "cost_recalc": ("ricalcoli", "ricalcolo", "conguaglio"),
    "cost_other": ("altre", "partite"),
    "cost_bonus": ("bonus", "sociale"),
    "cost_taxes": ("imposte", "iva", "accise"),
    "cost_tv": ("canone", "tv", "televisione", "rai"),
}


def values_equal(field_key: str, left: object, right: object) -> bool:
    """Compare two values of a field, tolerating rounding on numbers."""
    if left is None or right is None:
        return False
    kind = FIELDS[field_key].kind
    if kind in ("amount", "kwh"):
        return abs(float(left) - float(right)) < 0.006
    if kind == "code":
        return str(left).strip().upper() == str(right).strip().upper()
    return left == right


def _word_runs(fragment: str) -> list[list[str]]:
    """Split text into runs of consecutive words, broken by anything holding a digit.

    A label has to be contiguous to be found again, so every printed word stays,
    however short: dropping the "e" of "Imposte e IVA" gives a label that matches
    nothing. Values and codes end a run: in "dal 01/05/2026 al" the words "dal" and
    "al" are separate, and the second date is reached as an occurrence after "dal".
    """
    runs: list[list[str]] = [[]]
    for raw in normalize(fragment).split():
        if any(char.isdigit() for char in raw) and not _BAND.fullmatch(raw.strip(":.,")):
            runs.append([])
        else:
            runs[-1].extend(_WORD.findall(raw))
    return [run for run in runs if run]


def _trim(run: list[str], *, from_end: bool) -> list[str]:
    """Keep the words next to the value, without a dangling connective at the far side."""
    picked = run[-MAX_LABEL_WORDS:] if from_end else run[:MAX_LABEL_WORDS]
    while len(picked) > 1 and (picked[0] if from_end else picked[-1]) in _NOISE:
        picked = picked[1:] if from_end else picked[:-1]
    return picked


def _is_usable(words: list[str]) -> bool:
    return any(
        _BAND.fullmatch(word) or (len(word) >= 3 and word not in _NOISE) for word in words
    )


def _candidates(field_key: str, value: object, lines: list[str]) -> list[dict]:
    candidates: list[dict] = []

    def add(run: list[str], *, from_end: bool, **rule: object) -> None:
        words = _trim(run, from_end=from_end)
        if _is_usable(words):
            candidates.append({"label": " ".join(words), **rule})

    for index, line in enumerate(lines):
        for token in tokens_for(field_key, line):
            if not values_equal(field_key, token.value, value):
                continue
            for run in _word_runs(line[: token.start]):
                add(run, from_end=True, where="after")
            for run in _word_runs(line[token.end :]):
                add(run, from_end=False, where="before")
            for above in range(index - 1, max(index - 4, -1), -1):
                header = _word_runs(lines[above][max(0, token.start - 12) : token.end + 12])
                if not header or not _is_usable(_trim(header[-1], from_end=True)):
                    continue
                add(header[-1], from_end=True, where="below")
                add(header[-1], from_end=True, where="after", lookahead=index - above)
                break
    return candidates


def _with_occurrence(field_key: str, rule: dict, value: object, lines: list[str]) -> dict | None:
    """Find the occurrence and label repetition that yield the confirmed value."""
    matches = sum(1 for line in lines if label_regex(rule["label"]).search(normalize(line)))
    for skip in range(min(matches, 6)):
        for occurrence in range(6):
            attempt = dict(rule, occurrence=occurrence)
            if skip:
                attempt["skip_matches"] = skip
            found = apply_rule(field_key, attempt, lines)
            if found and values_equal(field_key, found.value, value):
                return attempt
    return None


def _score(field_key: str, rule: dict, lines: list[str]) -> tuple:
    words = rule["label"].split()
    hints = sum(word in FIELD_HINTS.get(field_key, ()) for word in words)
    repeats = sum(1 for line in lines if label_regex(rule["label"]).search(normalize(line)))
    plain = rule.get("where") == "after" and "lookahead" not in rule
    return (
        hints,
        -int(rule.get("skip_matches", 0)),
        -int(rule.get("occurrence", 0)),
        plain,
        -repeats,
        len(words),
    )


def learn_rule(field_key: str, value: object, lines: list[str]) -> dict | None:
    """Return the best rule locating a confirmed value, or None if it is not in the text."""
    best: dict | None = None
    best_score: tuple | None = None
    seen: set[str] = set()
    for candidate in _candidates(field_key, value, lines):
        key = f"{candidate['where']}|{candidate['label']}|{candidate.get('lookahead')}"
        if key in seen:
            continue
        seen.add(key)
        rule = _with_occurrence(field_key, candidate, value, lines)
        if rule is None:
            continue
        score = _score(field_key, rule, lines)
        if best_score is None or score > best_score:
            best, best_score = rule, score
    return best


def slug(name: str) -> str:
    """Turn a supplier name into a template id."""
    return re.sub(r"[^a-z0-9]+", "_", normalize(name)).strip("_") or "fornitore"


def add_builtin_rules(learned: dict, builtin: dict) -> dict:
    """Give a learned template the rules of its built-in version it does not have.

    They go last, so what was learned from the user's bills keeps priority, while an
    update that improves the built-in template still reaches them.
    """
    fields = {key: list(rules) for key, rules in learned.get("fields", {}).items()}
    for key, rules in builtin.get("fields", {}).items():
        known = fields.setdefault(key, [])
        known.extend(rule for rule in rules if rule not in known)
    return {**learned, "fields": fields}


def learn_template(
    supplier: str,
    confirmed: dict[str, object],
    text: str,
    *,
    base: dict | None = None,
    now: datetime | None = None,
) -> tuple[dict, list[str]]:
    """Add rules for confirmed values to a template.

    Earlier rules stay in the list after the new one, so bills in an older
    layout from the same supplier keep working. Returns the template and the
    fields whose value could not be located in the text.
    """
    lines = split_lines(text)
    template: dict = {
        "id": (base or {}).get("id") or slug(supplier),
        "name": (base or {}).get("name") or supplier,
        "version": 1,
        "learned": True,
        "match": (base or {}).get("match") or {"any": [normalize(supplier)]},
        "fields": {key: list(rules) for key, rules in (base or {}).get("fields", {}).items()},
    }
    if not match_score(template, text):
        template["match"] = {"any": _fingerprint_from_text(lines)}

    unlocated: list[str] = []
    for key, raw in confirmed.items():
        if key not in FIELDS or raw in (None, ""):
            continue
        value = from_storable(key, raw)
        existing = template["fields"].get(key, [])
        # Rules run in order and the first that finds something wins, so that
        # is the one to check: a correct rule further down would never be reached.
        current = next(
            (found for rule in existing if (found := apply_rule(key, rule, lines))), None
        )
        if current and values_equal(key, current.value, value):
            continue
        # A known rule that gives the right value beats a new one. A rule invented from
        # one bill can fit it by chance, as a number in a chart can match a time band,
        # and then read nonsense on every other bill.
        rule = next(
            (
                item
                for item in existing
                if (found := apply_rule(key, item, lines))
                and values_equal(key, found.value, value)
            ),
            None,
        ) or learn_rule(key, value, lines)
        if rule is None:
            unlocated.append(key)
            continue
        kept = [item for item in existing if item != rule]
        template["fields"][key] = [rule, *kept][:MAX_RULES_PER_FIELD]

    template["learned_at"] = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    return template, unlocated


_DOMAIN = re.compile(r"\b[a-z0-9\-]{3,}\.(?:it|com|eu)\b")
# The customer's own address can appear on the bill: it must not identify the
# supplier, and it must not end up in a template someone may share.
_PERSONAL_DOMAINS = {
    "gmail.com", "hotmail.com", "hotmail.it", "outlook.com", "outlook.it", "yahoo.com",
    "yahoo.it", "libero.it", "virgilio.it", "tiscali.it", "alice.it", "tim.it",
    "icloud.com", "live.it", "live.com", "fastwebnet.it", "pec.it",
}


def _fingerprint_from_text(lines: list[str]) -> list[str]:
    """Pick public strings that identify the sender: its web domain."""
    domains: list[str] = []
    for line in lines:
        for domain in _DOMAIN.findall(normalize(line)):
            if domain not in domains and domain not in _PERSONAL_DOMAINS:
                domains.append(domain)
    return domains[:3]
