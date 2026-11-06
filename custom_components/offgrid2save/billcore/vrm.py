"""Turn VRM energy counters into the roles used for the comparison.

VRM reports each flow by origin and destination: P is solar, G grid, B battery and c
the consumers, so Pc is solar energy that went straight to the loads.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import date, timedelta

from .savings import Sources

ROLE_CODES: dict[str, tuple[str, ...]] = {
    "pv": ("Pb", "Pc", "Pg"),
    "grid_import": ("Gb", "Gc"),
    "grid_export": ("Bg", "Pg"),
    "consumption": ("Bc", "Gc", "Pc"),
    "battery_charge": ("Gb", "Pb"),
    "battery_discharge": ("Bc", "Bg"),
}
VRM_SOURCES = Sources(
    pv=("vrm:pv",),
    grid_import=("vrm:grid_import",),
    grid_export=("vrm:grid_export",),
    consumption_add=("vrm:consumption",),
    battery_charge=("vrm:battery_charge",),
    battery_discharge=("vrm:battery_discharge",),
)
MAX_DAYS_PER_REQUEST = 170  # VRM allows 180 at daily resolution
RECENT_DAYS = 2  # still arriving: a GX device that was offline uploads them later
EMPTY_RECHECK_DAYS = 7


def days_from_records(
    records: object, to_local_date: Callable[[float], date]
) -> dict[date, dict[str, float]]:
    """Sum VRM's daily records into roles.

    A day exists if any counter reports it: VRM leaves out the flows that never
    happen, and on a plant with no grid those are real zeros, not missing data. A day
    can hold two records: see split_at_clock_changes for why.
    """
    if not isinstance(records, Mapping):  # VRM answers with an empty list when it has nothing
        return {}
    flows: dict[date, dict[str, float]] = {}
    for code, series in records.items():
        for point in series or ():
            value = point[1] if len(point) > 1 else None
            if value is not None:
                day = flows.setdefault(to_local_date(point[0] / 1000), {})
                day[code] = day.get(code, 0.0) + float(value)
    return {
        day: {
            role: round(sum(values.get(code, 0.0) for code in codes), 3)
            for role, codes in ROLE_CODES.items()
        }
        for day, values in flows.items()
    }


def split_at_clock_changes(
    start: date, end: date, utc_offset: Callable[[date], timedelta]
) -> list[tuple[date, date]]:
    """Split a range of days so that each piece has one UTC offset at its midnights.

    VRM cuts "days" into blocks of exactly 24 hours counted from the start of the
    request. Across a clock change every later block starts an hour off midnight, and
    is labelled with the day before the one it mostly holds. Real data showed the
    whole end of October shifted by a day. On the day of the change the last block is
    cut short by the end of the request, so that day comes in two records.
    """
    pieces: list[tuple[date, date]] = []
    piece_start = start
    day = start
    while day < end:
        following = day + timedelta(days=1)
        if utc_offset(following) != utc_offset(day):
            pieces.append((piece_start, day))
            piece_start = following
        day = following
    pieces.append((piece_start, end))
    return pieces


def missing_ranges(
    known: Mapping[str, Mapping[str, float]],
    periods: Iterable[tuple[date, date]],
    yesterday: date,
) -> list[tuple[date, date]]:
    """Return the ranges to download, so that a new bill only costs the days it adds.

    Recent days are always read again, and so are empty ones for a while, because a
    GX device that was offline uploads its data when it comes back.
    """
    needed: set[date] = set()
    for start, end in periods:
        day = start
        while day <= min(end, yesterday):
            stored = known.get(day.isoformat())
            age = (yesterday - day).days
            if stored is None or age < RECENT_DAYS or (not stored and age < EMPTY_RECHECK_DAYS):
                needed.add(day)
            day += timedelta(days=1)

    ranges: list[tuple[date, date]] = []
    for day in sorted(needed):
        if (
            ranges
            and day == ranges[-1][1] + timedelta(days=1)
            and (day - ranges[-1][0]).days < MAX_DAYS_PER_REQUEST
        ):
            ranges[-1] = (ranges[-1][0], day)
        else:
            ranges.append((day, day))
    return ranges


def to_daily(known: Mapping[str, Mapping[str, float]]) -> dict[str, dict[date, float]]:
    """Convert the stored days to the form the comparison reads."""
    daily: dict[str, dict[date, float]] = {f"vrm:{role}": {} for role in ROLE_CODES}
    for day, roles in known.items():
        for role, kwh in roles.items():
            daily[f"vrm:{role}"][date.fromisoformat(day)] = kwh
    return daily
