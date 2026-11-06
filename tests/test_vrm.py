from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from billcore.savings import LAYOUT_SEPARATE, aggregate_period, compute_comparison
from billcore.vrm import (
    MAX_DAYS_PER_REQUEST,
    VRM_SOURCES,
    days_from_records,
    missing_ranges,
    split_at_clock_changes,
    to_daily,
)

ROME = ZoneInfo("Europe/Rome")
DAY1 = date(2026, 9, 1)
DAY2 = date(2026, 9, 2)
YESTERDAY = date(2026, 11, 4)


def local_date(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).astimezone(ROME).date()


def ms(day):
    return datetime(day.year, day.month, day.day, tzinfo=ROME).timestamp() * 1000


def stored(*days):
    return {day.isoformat(): {"pv": 1.0} for day in days}


def test_flows_become_roles():
    records = {
        "Pc": [[ms(DAY1), 3.0]],
        "Pb": [[ms(DAY1), 5.0]],
        "Pg": [[ms(DAY1), 1.0]],
        "Bc": [[ms(DAY1), 4.0]],
        "Bg": [[ms(DAY1), 0.5]],
        "Gc": [[ms(DAY1), 2.0]],
        "Gb": [[ms(DAY1), 0.25]],
    }
    assert days_from_records(records, local_date)[DAY1] == {
        "pv": 9.0,
        "grid_import": 2.25,
        "grid_export": 1.5,
        "consumption": 9.0,
        "battery_charge": 5.25,
        "battery_discharge": 4.5,
    }


def test_flows_that_never_happen_are_zero_not_missing():
    # On a plant with no grid VRM has no grid series at all.
    result = days_from_records({"Pc": [[ms(DAY1), 3.0]]}, local_date)
    assert result[DAY1]["grid_import"] == 0
    assert result[DAY1]["pv"] == 3


def test_midnight_in_italy_stays_on_its_own_day():
    # It is still the day before in UTC.
    assert list(days_from_records({"Pc": [[ms(DAY2), 1.0]]}, local_date)) == [DAY2]


def offset(day):
    return datetime(day.year, day.month, day.day, tzinfo=ROME).utcoffset()


def test_a_range_is_split_where_the_clock_changes():
    # The real case: VRM's 24 hour blocks shifted every day after 25 October by one.
    assert split_at_clock_changes(date(2026, 9, 1), date(2026, 11, 4), offset) == [
        (date(2026, 9, 1), date(2026, 10, 25)),
        (date(2026, 10, 26), date(2026, 11, 4)),
    ]


def test_a_range_with_no_clock_change_stays_whole():
    assert split_at_clock_changes(date(2026, 9, 1), date(2026, 9, 30), offset) == [
        (date(2026, 9, 1), date(2026, 9, 30))
    ]


def test_spring_clock_change_is_split_too():
    assert split_at_clock_changes(date(2026, 3, 1), date(2026, 4, 30), offset) == [
        (date(2026, 3, 1), date(2026, 3, 29)),
        (date(2026, 3, 30), date(2026, 4, 30)),
    ]


def test_records_of_the_same_day_add_up():
    # The 25 hour day of a clock change comes as a 24 hour block and a 1 hour one.
    change = date(2026, 10, 25)
    start = datetime(2026, 10, 25, tzinfo=ROME).timestamp() * 1000
    records = {"Pc": [[start, 10.0], [start + 24 * 3600 * 1000, 0.5]]}
    assert days_from_records(records, local_date)[change]["pv"] == 10.5


def test_empty_answers_mean_no_data():
    assert days_from_records([], local_date) == {}
    assert days_from_records({}, local_date) == {}
    assert days_from_records({"Pc": None}, local_date) == {}
    assert days_from_records({"Pc": [[ms(DAY1), None]]}, local_date) == {}


def test_a_new_bill_downloads_its_whole_period():
    period = (date(2026, 9, 1), date(2026, 9, 30))
    assert missing_ranges({}, [period], YESTERDAY) == [period]


def test_days_already_stored_are_not_downloaded_again():
    period = (date(2026, 9, 1), date(2026, 9, 30))
    known = stored(*(date(2026, 9, 1) + timedelta(days=i) for i in range(30)))
    assert missing_ranges(known, [period], YESTERDAY) == []


def test_only_the_gap_is_downloaded():
    known = stored(*(date(2026, 9, 1) + timedelta(days=i) for i in range(30) if i != 10))
    assert missing_ranges(known, [(date(2026, 9, 1), date(2026, 9, 30))], YESTERDAY) == [
        (date(2026, 9, 11), date(2026, 9, 11))
    ]


def test_recent_days_are_read_again():
    # A GX device that was offline uploads them later.
    period = (date(2026, 11, 1), YESTERDAY)
    known = stored(*(date(2026, 11, 1) + timedelta(days=i) for i in range(4)))
    assert missing_ranges(known, [period], YESTERDAY) == [(date(2026, 11, 3), YESTERDAY)]


def test_empty_days_are_checked_again_for_a_while():
    known = {"2026-11-01": {}, "2026-09-01": {}}
    periods = [(date(2026, 11, 1), date(2026, 11, 1)), (date(2026, 9, 1), date(2026, 9, 1))]
    assert missing_ranges(known, periods, YESTERDAY) == [(date(2026, 11, 1), date(2026, 11, 1))]


def test_the_future_is_never_requested():
    period = (date(2026, 11, 1), date(2026, 11, 30))
    assert missing_ranges({}, [period], YESTERDAY) == [(date(2026, 11, 1), YESTERDAY)]


def test_long_periods_respect_the_limit_of_the_api():
    ranges = missing_ranges({}, [(date(2025, 1, 1), date(2026, 3, 31))], YESTERDAY)
    assert len(ranges) > 1
    for start, end in ranges:
        assert (end - start).days < MAX_DAYS_PER_REQUEST + 1
    assert ranges[0][0] == date(2025, 1, 1)
    assert ranges[-1][1] == date(2026, 3, 31)


def test_overlapping_periods_are_requested_once():
    periods = [(DAY1, DAY2), (DAY1, DAY2)]
    assert missing_ranges({}, periods, YESTERDAY) == [(DAY1, DAY2)]


def test_stored_days_feed_the_comparison():
    roles = {
        "pv": 10.0, "grid_import": 0.0, "grid_export": 0.0, "consumption": 8.0,
        "battery_charge": 4.0, "battery_discharge": 3.0,
    }
    known = {"2026-09-01": roles, "2026-09-02": roles, "2026-09-03": {}}
    energy = aggregate_period(to_daily(known), VRM_SOURCES, DAY1, date(2026, 9, 3))
    # A day VRM has nothing for is not measured, rather than measured as zero.
    assert energy.covered_days == 2
    assert energy.total_days == 3
    assert energy.pv_kwh == 20
    assert energy.consumption_kwh == 16

    result = compute_comparison(
        {"total_cost": 50.0, "consumption_kwh": 90.0},
        energy,
        price=0.25,
        price_source="bill_variable",
        layout=LAYOUT_SEPARATE,
    )
    assert result["savings_eur"] == pytest.approx(4.0)
    assert result["partial"] is True
