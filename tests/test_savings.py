from datetime import date, timedelta

import pytest

from billcore.savings import (
    LAYOUT_SEPARATE,
    PRICE_ALL_IN,
    PRICE_MANUAL,
    PRICE_WHOLE_HOME,
    PRICE_VARIABLE,
    PeriodEnergy,
    Sources,
    aggregate_period,
    compute_comparison,
    find_overlaps,
    find_superseded,
    resolve_price,
    whole_home_cost,
)
from billcore.validate import validate_fields

START = date(2026, 3, 1)
END = date(2026, 3, 10)
SOURCES = Sources(
    pv=("pv",),
    grid_import=("in_out", "in_inv"),
    grid_export=("inv_in",),
    consumption_add=("in_out", "inv_out"),
    consumption_subtract=("out_inv",),
    battery_charge=("chg",),
    battery_discharge=("dis",),
)


def days(first=START, last=END):
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def daily(**kwh_per_day):
    return {name: {day: value for day in days()} for name, value in kwh_per_day.items()}


def full_energy():
    return aggregate_period(
        daily(pv=10, in_out=2, in_inv=1, inv_in=0.5, inv_out=8, out_inv=0, chg=4, dis=3),
        SOURCES,
        START,
        END,
    )


def test_roles_are_summed_per_period():
    energy = full_energy()
    assert energy.total_days == 10
    assert energy.covered_days == 10
    assert energy.pv_kwh == 100
    assert energy.grid_import_kwh == 30
    assert energy.grid_export_kwh == 5
    assert energy.consumption_kwh == 100
    assert energy.battery_charge_kwh == 40
    assert energy.battery_discharge_kwh == 30


def test_a_day_counts_only_if_every_essential_source_measured_it():
    data = daily(pv=10, in_out=2, in_inv=1, inv_in=0.5, inv_out=8, out_inv=0)
    del data["in_out"][START]
    energy = aggregate_period(data, SOURCES, START, END)
    assert energy.covered_days == 9
    # The missing day is excluded from every role, not only from the missing one.
    assert energy.pv_kwh == 90
    assert energy.grid_import_kwh == 27


def test_consumption_from_energy_balance_without_a_load_meter():
    sources = Sources(
        pv=("pv",), grid_import=("imp",), grid_export=("exp",),
        battery_charge=("chg",), battery_discharge=("dis",),
    )
    energy = aggregate_period(
        daily(pv=10, imp=2, exp=1, chg=4, dis=3), sources, START, END
    )
    assert energy.consumption_method == "balance"
    assert energy.consumption_kwh == 100


def test_price_uses_the_variable_part_with_taxes():
    values = {
        "total_cost": 148.70,
        "consumption_kwh": 320.0,
        "cost_variable": 90.0,
        "cost_taxes": 13.0,
        "cost_tv": 19.0,
    }
    price, source = resolve_price(values, manual_price=None, default_tax_rate=0.1)
    assert source == PRICE_VARIABLE
    assert price == pytest.approx(90 * (1 + 13 / 116.7) / 320)


def test_price_derives_variable_from_fixed():
    values = {
        "total_cost": 110.0, "consumption_kwh": 100.0, "cost_fixed": 30.0, "cost_taxes": 10.0,
    }
    price, source = resolve_price(values, manual_price=None, default_tax_rate=0.1)
    assert source == PRICE_VARIABLE
    assert price == pytest.approx(70 * (1 + 10 / 100) / 100)


def test_all_in_average_is_the_last_resort_and_labelled():
    values = {"total_cost": 100.0, "consumption_kwh": 100.0, "cost_tv": 20.0}
    price, source = resolve_price(values, manual_price=None, default_tax_rate=0.1)
    assert source == PRICE_ALL_IN
    assert price == pytest.approx(0.8)


def test_manual_price_wins():
    values = {"total_cost": 100.0, "consumption_kwh": 100.0, "cost_variable": 50.0}
    assert resolve_price(values, manual_price=0.3, default_tax_rate=0.1) == (0.3, PRICE_MANUAL)


def test_no_price_without_billed_energy():
    assert resolve_price(
        {"total_cost": 30.0, "consumption_kwh": 0.0}, manual_price=None, default_tax_rate=0.1
    ) == (None, None)


