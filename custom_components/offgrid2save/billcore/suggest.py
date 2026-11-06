"""Recognize Victron GX energy counters among the entities of an installation.

Only a starting point for the configuration form: every role stays editable, and
any energy sensor from any brand can fill it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import re

from .savings import LAYOUT_SEPARATE, LAYOUT_THROUGH_PLANT

ROLE_PATTERNS: dict[str, tuple[str, ...]] = {
    "pv": (r"_total_yield$",),
    "grid_import": (
        r"_energy_from_ac_?in_?1_to_ac_?out$",
        r"_energy_from_ac_?in_?1_to_inverter$",
    ),
    "grid_export": (
        r"_energy_from_ac_?out_to_ac_?in_?1$",
        r"_energy_from_inverter_to_ac_?in_?1$",
    ),
    "consumption_add": (
        r"_energy_from_ac_?in_?1_to_ac_?out$",
        r"_energy_from_inverter_to_ac_?out$",
    ),
    "consumption_subtract": (
        r"_energy_from_ac_?out_to_ac_?in_?1$",
        r"_energy_from_(?:ac_?)?out_to_inverter$",
    ),
    "battery_charge": (r"_dc_battery_charge_energy$",),
    "battery_discharge": (r"_dc_battery_discharge_energy$",),
}
_PV_FALLBACK = re.compile(r"(?:^|\.)gx_device_pv_energy$")
_AC_INPUT_SOURCE = re.compile(r"^select\..*_ac_input_\d_source_type$")


def suggest_layout(states: Mapping[str, str]) -> str:
    """Tell from entity states whether the grid reaches the plant.

    A GX device declares what its AC input is connected to: when none is in use,
    any energy on the bill cannot be passing through the plant.
    """
    inputs = [state for entity, state in states.items() if _AC_INPUT_SOURCE.search(entity)]
    if inputs and all(state == "not_used" for state in inputs):
        return LAYOUT_SEPARATE
    return LAYOUT_THROUGH_PLANT


def suggest_sources(entity_ids: Iterable[str]) -> dict[str, list[str]]:
    """Return the entities that look right for each role."""
    sensors = sorted(entity for entity in entity_ids if entity.startswith("sensor."))
    suggested = {
        role: [
            entity
            for entity in sensors
            if any(re.search(pattern, entity) for pattern in patterns)
        ]
        for role, patterns in ROLE_PATTERNS.items()
    }
    # One counter per charger is more exact, the system total is only a fallback.
    if not suggested["pv"]:
        suggested["pv"] = [entity for entity in sensors if _PV_FALLBACK.search(entity)]
    return suggested
