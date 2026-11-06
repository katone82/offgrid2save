from billcore.savings import LAYOUT_SEPARATE, LAYOUT_THROUGH_PLANT
from billcore.suggest import suggest_layout, suggest_sources

MPPT = "sensor.smartsolar_mppt_ve_can_250_100_rev2_id_279"
MULTI = "sensor.multiplus_ii_48_6k5_100_50_id_276"
VICTRON = [
    f"{MPPT}_total_yield",
    f"{MPPT}_yield_today",
    f"{MULTI}_energy_from_ac_in_1_to_ac_out",
    f"{MULTI}_energy_from_ac_in_1_to_inverter",
    f"{MULTI}_energy_from_ac_out_to_ac_in_1",
    f"{MULTI}_energy_from_inverter_to_ac_in_1",
    f"{MULTI}_energy_from_inverter_to_ac_out",
    f"{MULTI}_energy_from_out_to_inverter",
    "sensor.gx_device_pv_energy",
    "sensor.gx_device_dc_battery_charge_energy",
    "sensor.gx_device_dc_battery_discharge_energy",
    "sensor.gx_device_dc_battery_voltage",
    "light.salotto",
]


def test_victron_counters_fill_their_roles():
    suggested = suggest_sources(VICTRON)
    assert suggested["pv"] == [f"{MPPT}_total_yield"]
    assert suggested["grid_import"] == [
        f"{MULTI}_energy_from_ac_in_1_to_ac_out",
        f"{MULTI}_energy_from_ac_in_1_to_inverter",
    ]
    assert suggested["grid_export"] == [
        f"{MULTI}_energy_from_ac_out_to_ac_in_1",
        f"{MULTI}_energy_from_inverter_to_ac_in_1",
    ]
    assert suggested["consumption_add"] == [
        f"{MULTI}_energy_from_ac_in_1_to_ac_out",
        f"{MULTI}_energy_from_inverter_to_ac_out",
    ]
    assert suggested["consumption_subtract"] == [
        f"{MULTI}_energy_from_ac_out_to_ac_in_1",
        f"{MULTI}_energy_from_out_to_inverter",
    ]
    assert suggested["battery_charge"] == ["sensor.gx_device_dc_battery_charge_energy"]
    assert suggested["battery_discharge"] == ["sensor.gx_device_dc_battery_discharge_energy"]


def test_unused_ac_inputs_mean_the_plant_is_separate_from_the_grid():
    states = {
        "select.gx_device_ac_input_1_source_type": "not_used",
        "select.gx_device_ac_input_2_source_type": "not_used",
    }
    assert suggest_layout(states) == LAYOUT_SEPARATE


def test_an_ac_input_in_use_means_the_grid_goes_through_the_plant():
    states = {
        "select.gx_device_ac_input_1_source_type": "grid",
        "select.gx_device_ac_input_2_source_type": "not_used",
    }
    assert suggest_layout(states) == LAYOUT_THROUGH_PLANT


def test_other_brands_default_to_grid_through_the_plant():
    assert suggest_layout({"select.something_else": "not_used"}) == LAYOUT_THROUGH_PLANT


def test_gx_total_is_the_pv_fallback():
    assert suggest_sources(["sensor.gx_device_pv_energy"])["pv"] == ["sensor.gx_device_pv_energy"]


def test_other_brands_suggest_nothing():
    suggested = suggest_sources(["sensor.fronius_energy_total", "sensor.shelly_em_energy"])
    assert all(not value for value in suggested.values())