def test_comparison_on_a_complete_period():
    values = {"total_cost": 50.0, "consumption_kwh": 33.0}
    result = compute_comparison(
        values, full_energy(), price=0.25, price_source=PRICE_VARIABLE, export_price=0.1
    )
    assert result["avoided_kwh"] == 70
    assert result["savings_eur"] == 18.0  # 70 kWh * 0.25 + 5 kWh exported * 0.10
    assert result["export_eur"] == 0.5
    assert result["cost_without_plant_eur"] == 67.5
    assert result["self_sufficiency_pct"] == 70
    assert result["home_kwh"] == 100
    assert result["self_consumption_pct"] == 95
    assert result["meter_delta_kwh"] == 3
    assert result["meter_delta_pct"] == 10
    assert result["partial"] is False


def test_partial_period_has_savings_but_no_meter_check():
    data = daily(pv=10, in_out=2, in_inv=1, inv_in=0.5, inv_out=8, out_inv=0)
    del data["pv"][START]
    energy = aggregate_period(data, SOURCES, START, END)
    result = compute_comparison(
        {"total_cost": 50.0, "consumption_kwh": 33.0}, energy, price=0.25, price_source=PRICE_VARIABLE
    )
    assert result["partial"] is True
    assert result["coverage_pct"] == 90
    assert result["avoided_kwh"] == 63
    assert result["meter_delta_kwh"] is None


def test_period_before_the_plant_was_monitored_has_no_savings():
    energy = aggregate_period({}, SOURCES, START, END)
    result = compute_comparison(
        {"total_cost": 50.0, "consumption_kwh": 33.0}, energy, price=0.25, price_source=PRICE_VARIABLE
    )
    assert result["coverage_pct"] == 0
    assert result["savings_eur"] is None
    assert "pv" in energy.missing_sources


def test_without_grid_meter_the_bill_replaces_it_on_full_periods_only():
    sources = Sources(pv=("pv",), consumption_add=("load",))
    energy = aggregate_period(daily(pv=10, load=10), sources, START, END)
    result = compute_comparison(
        {"total_cost": 50.0, "consumption_kwh": 30.0}, energy, price=0.25, price_source=PRICE_VARIABLE
    )
    assert result["avoided_kwh"] == 70
    assert result["meter_delta_kwh"] is None

    data = daily(pv=10, load=10)
    del data["pv"][START]
    energy = aggregate_period(data, sources, START, END)
    result = compute_comparison(
        {"total_cost": 50.0, "consumption_kwh": 30.0}, energy, price=0.25, price_source=PRICE_VARIABLE
    )
    assert result["savings_eur"] is None


def island():
    """A plant with no grid at its AC input, like an inverter-only MultiPlus."""
    return aggregate_period(
        daily(pv=10, in_out=0, in_inv=0, inv_in=0, inv_out=8, out_inv=0, chg=4, dis=3),
        SOURCES,
        START,
        END,
    )


def test_separate_plant_adds_to_the_bill_instead_of_overlapping_it():
    result = compute_comparison(
        {"total_cost": 50.0, "consumption_kwh": 120.0},
        island(),
        price=0.25,
        price_source=PRICE_VARIABLE,
        layout=LAYOUT_SEPARATE,
    )
    assert result["avoided_kwh"] == 80
    assert result["savings_eur"] == 20
    assert result["cost_without_plant_eur"] == 70
    # 80 kWh from the plant out of 200 for the whole home, not "100%".
    assert result["self_sufficiency_pct"] == 40
    assert result["grid_kwh"] == 120
    # Plant plus grid make up the month.
    assert result["home_kwh"] == 200
    # Bill and plant counters measure different circuits.
    assert result["meter_delta_kwh"] is None


def test_same_island_data_read_as_through_plant_would_be_wrong():
    # Guards the reason the layout exists: with no energy on the AC-in counters,
    # the other reading claims total self-sufficiency and a huge meter difference.
    result = compute_comparison(
        {"total_cost": 50.0, "consumption_kwh": 120.0},
        island(),
        price=0.25,
        price_source=PRICE_VARIABLE,
    )
    assert result["self_sufficiency_pct"] == 100
    assert result["meter_delta_kwh"] == 120


def test_separate_plant_with_partial_data_gives_savings_but_no_share():
    data = daily(pv=10, in_out=0, in_inv=0, inv_in=0, inv_out=8, out_inv=0)
    del data["pv"][START]
    energy = aggregate_period(data, SOURCES, START, END)
    result = compute_comparison(
        {"total_cost": 50.0, "consumption_kwh": 120.0},
        energy,
        price=0.25,
        price_source=PRICE_VARIABLE,
        layout=LAYOUT_SEPARATE,
    )
    assert result["savings_eur"] == 18
    assert result["self_sufficiency_pct"] is None
    assert result["home_kwh"] is None


