"""From the text of a PDF to a classified bill."""

from __future__ import annotations

from dataclasses import dataclass, field

from .extract import Found, best_template, extract_fields, is_gas_only, split_lines
from .fields import FIELDS, from_storable, to_storable
from .validate import has_errors, validate_fields

STATUS_OK = "ok"
STATUS_REVIEW = "needs_review"
STATUS_LEARN = "needs_learning"
STATUS_UNREADABLE = "unreadable"
STATUS_IGNORED = "ignored"


@dataclass
class Reading:
    """The outcome of reading one bill."""

    status: str
    template_id: str | None = None
    supplier: str | None = None
    values: dict[str, object] = field(default_factory=dict)
    lines: dict[str, int] = field(default_factory=dict)
    issues: list[dict] = field(default_factory=list)


def _run(template: dict, lines: list[str]) -> tuple[dict[str, object], dict[str, int]]:
    found: dict[str, Found] = extract_fields(template, lines)
    return (
        {key: item.value for key, item in found.items()},
        {key: item.line for key, item in found.items()},
    )


def read_bill(
    text: str,
    templates: list[dict],
    generic: dict,
    *,
    confirmed: dict[str, object] | None = None,
) -> Reading:
    """Classify a bill.

    A reading is trusted only once a person has vouched for it: either through
    values confirmed for this very bill, or because its template was learned
    from a bill they confirmed. Anything else is a proposal, however plausible
    it looks, because a wrong number here would silently skew every total.
    """
    typed = {
        key: from_storable(key, value)
        for key, value in (confirmed or {}).items()
        if key in FIELDS and value not in (None, "")
    }

    if not text.strip():
        issues = validate_fields(typed)
        if typed and not has_errors(issues):
            return Reading(STATUS_OK, values=typed, issues=issues)
        return Reading(
            STATUS_UNREADABLE,
            values=typed,
            issues=[{"level": "error", "code": "no_text"}, *issues],
        )
    if is_gas_only(text):
        return Reading(STATUS_IGNORED, issues=[{"level": "warning", "code": "gas_bill"}])

    lines = split_lines(text)
    template = best_template(templates, text)
    generic_values, generic_lines = _run(generic, lines)

    if template is None:
        values = {**generic_values, **typed}
        issues = validate_fields(values)
        trusted = bool(typed) and not has_errors(issues)
        return Reading(
            STATUS_OK if trusted else STATUS_LEARN,
            values=values,
            lines=generic_lines,
            issues=issues,
        )

    values, value_lines = _run(template, lines)
    own_issues = validate_fields({**values, **typed})
    if has_errors(own_issues):
        # The layout changed, or the template never fitted: offer the generic
        # reading for the gaps. The bill stays under review because of own_issues.
        for key, value in generic_values.items():
            if key not in values:
                values[key] = value
                value_lines[key] = generic_lines[key]
    values.update(typed)
    issues = validate_fields(values)
    trusted = (bool(template.get("learned")) or bool(typed)) and not has_errors(own_issues)
    return Reading(
        STATUS_OK if trusted and not has_errors(issues) else STATUS_REVIEW,
        template["id"],
        template.get("name"),
        values,
        value_lines,
        issues,
    )


def reading_to_store(reading: Reading) -> dict:
    """Serialize a reading."""
    return {
        "status": reading.status,
        "template_id": reading.template_id,
        "supplier": reading.supplier,
        "values": {key: to_storable(value) for key, value in reading.values.items()},
        "lines": reading.lines,
        "issues": reading.issues,
    }


def values_from_store(stored: dict[str, object]) -> dict[str, object]:
    """Rebuild typed values."""
    return {
        key: from_storable(key, value)
        for key, value in stored.items()
        if key in FIELDS and value is not None
    }
