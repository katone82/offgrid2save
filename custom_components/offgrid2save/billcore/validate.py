"""Consistency checks that tell a correct reading from a wrong one."""

from __future__ import annotations

from datetime import date

from .fields import REQUIRED_FIELDS

ERROR = "error"
WARNING = "warning"
SUM_TOLERANCE_EUR = 1.0
KWH_TOLERANCE = 1.5
MAX_PERIOD_DAYS = 400
MIN_UNIT_PRICE = 0.05
MAX_UNIT_PRICE = 2.0
_PARTS = (
    "cost_energy",
    "cost_transport",
    "cost_system",
    "cost_recalc",
    "cost_other",
    "cost_bonus",
    "cost_taxes",
    "cost_tv",
)


def _issue(level: str, code: str, **detail: object) -> dict:
    return {"level": level, "code": code, **detail}


def validate_fields(values: dict[str, object]) -> list[dict]:
    """Return problems found in a set of bill values.

    Errors mean the bill cannot enter the calculations until reviewed, warnings
    are shown but do not block it.
    """
    issues: list[dict] = [
        _issue(ERROR, "missing_field", field=key)
        for key in REQUIRED_FIELDS
        if values.get(key) is None
    ]

    start, end = values.get("period_start"), values.get("period_end")
    if isinstance(start, date) and isinstance(end, date):
        if end < start:
            issues.append(_issue(ERROR, "period_reversed"))
        elif (end - start).days > MAX_PERIOD_DAYS:
            issues.append(_issue(ERROR, "period_too_long", days=(end - start).days))

    kwh = values.get("consumption_kwh")
    total = values.get("total_cost")
    if isinstance(kwh, float) and kwh < 0:
        issues.append(_issue(ERROR, "negative_consumption"))

    bands = [values.get(f"consumption_f{i}") for i in (1, 2, 3)]
    if isinstance(kwh, float) and all(isinstance(band, float) for band in bands):
        band_sum = sum(bands)
        if abs(band_sum - kwh) > KWH_TOLERANCE:
            issues.append(
                _issue(WARNING, "bands_mismatch", bands=round(band_sum, 2), billed=kwh)
            )

    parts = [values[key] for key in _PARTS if isinstance(values.get(key), float)]
    if isinstance(total, float) and len(parts) >= 3:
        # Only worth comparing when the main voices are all there: a partial
        # sum falling short of the total proves nothing.
        complete = all(
            isinstance(values.get(key), float)
            for key in ("cost_energy", "cost_transport", "cost_system", "cost_taxes")
        )
        difference = abs(sum(parts) - total)
        if complete and difference > SUM_TOLERANCE_EUR:
            issues.append(
                _issue(WARNING, "parts_mismatch", parts=round(sum(parts), 2), total=total)
            )

    if isinstance(kwh, float) and kwh > 0 and isinstance(total, float) and total > 0:
        unit = (total - float(values.get("cost_tv") or 0.0)) / kwh
        # A tiny billed consumption legitimately gives a huge average price,
        # because fixed charges dominate: only flag it above a real consumption.
        if unit < MIN_UNIT_PRICE or (unit > MAX_UNIT_PRICE and kwh >= 50):
            issues.append(_issue(WARNING, "implausible_unit_price", unit=round(unit, 3)))

    return issues


def has_errors(issues: list[dict]) -> bool:
    """Tell whether any issue blocks the bill."""
    return any(issue["level"] == ERROR for issue in issues)