def test_separate_plant_needs_no_grid_counter():
    sources = Sources(pv=("pv",), consumption_add=("load",))
    energy = aggregate_period(daily(pv=10, load=8), sources, START, END)
    result = compute_comparison(
        {"total_cost": 50.0, "consumption_kwh": 120.0},
        energy,
        price=0.25,
        price_source=PRICE_VARIABLE,
        layout=LAYOUT_SEPARATE,
    )
    assert result["avoided_kwh"] == 80


def test_grid_charging_a_separate_plant_is_not_counted_as_avoided():
    # If the AC input gets connected later, that energy is on the bill: not saved.
    energy = aggregate_period(
        daily(pv=10, in_out=1, in_inv=1, inv_in=0, inv_out=8, out_inv=0), SOURCES, START, END
    )
    result = compute_comparison(
        {"total_cost": 50.0, "consumption_kwh": 120.0},
        energy,
        price=0.25,
        price_source=PRICE_VARIABLE,
        layout=LAYOUT_SEPARATE,
    )
    assert result["avoided_kwh"] == 70


SEPTEMBER = {
    "total_cost": 57.94, "consumption_kwh": 90.0, "cost_tv": 9.0, "cost_other": -2.0,
    "cost_variable": 18.4, "cost_taxes": 6.67,
}


def september_energy(days=30, covered=30, loads=361.5):
    return PeriodEnergy(
        START, END, total_days=days, covered_days=covered, consumption_kwh=loads, pv_kwh=loads
    )


def test_simulated_bill_and_unit_cost():
    # Worked out by hand: (50.94 + 361.5 * 0.25) / (90 + 361.5)
    simulated, unit = whole_home_cost(SEPTEMBER, 361.5, 0.25)
    assert simulated == pytest.approx(141.315)
    assert unit == pytest.approx(141.315 / 451.5)


def test_savings_are_the_unit_cost_times_the_solar_kwh():
    result = compute_comparison(
        SEPTEMBER, september_energy(), price=0.25, price_source=PRICE_VARIABLE,
        layout=LAYOUT_SEPARATE, whole_home=True,
    )
    assert result["simulated_bill_eur"] == pytest.approx(141.32, abs=0.01)
    assert result["bill_energy_eur"] == 50.94
    assert result["price_eur_kwh"] == pytest.approx(141.315 / 451.5, abs=0.0001)
    assert result["price_source"] == PRICE_WHOLE_HOME
    assert result["enel_price_eur_kwh"] == 0.25
    assert result["savings_eur"] == pytest.approx(361.5 * 141.315 / 451.5, abs=0.01)
    assert result["home_kwh"] == 451.5


def test_without_plant_is_what_the_supplier_would_have_charged():
    result = compute_comparison(
        SEPTEMBER, september_energy(), price=0.25, price_source=PRICE_VARIABLE,
        layout=LAYOUT_SEPARATE, whole_home=True,
    )
    # Fixed charges would not double: real bill plus the solar kWh at the supplier's price.
    assert result["cost_without_plant_eur"] == pytest.approx(57.94 + 361.5 * 0.25, abs=0.01)


def test_a_one_off_credit_does_not_change_the_unit_cost():
    regular = {"total_cost": 80.0, "consumption_kwh": 100.0, "cost_tv": 9.0, "cost_other": -2.0}
    credit = {"total_cost": 55.0, "consumption_kwh": 100.0, "cost_tv": 9.0, "cost_other": -27.0}
    assert whole_home_cost(regular, 300.0, 0.25) == pytest.approx(whole_home_cost(credit, 300.0, 0.25))


def test_more_solar_lowers_the_unit_cost_towards_the_supplier_price():
    low = whole_home_cost(SEPTEMBER, 50.0, 0.25)[1]
    high = whole_home_cost(SEPTEMBER, 2000.0, 0.25)[1]
    assert low > high > 0.25


