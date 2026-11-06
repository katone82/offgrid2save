#!/usr/bin/env python3
"""Recover daily energy from a Home Assistant database, even one set aside as corrupt.

When its database gets corrupted, Home Assistant renames it and starts a new one, and
all long-term statistics seem lost. Most of them are usually still readable. This
extracts the daily energy of every kWh sensor, for OffGrid2Save to use where current
statistics have nothing. It only reads the database and needs nothing but Python.

Run it on the machine holding the database, with the time zone of Home Assistant:

    python3 recover_history.py home-assistant_v2.db.corrupt.XXX > offgrid2save/history.json
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import sqlite3
import sys

TO_KWH = {"kWh": 1.0, "Wh": 0.001, "MWh": 1000.0}
MIN_ROWS_PER_DAY = 20
MAX_GAP_SECONDS = 2 * 3600


def daily_changes(rows: list[tuple[float, float]], factor: float) -> dict[str, float]:
    """Turn hourly (timestamp, running sum) rows into energy per local day, keeping only sound days.

    An old database can look complete and still hold false days, and a day counted
    wrong would skew the savings. So a day is left out when:

    - recording was incomplete, or stopped for a while before it: the next difference
      holds the energy of the missing hours, which may belong to another bill;
    - the counter dropped: part of that day's energy is lost;
    - the counter stood still and what ended the standstill was not a sound day. A
      frozen sensor reads zero for days and then jumps. Those days stay only when the
      jump does too, because then their sum is right.
    """
    by_day: dict = {}
    previous_timestamp, previous_total = rows[0]
    unsound: set = set()
    for timestamp, total in rows:
        day = datetime.fromtimestamp(timestamp).date()
        by_day.setdefault(day, []).append(total)
        if timestamp - previous_timestamp > MAX_GAP_SECONDS or total < previous_total - 1e-6:
            unsound.add(day)
        previous_timestamp, previous_total = timestamp, total
    unsound.update(day for day, totals in by_day.items() if len(totals) < MIN_ROWS_PER_DAY)

    changes: dict = {}
    previous_end = rows[0][1]
    for day in sorted(by_day):
        changes[day] = max(by_day[day][-1] - previous_end, 0.0)
        previous_end = by_day[day][-1]

    # A counter that never moved is a true zero, such as an AC input with nothing on it.
    if any(changes.values()):
        sound_after = False
        for day in sorted(changes, reverse=True):
            if changes[day] == 0.0 and not sound_after:
                unsound.add(day)
            following_is_contiguous = day - timedelta(days=1) in changes
            sound_after = day not in unsound and following_is_contiguous

    return {
        day.isoformat(): round(change * factor, 3)
        for day, change in sorted(changes.items())
        if day not in unsound
    }


def recover(path: str) -> dict[str, dict[str, float]]:
    """Read every energy series that can still be read."""
    database = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    series = database.execute(
        "select id, statistic_id, unit_of_measurement from statistics_meta "
        "where has_sum = 1 and statistic_id like 'sensor.%'"
    ).fetchall()
    recovered: dict[str, dict[str, float]] = {}
    for meta_id, statistic_id, unit in series:
        if unit not in TO_KWH:
            continue
        try:
            rows = database.execute(
                "select start_ts, sum from statistics "
                "where metadata_id = ? and sum is not null order by start_ts",
                (meta_id,),
            ).fetchall()
        except sqlite3.DatabaseError as err:
            # A damaged page takes one series with it, the others are still good.
            print(f"{statistic_id}: unreadable, skipped ({err})", file=sys.stderr)
            continue
        if rows:
            recovered[statistic_id] = daily_changes(rows, TO_KWH[unit])
    return recovered


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    json.dump(recover(sys.argv[1]), sys.stdout, indent=0, sort_keys=True)
