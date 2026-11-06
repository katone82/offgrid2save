"""The values a bill can provide."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class FieldDef:
    """Definition of an extractable bill field."""

    key: str
    kind: str  # amount | kwh | date | code
    required: bool = False


FIELDS: dict[str, FieldDef] = {
    field.key: field
    for field in (
        FieldDef("period_start", "date", required=True),
        FieldDef("period_end", "date", required=True),
        FieldDef("total_cost", "amount", required=True),
        FieldDef("consumption_kwh", "kwh", required=True),
        FieldDef("bill_number", "code"),
        FieldDef("issue_date", "date"),
        FieldDef("consumption_f1", "kwh"),
        FieldDef("consumption_f2", "kwh"),
        FieldDef("consumption_f3", "kwh"),
        FieldDef("cost_energy", "amount"),
        FieldDef("cost_transport", "amount"),
        FieldDef("cost_system", "amount"),
        FieldDef("cost_variable", "amount"),
        FieldDef("cost_fixed", "amount"),
        FieldDef("cost_recalc", "amount"),
        FieldDef("cost_other", "amount"),
        FieldDef("cost_bonus", "amount"),
        FieldDef("cost_taxes", "amount"),
        FieldDef("cost_tv", "amount"),
    )
}

REQUIRED_FIELDS = tuple(key for key, field in FIELDS.items() if field.required)


def to_storable(value: object) -> object:
    """Turn a field value into something JSON can hold."""
    return value.isoformat() if isinstance(value, date) else value


def from_storable(key: str, value: object) -> object:
    """Rebuild a field value from its stored form."""
    if value is None:
        return None
    kind = FIELDS[key].kind
    if kind == "date":
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    if kind in ("amount", "kwh"):
        return float(value)
    return str(value)