def test_partial_data_weighs_the_whole_period_on_the_unit_cost():
    half = compute_comparison(
        SEPTEMBER, september_energy(covered=15, loads=180.75), price=0.25,
        price_source=PRICE_VARIABLE, layout=LAYOUT_SEPARATE, whole_home=True,
    )
    full = compute_comparison(
        SEPTEMBER, september_energy(), price=0.25, price_source=PRICE_VARIABLE,
        layout=LAYOUT_SEPARATE, whole_home=True,
    )
    assert half["price_eur_kwh"] == pytest.approx(full["price_eur_kwh"], abs=0.0001)
    assert half["savings_eur"] == pytest.approx(full["savings_eur"] / 2, abs=0.01)


def test_a_bill_with_no_grid_energy_still_works():
    values = {"total_cost": 40.0, "consumption_kwh": 0.0, "cost_tv": 9.0}
    assert whole_home_cost(values, 100.0, 0.25) == pytest.approx((56.0, 0.56))


def test_manual_price_is_not_replaced_by_the_unit_cost():
    result = compute_comparison(
        SEPTEMBER, september_energy(), price=0.3, price_source=PRICE_MANUAL,
        layout=LAYOUT_SEPARATE, whole_home=True,
    )
    assert result["price_eur_kwh"] == 0.3
    assert result["savings_eur"] == pytest.approx(361.5 * 0.3, abs=0.01)


def test_days_with_no_bill_use_the_price_they_are_given():
    result = compute_comparison(
        {}, september_energy(), price=0.3, price_source=PRICE_WHOLE_HOME,
        layout=LAYOUT_SEPARATE, whole_home=True,
    )
    assert result["savings_eur"] == pytest.approx(361.5 * 0.3, abs=0.01)


def test_period_with_no_bill_has_savings_on_a_separate_plant():
    result = compute_comparison(
        {}, island(), price=0.25, price_source=PRICE_VARIABLE, layout=LAYOUT_SEPARATE
    )
    assert result["savings_eur"] == 20
    assert result["self_sufficiency_pct"] is None


def test_avoided_energy_is_never_negative():
    energy = PeriodEnergy(
        START, END, total_days=10, covered_days=10, grid_import_kwh=50, consumption_kwh=40
    )
    result = compute_comparison(
        {"total_cost": 20.0, "consumption_kwh": 50.0}, energy, price=0.2, price_source=PRICE_VARIABLE
    )
    assert result["avoided_kwh"] == 0
    assert result["savings_eur"] == 0


def test_reissued_bill_replaces_the_older_one():
    bills = [
        {"id": "old", "period_start": START, "period_end": END, "issue_date": "2026-04-01"},
        {"id": "new", "period_start": START, "period_end": END, "issue_date": "2026-05-01"},
        {"id": "other", "period_start": date(2026, 4, 1), "period_end": date(2026, 4, 30)},
    ]
    assert find_superseded(bills) == {"old"}


def test_partial_overlap_is_detected():
    bills = [
        {"id": "a", "period_start": date(2026, 1, 1), "period_end": date(2026, 2, 28)},
        {"id": "b", "period_start": date(2026, 2, 1), "period_end": date(2026, 3, 31)},
        {"id": "c", "period_start": date(2026, 4, 1), "period_end": date(2026, 4, 30)},
    ]
    assert find_overlaps(bills, set()) == {"a", "b"}


def test_validation_catches_what_a_misread_looks_like():
    good = {
        "period_start": START, "period_end": END, "total_cost": 60.0, "consumption_kwh": 200.0,
    }
    assert validate_fields(good) == []
    assert any(i["code"] == "missing_field" for i in validate_fields({**good, "total_cost": None}))
    assert any(
        i["code"] == "period_reversed"
        for i in validate_fields({**good, "period_start": END, "period_end": START})
    )
    assert any(
        i["code"] == "bands_mismatch"
        for i in validate_fields(
            {**good, "consumption_f1": 10.0, "consumption_f2": 10.0, "consumption_f3": 10.0}
        )
    )
    assert any(
        i["code"] == "parts_mismatch"
        for i in validate_fields(
            {**good, "cost_energy": 1.0, "cost_transport": 1.0, "cost_system": 1.0, "cost_taxes": 1.0}
        )
    )
    assert any(
        i["code"] == "implausible_unit_price"
        for i in validate_fields({**good, "total_cost": 2.0})
    )


def test_tiny_billed_consumption_is_not_an_implausible_price():
    # Fixed charges over few kWh: exactly what a well-sized plant produces.
    values = {
        "period_start": START, "period_end": END, "total_cost": 45.0, "consumption_kwh": 12.0,
    }
    assert validate_fields(values) == []
