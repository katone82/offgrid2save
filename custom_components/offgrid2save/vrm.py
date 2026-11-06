"""Read a plant's energy from the VRM portal, keeping what was already downloaded."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import date, datetime, timedelta
import logging

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .billcore.vrm import days_from_records, missing_ranges, split_at_clock_changes, to_daily
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
VRM_URL = "https://vrmapi.victronenergy.com/v2"
TIMEOUT = aiohttp.ClientTimeout(total=30)
MAX_WAIT_SECONDS = 30

STATUS_OK = "ok"
STATUS_AUTH = "auth_error"
STATUS_UNREACHABLE = "unreachable"


class VrmAuthError(Exception):
    """VRM refused the token."""


class VrmError(Exception):
    """VRM could not be reached or gave an unusable answer."""


class VrmClient:
    """The few calls needed from the VRM API."""

    def __init__(self, hass: HomeAssistant, token: str) -> None:
        self._session = async_get_clientsession(hass)
        self._headers = {"x-authorization": f"Token {token}"}

    async def _get(self, path: str, params: dict | None = None) -> dict:
        for attempt in (1, 2):
            try:
                async with self._session.get(
                    VRM_URL + path, headers=self._headers, params=params, timeout=TIMEOUT
                ) as response:
                    if response.status in (401, 403):
                        raise VrmAuthError(f"HTTP {response.status}")
                    if response.status == 429 and attempt == 1:
                        wait = min(int(response.headers.get("Retry-After", "5")), MAX_WAIT_SECONDS)
                        await asyncio.sleep(wait)
                        continue
                    if response.status != 200:
                        raise VrmError(f"HTTP {response.status}")
                    return await response.json()
            except (aiohttp.ClientError, TimeoutError, ValueError) as err:
                raise VrmError(str(err) or type(err).__name__) from err
        raise VrmError("rate limited")

    async def async_installations(self) -> list[dict]:
        """List the plants this token can read."""
        user = (await self._get("/users/me"))["user"]["id"]
        return (await self._get(f"/users/{user}/installations")).get("records", [])

    async def async_days(self, site: int, start: date, end: date) -> dict[date, dict[str, float]]:
        """Download energy per day, as roles, for a range of whole days."""

        def utc_offset(day: date) -> timedelta:
            return dt_util.start_of_local_day(day).utcoffset()

        def to_local_date(timestamp: float) -> date:
            return dt_util.as_local(datetime.fromtimestamp(timestamp, dt_util.UTC)).date()

        found: dict[date, dict[str, float]] = {}
        for piece_start, piece_end in split_at_clock_changes(start, end, utc_offset):
            reply = await self._get(
                f"/installations/{site}/stats",
                {
                    "type": "kwh",
                    "interval": "days",
                    "start": int(dt_util.start_of_local_day(piece_start).timestamp()),
                    "end": int(
                        dt_util.start_of_local_day(piece_end + timedelta(days=1)).timestamp()
                    ),
                },
            )
            found.update(days_from_records(reply.get("records"), to_local_date))
        return {day: roles for day, roles in found.items() if start <= day <= end}


class VrmHistory:
    """Downloaded days, stored so that a new bill only fetches what it adds."""

    def __init__(self, hass: HomeAssistant, token: str, site: int) -> None:
        self._client = VrmClient(hass, token)
        self._site = site
        self._store: Store[dict] = Store(hass, 1, f"{DOMAIN}.vrm_{site}")
        self._days: dict[str, dict[str, float]] = {}
        self.status = STATUS_OK
        self.last_download: str | None = None

    async def async_load(self) -> None:
        """Load what was downloaded before."""
        self._days = (await self._store.async_load() or {}).get("days", {})

    async def async_daily(
        self, periods: Iterable[tuple[date, date]], yesterday: date
    ) -> dict[str, dict[date, float]]:
        """Fetch what is missing for these periods, then return everything known.

        When VRM cannot be reached the comparison goes on with the stored days: the
        status lets the panel say so, and the next refresh tries again.
        """
        changed = False
        try:
            for start, end in missing_ranges(self._days, periods, yesterday):
                found = await self._client.async_days(self._site, start, end)
                day = start
                while day <= end:
                    self._days[day.isoformat()] = found.get(day, {})
                    day += timedelta(days=1)
                changed = True
                self.last_download = dt_util.utcnow().isoformat(timespec="seconds")
            self.status = STATUS_OK
        except VrmAuthError as err:
            _LOGGER.warning("VRM refused the access token: %s", err)
            self.status = STATUS_AUTH
        except VrmError as err:
            _LOGGER.warning("Cannot read from VRM, using stored data: %s", err)
            self.status = STATUS_UNREACHABLE
        if changed:
            await self._store.async_save({"days": self._days})
        return to_daily(self._days)
