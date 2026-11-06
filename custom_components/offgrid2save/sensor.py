"""Sensors, to use the results in dashboards and automations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VERSION
from .manager import BillManager

EUR = "EUR"


def _last_bill(data: dict) -> dict | None:
    """Return the newest bill that entered the calculations."""
    counted = [b for b in data["bills"] if b["status"] == "ok" and not b["superseded"]]
    return counted[-1] if counted else None


def _bill_value(key: str) -> Callable[[dict], Any]:
    def read(data: dict) -> Any:
        bill = _last_bill(data)
        return bill["values"].get(key) if bill else None

    return read


def _comparison(key: str) -> Callable[[dict], Any]:
    def read(data: dict) -> Any:
        bill = _last_bill(data)
        return (bill["comparison"] or {}).get(key) if bill else None

    return read


def _current(key: str) -> Callable[[dict], Any]:
    def read(data: dict) -> Any:
        return (data["current_period"] or {}).get(key)

    return read


@dataclass(frozen=True, kw_only=True)
class OffGrid2SaveSensorDescription(SensorEntityDescription):
    """A sensor and how to read its value from the overview."""

    value_fn: Callable[[dict], Any]


def _money(key: str, value_fn: Callable[[dict], Any], **extra: Any) -> OffGrid2SaveSensorDescription:
    return OffGrid2SaveSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=EUR,
        suggested_display_precision=2,
        value_fn=value_fn,
        **extra,
    )


def _percent(key: str, value_fn: Callable[[dict], Any]) -> OffGrid2SaveSensorDescription:
    return OffGrid2SaveSensorDescription(
        key=key,
        translation_key=key,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=value_fn,
    )


SENSORS: tuple[OffGrid2SaveSensorDescription, ...] = (
    _money("total_savings", lambda data: data["totals"]["savings_eur"]),
    _money("total_paid", lambda data: data["totals"]["cost_eur"]),
    _money("total_without_plant", lambda data: data["totals"]["cost_without_plant_eur"]),
    _money("last_bill_cost", _bill_value("total_cost")),
    _money("last_bill_savings", _comparison("savings_eur")),
    _money("last_bill_without_plant", _comparison("cost_without_plant_eur")),
    OffGrid2SaveSensorDescription(
        key="last_bill_energy",
        translation_key="last_bill_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=_bill_value("consumption_kwh"),
    ),
    OffGrid2SaveSensorDescription(
        key="energy_price",
        translation_key="energy_price",
        native_unit_of_measurement="EUR/kWh",
        suggested_display_precision=3,
        value_fn=_comparison("price_eur_kwh"),
    ),
    _percent("last_bill_self_sufficiency", _comparison("self_sufficiency_pct")),
    _money("current_period_savings", _current("savings_eur")),
    _percent("current_period_self_sufficiency", _current("self_sufficiency_pct")),
    OffGrid2SaveSensorDescription(
        key="bills_to_review",
        translation_key="bills_to_review",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["to_review"],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: Any, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Create the sensors."""
    manager: BillManager = entry.runtime_data
    async_add_entities(OffGrid2SaveSensor(manager, description) for description in SENSORS)


class OffGrid2SaveSensor(CoordinatorEntity[BillManager], SensorEntity):
    """A value from the overview."""

    entity_description: OffGrid2SaveSensorDescription
    _attr_has_entity_name = True

    def __init__(self, manager: BillManager, description: OffGrid2SaveSensorDescription) -> None:
        super().__init__(manager)
        self.entity_description = description
        entry_id = manager.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="OffGrid2Save",
            entry_type=DeviceEntryType.SERVICE,
            sw_version=VERSION,
        )

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)
