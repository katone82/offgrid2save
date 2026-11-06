from datetime import date, datetime, timedelta
from pathlib import Path
import sqlite3
import sys

from billcore.savings import Sources, covered_days, merge_daily

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from recover_history import daily_changes, recover

DAY1 = date(2026, 9, 1)
DAY2 = date(2026, 9, 2)
DAY3 = date(2026, 9, 3)
DAY4 = date(2026, 9, 4)


def at(day, hour=12):
    return datetime(day.year, day.month, day.day, hour).timestamp()


def hours(day, start, end, count=24):
    """Hourly rows for a day, with the running sum going from start to end."""
    return [
        (at(day, hour), start + (end - start) * (hour + 1) / count)
        for hour in range(count)
    ]


def iso(*days):
    return [day.isoformat() for day in days]


def test_statistics_win_over_history_and_history_fills_the_rest():
    merged = merge_daily(
        {"a": {DAY1: 1.0, DAY2: 2.0}, "unused": {DAY1: 9.0}},
        {"a": {DAY2: 5.0, DAY3: 6.0}},
    )
    assert merged["a"] == {DAY1: 1.0, DAY2: 5.0, DAY3: 6.0}


def test_covered_days_need_every_essential_source():
    sources = Sources(pv=("pv",), consumption_add=("load",))
    daily = {"pv": {DAY1: 1.0, DAY2: 1.0}, "load": {DAY2: 1.0, DAY3: 1.0}}
    assert covered_days(daily, sources) == [DAY2]
    assert covered_days({"pv": {DAY1: 1.0}}, sources) == []


def test_complete_days_are_kept():
    rows = hours(DAY1, 10, 12) + hours(DAY2, 12, 15)
    result = daily_changes(rows, 1.0)
    assert result[DAY2.isoformat()] == 3.0
    assert result[DAY1.isoformat()] > 0


def test_a_jump_after_a_hole_is_not_one_day_of_energy():
    # The real case: 351 kWh "produced" on a day, after 21 days with no data.
    later = DAY1 + timedelta(days=20)
    rows = hours(DAY1, 0, 10) + hours(later, 361, 370) + hours(later + timedelta(days=1), 370, 380)
    result = daily_changes(rows, 1.0)
    assert later.isoformat() not in result
    assert result[(later + timedelta(days=1)).isoformat()] == 10.0


def test_partly_recorded_day_is_left_out():
    rows = (
        hours(DAY1, 0, 10) + hours(DAY2, 10, 12, count=12)
        + hours(DAY3, 12, 20) + hours(DAY4, 20, 30)
    )
    result = daily_changes(rows, 1.0)
    assert DAY2.isoformat() not in result
    # The next day opens with the hole, so its difference holds the missing hours too.
    assert DAY3.isoformat() not in result
    assert result[DAY4.isoformat()] == 10.0


def test_hole_inside_a_day_is_left_out():
    day2 = [row for row in hours(DAY2, 10, 20) if not 8 <= datetime.fromtimestamp(row[0]).hour <= 11]
    rows = hours(DAY1, 0, 10) + day2 + hours(DAY3, 20, 30)
    assert DAY2.isoformat() not in daily_changes(rows, 1.0)


def test_counter_reset_day_is_left_out():
    # The real case: the load counter restarts and the running sum falls by 130.
    reset = hours(DAY2, 140, 150)[:10] + hours(DAY2, 20, 25)[10:]
    rows = hours(DAY1, 130, 140) + reset + hours(DAY3, 25, 35)
    result = daily_changes(rows, 1.0)
    assert DAY2.isoformat() not in result
    assert result[DAY3.isoformat()] == 10.0


def test_frozen_days_count_together_with_the_jump_that_ends_them():
    # The total over the stretch is right even if single days are not.
    rows = hours(DAY1, 0, 10) + hours(DAY2, 10, 10) + hours(DAY3, 10, 10) + hours(DAY4, 10, 40)
    result = daily_changes(rows, 1.0)
    assert result[DAY2.isoformat()] == 0.0
    assert result[DAY3.isoformat()] == 0.0
    assert result[DAY4.isoformat()] == 30.0


def test_frozen_days_go_when_the_jump_is_not_sound():
    # A jump that is left out takes its standstill with it, or those days would read 0.
    after = DAY4 + timedelta(days=3)
    rows = (
        hours(DAY1, 0, 10) + hours(DAY2, 10, 10) + hours(DAY3, 10, 10)
        + hours(after, 500, 510) + hours(after + timedelta(days=1), 510, 520)
    )
    result = daily_changes(rows, 1.0)
    assert DAY2.isoformat() not in result
    assert DAY3.isoformat() not in result
    assert DAY1.isoformat() in result


def test_frozen_days_at_the_end_are_left_out():
    rows = hours(DAY1, 0, 10) + hours(DAY2, 10, 10)
    assert DAY2.isoformat() not in daily_changes(rows, 1.0)


def test_counter_that_never_moves_is_a_true_zero():
    # An AC input with nothing connected must not void the days of the plant.
    rows = hours(DAY1, 0, 0) + hours(DAY2, 0, 0) + hours(DAY3, 0, 0)
    assert daily_changes(rows, 1.0) == dict.fromkeys(iso(DAY1, DAY2, DAY3), 0.0)


def test_units_are_converted():
    rows = hours(DAY1, 0, 0) + hours(DAY2, 0, 500)
    assert daily_changes(rows, 0.001)[DAY2.isoformat()] == 0.5


def test_recover_reads_energy_series_only(tmp_path):
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.execute("create table statistics_meta (id, statistic_id, unit_of_measurement, has_sum)")
    db.execute("create table statistics (metadata_id, start_ts, sum)")
    db.executemany(
        "insert into statistics_meta values (?, ?, ?, ?)",
        [
            (1, "sensor.pv", "kWh", 1),
            (2, "sensor.water", "L", 1),
            (3, "external:pv", "kWh", 1),
            (4, "sensor.empty", "kWh", 1),
        ],
    )
    rows = hours(DAY1, 0, 3) + hours(DAY2, 3, 8)
    db.executemany("insert into statistics values (1, ?, ?)", rows)
    db.executemany("insert into statistics values (2, ?, ?)", rows)
    db.executemany("insert into statistics values (3, ?, ?)", rows)
    db.commit()
    db.close()
    recovered = recover(str(path))
    assert list(recovered) == ["sensor.pv"]
    assert recovered["sensor.pv"][DAY2.isoformat()] == 5.0
