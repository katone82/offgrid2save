"""Compare what a bill charged with what the plant measured."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

PRICE_MANUAL = "manual"
PRICE_VARIABLE = "bill_variable"
PRICE_ALL_IN = "all_in_average"
PRICE_PREVIOUS = "previous_bill"
PRICE_WHOLE_HOME = "whole_home"

# What a kWh from the plant is worth. The whole-home cost bills the plant's kWh as if
# the supplier had provided them, then shares the result over every kWh of the month.
# The variable price only counts what grows with consumption: it gives lower savings.
PRICE_METHOD_WHOLE_HOME = "whole_home"
PRICE_METHOD_VARIABLE = "variable"

# Where the billed grid energy goes. Through the plant, it reaches the same loads
# the plant measures, as in a grid-tied hybrid system. Separate, the plant runs its
# loads as an island and the bill pays for other circuits, so the two figures add up
# instead of overlapping.
LAYOUT_THROUGH_PLANT = "through_plant"
LAYOUT_SEPARATE = "separate"


@dataclass(frozen=True)
class Sources:
    """Which energy statistics play which role."""

    pv: tuple[str, ...] = ()
    grid_import: tuple[str, ...] = ()
    grid_export: tuple[str, ...] = ()
    consumption_add: tuple[str, ...] = ()
    consumption_subtract: tuple[str, ...] = ()
    battery_charge: tuple[str, ...] = ()
    battery_discharge: tuple[str, ...] = ()

    def all_ids(self) -> set[str]:
        """Return every statistic that has to be read."""
        return {
            *self.pv,
            *self.grid_import,
            *self.grid_export,
            *self.consumption_add,
            *self.consumption_subtract,
            *self.battery_charge,
            *self.battery_discharge,
        }

    def essential_ids(self) -> set[str]:
        """Return the statistics a day needs to count as measured."""
        return {*self.grid_import, *self.consumption_add, *self.pv}


@dataclass
class PeriodEnergy:
    """Energy measured over the covered days of a period."""

    start: date
    end: date
    total_days: int = 0
    covered_days: int = 0
    pv_kwh: float = 0.0
    grid_import_kwh: float = 0.0
    grid_export_kwh: float = 0.0
    consumption_kwh: float = 0.0
    battery_charge_kwh: float = 0.0
    battery_discharge_kwh: float = 0.0
    consumption_method: str = "meter"
    grid_measured: bool = True
    missing_sources: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return self.total_days > 0 and self.covered_days == self.total_days

    def as_dict(self) -> dict:
        data = asdict(self)
        data["start"] = self.start.isoformat()
        data["end"] = self.end.isoformat()
        return data


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def aggregate_period(
    daily: dict[str, dict[date, float]], sources: Sources, start: date, end: date
) -> PeriodEnergy:
    """Sum daily energy per role, counting only days every essential source measured.

    Counting a role on a day when another role has no data would compare
    consumption and grid import over different windows, and invent savings.
    """
    days = _days(start, end)
    essential = sources.essential_ids()
    covered = [
        day
        for day in days
        if essential and all(day in daily.get(source, {}) for source in essential)
    ]

    def total(ids: tuple[str, ...]) -> float:
        return sum(daily.get(source, {}).get(day, 0.0) for source in ids for day in covered)

    pv = total(sources.pv)
    grid_import = total(sources.grid_import)
    grid_export = total(sources.grid_export)
    charge = total(sources.battery_charge)
    discharge = total(sources.battery_discharge)
    if sources.consumption_add:
        consumption = total(sources.consumption_add) - total(sources.consumption_subtract)
        method = "meter"
    else:
        consumption = pv + grid_import - grid_export + discharge - charge
        method = "balance"

    return PeriodEnergy(
        start=start,
        end=end,
        total_days=len(days),
        covered_days=len(covered),
        pv_kwh=pv,
        grid_import_kwh=grid_import,
        grid_export_kwh=grid_export,
        consumption_kwh=max(consumption, 0.0),
        battery_charge_kwh=charge,
        battery_discharge_kwh=discharge,
        consumption_method=method,
        grid_measured=bool(sources.grid_import),
        missing_sources=sorted(s for s in sources.all_ids() if not daily.get(s)),
    )


def merge_daily(
    history: dict[str, dict[date, float]], statistics: dict[str, dict[date, float]]
) -> dict[str, dict[date, float]]:
    """Fill the days missing from the statistics with recovered history."""
    merged = {entity: dict(days) for entity, days in history.items()}
    for entity, days in statistics.items():
        merged.setdefault(entity, {}).update(days)
    return merged


def covered_days(daily: dict[str, dict[date, float]], sources: Sources) -> list[date]:
    """Return the days every essential source measured, oldest first."""
    essential = sources.essential_ids()
    if not essential or not all(daily.get(source) for source in essential):
        return []
    days = set.intersection(*(set(daily[source]) for source in essential))
    return sorted(days)


def bill_energy_cost(values: dict[str, object]) -> float | None:
    """Return what a bill charged for energy.

    The TV licence and other items are left out: they have nothing to do with energy,
    and a one-off credit would make a month look cheap.
    """
    total = values.get("total_cost")
    if not isinstance(total, float):
        return None
    excluded = ("cost_tv", "cost_other", "cost_recalc", "cost_bonus")
    return max(total - sum(float(values.get(key) or 0.0) for key in excluded), 0.0)


def resolve_price(
    values: dict[str, object],
    *,
    manual_price: float | None,
    default_tax_rate: float,
) -> tuple[float | None, str | None]:
    """Return what one more kWh from the supplier costs, taxes included.

    This is the variable part of the bill. The average of the whole bill is only a
    last resort, labelled as such, because it includes fixed charges.
    """
    if manual_price:
        return manual_price, PRICE_MANUAL

    kwh = values.get("consumption_kwh")
    total = values.get("total_cost")
    if not isinstance(kwh, float) or kwh <= 0 or not isinstance(total, float):
        return None, None

    tv = float(values.get("cost_tv") or 0.0)
    other = float(values.get("cost_other") or 0.0)
    recalc = float(values.get("cost_recalc") or 0.0)
    bonus = float(values.get("cost_bonus") or 0.0)
    taxes = values.get("cost_taxes")
    tax_rate = default_tax_rate
    if isinstance(taxes, float):
        taxable = total - taxes - tv - other - recalc - bonus
        if taxable > 0 and taxes >= 0:
            tax_rate = taxes / taxable

    variable = values.get("cost_variable")
    fixed = values.get("cost_fixed")
    if not isinstance(variable, float) and isinstance(fixed, float) and isinstance(taxes, float):
        variable = total - taxes - tv - other - recalc - bonus - fixed
    if isinstance(variable, float) and variable > 0:
        return variable * (1 + tax_rate) / kwh, PRICE_VARIABLE

    return bill_energy_cost(values) / kwh, PRICE_ALL_IN


def whole_home_cost(
    values: dict[str, object], plant_kwh: float, enel_price: float
) -> tuple[float, float] | None:
    """Bill the plant's kWh as if the supplier had provided them.

    Returns that simulated cost and what it comes to per kWh, over all the kWh of the
    month. Fixed charges get shared over everything the home used, rather than only
    over the few kWh a good plant leaves on the bill.
    """
    energy_cost = bill_energy_cost(values)
    billed = values.get("consumption_kwh")
    if energy_cost is None or not isinstance(billed, float) or billed + plant_kwh <= 0:
        return None
    simulated = energy_cost + plant_kwh * enel_price
    return simulated, simulated / (billed + plant_kwh)


def compute_comparison(
    values: dict[str, object],
    energy: PeriodEnergy,
    *,
    price: float | None,
    price_source: str | None,
    export_price: float = 0.0,
    layout: str = LAYOUT_THROUGH_PLANT,
    whole_home: bool = False,
) -> dict:
    """Put a bill next to the measured energy of its period.

    ``price`` is what a kWh costs from the supplier. With ``whole_home`` the savings use
    the whole-home cost built from it, unless the user set their own price.
    """
    billed = values.get("consumption_kwh")
    total = values.get("total_cost")
    result: dict = {
        "price_eur_kwh": round(price, 4) if price is not None else None,
        "price_source": price_source,
        "coverage_pct": round(100 * energy.covered_days / energy.total_days, 1)
        if energy.total_days
        else 0.0,
        "partial": not energy.is_complete,
        "energy": energy.as_dict(),
        "enel_price_eur_kwh": round(price, 4) if price is not None else None,
        "enel_price_source": price_source,
        "bill_energy_eur": None,
        "simulated_bill_eur": None,
        "layout": layout,
        "avoided_kwh": None,
        "grid_kwh": None,
        "home_kwh": None,
        "savings_eur": None,
        "export_eur": None,
        "cost_without_plant_eur": None,
        "self_sufficiency_pct": None,
        "self_consumption_pct": None,
        "meter_delta_kwh": None,
        "meter_delta_pct": None,
    }
    if energy.covered_days == 0:
        return result

    # Measured import, not billed kWh: both sides of the subtraction then cover
    # the same days, and estimated bill readings do not distort the result.
    # Plants with no grid meter fall back on the bill, valid over the full period only.
    separate = layout == LAYOUT_SEPARATE
    if energy.grid_measured or separate:
        grid = energy.grid_import_kwh
    elif energy.is_complete and isinstance(billed, float):
        grid = billed
    else:
        return result
    avoided = max(energy.consumption_kwh - grid, 0.0)
    result["avoided_kwh"] = round(avoided, 2)
    if separate:
        # The bill covers its whole period: comparing it with a part of the period
        # would understate how much of the home the plant supplies.
        if isinstance(billed, float):
            result["grid_kwh"] = round(billed, 2)
            if energy.is_complete:
                # The month's total: what the plant supplied plus what the grid did.
                result["home_kwh"] = round(avoided + billed, 2)
                if avoided + billed > 0:
                    result["self_sufficiency_pct"] = round(100 * avoided / (avoided + billed), 1)
    else:
        result["grid_kwh"] = round(grid, 2)
        result["home_kwh"] = round(energy.consumption_kwh, 2)
        if energy.consumption_kwh > 0:
            result["self_sufficiency_pct"] = round(100 * avoided / energy.consumption_kwh, 1)
    if energy.pv_kwh > 0:
        used = max(energy.pv_kwh - energy.grid_export_kwh, 0.0)
        result["self_consumption_pct"] = round(100 * used / energy.pv_kwh, 1)

    if price is not None:
        unit = price
        if whole_home and price_source != PRICE_MANUAL:
            # With data for part of the period, the kWh of the missing days still weigh
            # on the unit cost: the bill being shared covers all of them.
            whole_period = avoided * energy.total_days / energy.covered_days
            cost = whole_home_cost(values, whole_period, price)
            if cost:
                unit = cost[1]
                result["bill_energy_eur"] = round(bill_energy_cost(values), 2)
                result["simulated_bill_eur"] = round(cost[0], 2)
                result["price_eur_kwh"] = round(unit, 4)
                result["price_source"] = PRICE_WHOLE_HOME
        export = energy.grid_export_kwh * export_price
        result["savings_eur"] = round(avoided * unit + export, 2)
        result["export_eur"] = round(export, 2)
        if isinstance(total, float):
            # What the supplier would really have charged: fixed charges stay as they are.
            result["cost_without_plant_eur"] = round(total + avoided * price, 2)

    # The meter check only means something over the whole billed period, and when
    # the billed energy really passes through the plant's counters.
    if not separate and energy.grid_measured and energy.is_complete and isinstance(billed, float):
        delta = billed - energy.grid_import_kwh
        result["meter_delta_kwh"] = round(delta, 2)
        if energy.grid_import_kwh > 0:
            result["meter_delta_pct"] = round(100 * delta / energy.grid_import_kwh, 1)
    return result


def find_superseded(bills: list[dict]) -> set[str]:
    """Return ids of bills replaced by a later one for the very same period.

    Suppliers reissue corrected bills: counting both would double the savings.
    Each bill dict needs id, period_start, period_end and optionally issue_date.
    """
    newest: dict[tuple, dict] = {}
    superseded: set[str] = set()
    for bill in bills:
        key = (bill["period_start"], bill["period_end"])
        current = newest.get(key)
        if current is None:
            newest[key] = bill
            continue
        older, kept = sorted(
            (current, bill), key=lambda item: (str(item.get("issue_date") or ""), item["id"])
        )
        superseded.add(older["id"])
        newest[key] = kept
    return superseded


def find_overlaps(bills: list[dict], ignored: set[str]) -> set[str]:
    """Return ids of bills whose period partly overlaps another one."""
    active = sorted(
        (bill for bill in bills if bill["id"] not in ignored),
        key=lambda item: item["period_start"],
    )
    overlapping: set[str] = set()
    for previous, current in zip(active, active[1:]):
        if current["period_start"] <= previous["period_end"]:
            overlapping.update((previous["id"], current["id"]))
    return overlapping
