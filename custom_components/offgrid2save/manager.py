"""Watch the bills folder, read new bills and keep the comparison up to date."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
import hashlib
import json
import logging
from pathlib import Path
import re

from homeassistant.components import persistent_notification
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util, slugify

from .billcore.extract import match_score, split_lines
from .billcore.fields import FIELDS
from .billcore.learn import add_builtin_rules, learn_template, slug
from .billcore.pdf_text import UnreadablePdf, pdf_to_text
from .billcore.pipeline import (
    STATUS_IGNORED,
    STATUS_LEARN,
    STATUS_OK,
    STATUS_REVIEW,
    STATUS_UNREADABLE,
    read_bill,
    reading_to_store,
    values_from_store,
)
from .billcore.savings import (
    LAYOUT_THROUGH_PLANT,
    PRICE_ALL_IN,
    PRICE_MANUAL,
    PRICE_METHOD_VARIABLE,
    PRICE_METHOD_WHOLE_HOME,
    PRICE_PREVIOUS,
    PRICE_VARIABLE,
    Sources,
    aggregate_period,
    compute_comparison,
    covered_days,
    find_overlaps,
    find_superseded,
    merge_daily,
    resolve_price,
)
from .billcore.vrm import VRM_SOURCES
from .const import (
    CONF_BATTERY_CHARGE,
    CONF_BATTERY_DISCHARGE,
    CONF_BILLS_PATH,
    CONF_CONSUMPTION_ADD,
    CONF_CONSUMPTION_SUBTRACT,
    CONF_DATA_SOURCE,
    CONF_EXPORT_PRICE,
    CONF_GRID_EXPORT,
    CONF_GRID_IMPORT,
    CONF_GRID_LAYOUT,
    CONF_MANUAL_PRICE,
    CONF_PRICE_METHOD,
    CONF_PV,
    CONF_TAX_RATE,
    CONF_VRM_SITE,
    CONF_VRM_SITE_NAME,
    CONF_VRM_TOKEN,
    DATA_SOURCE_ENTITIES,
    DATA_SOURCE_VRM,
    DEFAULT_BILLS_PATH,
    DEFAULT_TAX_RATE,
    DOMAIN,
    EVENT_BILL_PROCESSED,
    HISTORY_FILE,
    TEMPLATES_DIR,
)

from .vrm import STATUS_AUTH, STATUS_OK, VrmHistory

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(minutes=5)
STATISTICS_LOOKBACK = timedelta(days=5 * 366)
STORAGE_VERSION = 1
BUILTIN_TEMPLATES = Path(__file__).parent / "templates"
_ACTION_NEEDED = (STATUS_LEARN, STATUS_REVIEW, STATUS_UNREADABLE)


class BillNotFound(Exception):
    """The requested bill does not exist."""


def resolve_bills_path(hass: HomeAssistant, raw: str) -> Path | None:
    """Return the folder if Home Assistant may use it, None otherwise."""
    path = Path(raw)
    if not path.is_absolute():
        path = Path(hass.config.path(raw))
    path = path.resolve()
    inside_config = path.is_relative_to(Path(hass.config.config_dir).resolve())
    return path if inside_config or hass.config.is_allowed_path(str(path)) else None


def _load_templates(user_dir: Path) -> tuple[list[dict], dict]:
    """Load built-in templates, overridden by those learned on this installation."""
    templates: dict[str, dict] = {}
    generic: dict = {}
    for folder in (BUILTIN_TEMPLATES, user_dir):
        if not folder.is_dir():
            continue
        for file in sorted(folder.glob("*.json")):
            try:
                template = json.loads(file.read_text("utf-8"))
                template_id = template["id"]
            except (OSError, ValueError, KeyError, TypeError) as err:
                # A hand-edited or shared template must not stop the other bills.
                _LOGGER.warning("Ignoring template %s: %s", file.name, err)
                continue
            if template_id == "generic_it":
                generic = template
            elif template_id in templates:
                templates[template_id] = add_builtin_rules(template, templates[template_id])
            else:
                templates[template_id] = template
    return list(templates.values()), generic


def _load_history(path: Path) -> dict[str, dict[date, float]]:
    """Load energy recovered from an old database, see tools/recover_history.py."""
    if not path.is_file():
        return {}
    try:
        return {
            entity: {date.fromisoformat(day): float(kwh) for day, kwh in days.items()}
            for entity, days in json.loads(path.read_text("utf-8")).items()
        }
    except (OSError, ValueError, AttributeError, TypeError) as err:
        _LOGGER.warning("Ignoring %s: %s", path.name, err)
        return {}


def _file_key(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_size}:{int(stat.st_mtime)}"


def _sources_from_options(options: dict) -> Sources:
    def role(key: str) -> tuple[str, ...]:
        return tuple(options.get(key) or ())

    return Sources(
        pv=role(CONF_PV),
        grid_import=role(CONF_GRID_IMPORT),
        grid_export=role(CONF_GRID_EXPORT),
        consumption_add=role(CONF_CONSUMPTION_ADD),
        consumption_subtract=role(CONF_CONSUMPTION_SUBTRACT),
        battery_charge=role(CONF_BATTERY_CHARGE),
        battery_discharge=role(CONF_BATTERY_DISCHARGE),
    )


class BillManager(DataUpdateCoordinator[dict]):
    """Own the bills, and publish the overview everything else displays."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=None)
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.bills")
        self._bills: dict[str, dict] = {}
        self._scan_lock = asyncio.Lock()
        self._templates: list[dict] = []
        self._generic: dict = {}
        self._pending_events: list[str] = []
        self._copies: dict[str, str] = {}
        self._vrm: VrmHistory | None = None
        self._templates_dir = Path(hass.config.path(TEMPLATES_DIR))

    @property
    def options(self) -> dict:
        # Options replace the initial setup as a whole: merging the two would
        # bring back anything the user has since removed.
        return dict(self.config_entry.options or self.config_entry.data)

    @property
    def bills_dir(self) -> Path:
        raw = self.options.get(CONF_BILLS_PATH, DEFAULT_BILLS_PATH)
        return resolve_bills_path(self.hass, raw) or Path(self.hass.config.path(DEFAULT_BILLS_PATH))

    async def async_start(self) -> None:
        """Load stored bills and start watching."""
        stored = await self._store.async_load() or {}
        self._bills = stored.get("bills", {})
        options = self.options
        if options.get(CONF_DATA_SOURCE) == DATA_SOURCE_VRM:
            self._vrm = VrmHistory(self.hass, options[CONF_VRM_TOKEN], options[CONF_VRM_SITE])
            await self._vrm.async_load()
        self._templates, self._generic = await self.hass.async_add_executor_job(
            _load_templates, self._templates_dir
        )
        await self.async_config_entry_first_refresh()

        entry = self.config_entry
        entry.async_on_unload(
            async_track_time_interval(self.hass, self._async_periodic_scan, SCAN_INTERVAL)
        )
        # Daily statistics of a day are complete once it is over: this adds the
        # new day to the period not yet billed.
        entry.async_on_unload(
            async_track_time_change(self.hass, self._async_daily, hour=0, minute=30, second=0)
        )

    async def _async_update_data(self) -> dict:
        await self._async_scan()
        return await self._async_compute()

    async def _async_periodic_scan(self, _now: datetime) -> None:
        if await self._async_scan():
            await self.async_refresh()

    @callback
    def _async_daily(self, _now: datetime) -> None:
        self.hass.async_create_task(self.async_refresh())

    async def async_rescan(self) -> None:
        """Check the folder now."""
        await self.async_refresh()

    # ------------------------------------------------------------------ folder

    def _list_pdfs(self) -> dict[str, str]:
        folder = self.bills_dir
        folder.mkdir(parents=True, exist_ok=True)
        return {
            file.name: _file_key(file)
            for file in folder.iterdir()
            if file.is_file() and file.suffix.lower() == ".pdf"
        }

    def _read_one(self, name: str, confirmed: dict) -> tuple[str, dict, str]:
        """Hash and read one file. Runs in the executor."""
        path = self.bills_dir / name
        data = path.read_bytes()
        try:
            text = pdf_to_text(data)
        except UnreadablePdf as err:
            _LOGGER.warning("Cannot read %s: %s", name, err)
            text = ""
        reading = read_bill(text, self._templates, self._generic, confirmed=confirmed)
        return hashlib.sha256(data).hexdigest()[:16], reading_to_store(reading), _file_key(path)

    async def _async_scan(self) -> bool:
        """Read files that are new or changed. Returns whether anything changed."""
        async with self._scan_lock:
            files = await self.hass.async_add_executor_job(self._list_pdfs)
            changed = False
            known = {bill["file"]: bill for bill in self._bills.values()}

            fresh: list[str] = []
            for name, key in files.items():
                current = known.get(name)
                if (current and current.get("file_key") == key) or self._copies.get(name) == key:
                    continue
                try:
                    bill_id, reading, file_key = await self.hass.async_add_executor_job(
                        self._read_one, name, current.get("confirmed", {}) if current else {}
                    )
                    if current and current["id"] != bill_id:
                        # Same name, new content: the old confirmations do not apply.
                        self._bills.pop(current["id"], None)
                        persistent_notification.async_dismiss(
                            self.hass, f"{DOMAIN}_{current['id']}"
                        )
                        current = None
                        bill_id, reading, file_key = await self.hass.async_add_executor_job(
                            self._read_one, name, {}
                        )
                except OSError as err:
                    # Removed or still being written: the next scan tries again.
                    _LOGGER.debug("Skipping %s for now: %s", name, err)
                    continue
                # Same content under another name: a copy if the original is still
                # there, otherwise a rename that must keep what the user confirmed.
                twin = None if current else self._bills.get(bill_id)
                if twin and twin["file"] != name and twin["file"] in files:
                    _LOGGER.debug("%s is a copy of %s, skipped", name, twin["file"])
                    self._copies[name] = key
                    continue
                previous = current or twin or {}
                if twin:
                    _, reading, file_key = await self.hass.async_add_executor_job(
                        self._read_one, name, twin.get("confirmed", {})
                    )
                self._bills[bill_id] = {
                    "id": bill_id,
                    "file": name,
                    "file_key": file_key,
                    "confirmed": previous.get("confirmed", {}),
                    "supplier_name": previous.get("supplier_name"),
                    "processed_at": dt_util.utcnow().isoformat(timespec="seconds"),
                    **reading,
                }
                if not twin:
                    fresh.append(bill_id)
                changed = True

            for bill_id, bill in list(self._bills.items()):
                if bill["file"] not in files:
                    del self._bills[bill_id]
                    persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_{bill_id}")
                    changed = True

            if changed:
                await self._store.async_save({"bills": self._bills})
            for bill_id in fresh:
                self._announce_action_needed(self._bills[bill_id])
            self._pending_events.extend(fresh)
            return changed

    @callback
    def _announce_action_needed(self, bill: dict) -> None:
        """Tell the user a bill waits for them, it would otherwise sit there unseen."""
        notification_id = f"{DOMAIN}_{bill['id']}"
        if bill["status"] not in _ACTION_NEEDED:
            persistent_notification.async_dismiss(self.hass, notification_id)
            return
        persistent_notification.async_create(
            self.hass,
            f"**{bill['file']}**: [apri OffGrid2Save](/offgrid2save) per controllare i valori letti. "
            "Dopo la conferma le bollette successive di questo fornitore vengono lette in automatico.",
            title="Bolletta da confermare",
            notification_id=notification_id,
        )

    async def _async_reread_unconfirmed(self) -> None:
        """Read again everything not vouched for: a new template may now fit it."""
        for bill in list(self._bills.values()):
            if bill["status"] == STATUS_OK and bill.get("confirmed"):
                continue
            _, reading, _ = await self.hass.async_add_executor_job(
                self._read_one, bill["file"], bill.get("confirmed", {})
            )
            bill.update(reading)
            self._announce_action_needed(bill)

    # ---------------------------------------------------------------- learning

    def _bill(self, bill_id: str) -> dict:
        try:
            return self._bills[bill_id]
        except KeyError as err:
            raise BillNotFound(bill_id) from err

    async def async_detail(self, bill_id: str) -> dict:
        """Return a bill with its text, for the review screen."""
        bill = self._bill(bill_id)

        def read_lines() -> list[str]:
            try:
                return split_lines(pdf_to_text((self.bills_dir / bill["file"]).read_bytes()))[:600]
            except (UnreadablePdf, OSError):
                return []

        return {**bill, "text_lines": await self.hass.async_add_executor_job(read_lines)}

    async def async_confirm(self, bill_id: str, supplier: str, values: dict) -> dict:
        """Store what a person confirmed, and learn the layout from it."""
        bill = self._bill(bill_id)
        clean = {
            key: value for key, value in values.items() if key in FIELDS and value not in (None, "")
        }
        base_id = bill.get("template_id") or slug(supplier)
        base = next((item for item in self._templates if item["id"] == base_id), None)

        def learn() -> tuple[dict | None, list[str], bool]:
            try:
                text = pdf_to_text((self.bills_dir / bill["file"]).read_bytes())
            except (UnreadablePdf, OSError):
                text = ""
            if not text.strip():
                return None, [], False
            template, unlocated = learn_template(supplier, clean, text, base=base)
            recognizable = match_score(template, text) > 0
            self._templates_dir.mkdir(parents=True, exist_ok=True)
            (self._templates_dir / f"{template['id']}.json").write_text(
                json.dumps(template, ensure_ascii=False, indent=2), "utf-8"
            )
            return template, unlocated, recognizable

        template, unlocated, recognizable = await self.hass.async_add_executor_job(learn)
        bill["confirmed"] = clean
        bill["supplier_name"] = supplier
        if template:
            self._templates, self._generic = await self.hass.async_add_executor_job(
                _load_templates, self._templates_dir
            )
        await self._async_reread_unconfirmed()
        _, reading, _ = await self.hass.async_add_executor_job(self._read_one, bill["file"], clean)
        bill.update(reading)
        self._announce_action_needed(bill)
        await self._store.async_save({"bills": self._bills})
        await self.async_refresh()
        return {
            "status": bill["status"],
            "template_id": template["id"] if template else None,
            "unlocated": unlocated,
            "recognizable": recognizable,
        }

    async def async_add_upload(self, filename: str, data: bytes) -> dict:
        """Save a PDF into the bills folder and process it at once."""
        digest = hashlib.sha256(data).hexdigest()[:16]
        if digest in self._bills:
            return {"id": digest, "duplicate": True, "status": self._bills[digest]["status"]}

        def write() -> None:
            folder = self.bills_dir
            folder.mkdir(parents=True, exist_ok=True)
            stem = slugify(re.sub(r"\.pdf$", "", filename, flags=re.I)) or "bolletta"
            target = folder / f"{stem}.pdf"
            suffix = 1
            while target.exists():
                target = folder / f"{stem}_{suffix}.pdf"
                suffix += 1
            target.write_bytes(data)

        await self.hass.async_add_executor_job(write)
        await self.async_refresh()
        bill = self._bills.get(digest)
        return {"id": digest, "duplicate": False, "status": bill["status"] if bill else None}

    # ------------------------------------------------------------- comparison

    async def _async_read_daily(
        self, sources: Sources, start: date, end: date
    ) -> dict[str, dict[date, float]]:
        ids = sources.all_ids()
        if not ids:
            return {}
        history = await self.hass.async_add_executor_job(
            _load_history, Path(self.hass.config.path(HISTORY_FILE))
        )
        rows = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            dt_util.start_of_local_day(start),
            dt_util.start_of_local_day(end + timedelta(days=1)),
            ids,
            "day",
            {"energy": "kWh"},
            {"change"},
        )
        statistics = {
            entity: {
                dt_util.as_local(dt_util.utc_from_timestamp(row["start"])).date(): row["change"]
                for row in entity_rows
                if row.get("change") is not None
            }
            for entity, entity_rows in rows.items()
        }
        return merge_daily({k: v for k, v in history.items() if k in ids}, statistics)

    async def _async_compute(self) -> dict:
        options = self.options
        sources = VRM_SOURCES if self._vrm else _sources_from_options(options)
        manual_price = options.get(CONF_MANUAL_PRICE) or None
        export_price = float(options.get(CONF_EXPORT_PRICE) or 0.0)
        tax_rate = float(options.get(CONF_TAX_RATE, DEFAULT_TAX_RATE)) / 100
        layout = options.get(CONF_GRID_LAYOUT, LAYOUT_THROUGH_PLANT)
        price_method = (
            PRICE_METHOD_VARIABLE
            if options.get(CONF_PRICE_METHOD) == PRICE_METHOD_VARIABLE
            else PRICE_METHOD_WHOLE_HOME
        )
        yesterday = dt_util.now().date() - timedelta(days=1)

        usable: list[dict] = []
        for bill in self._bills.values():
            if bill["status"] != STATUS_OK:
                continue
            typed = values_from_store(bill["values"])
            usable.append(
                {
                    "id": bill["id"],
                    "period_start": typed["period_start"],
                    "period_end": typed["period_end"],
                    "issue_date": typed.get("issue_date"),
                    "typed": typed,
                    "bill": bill,
                }
            )
        usable.sort(key=lambda item: item["period_start"])

        # Read everything there is, not only the billed periods: the plant's figures
        # are worth showing even when no bill overlaps them.
        last_end = max((item["period_end"] for item in usable), default=None)
        if self._vrm:
            # What each bill adds is downloaded here, once: this is what makes a new
            # bill bring its own month of plant data along.
            periods = [(item["period_start"], item["period_end"]) for item in usable]
            if last_end is not None:
                periods.append((last_end + timedelta(days=1), yesterday))
            daily = await self._vrm.async_daily(periods, yesterday)
            self._announce_vrm_status()
        else:
            read_from = yesterday - STATISTICS_LOOKBACK
            if usable:
                read_from = min(read_from, usable[0]["period_start"])
            daily = await self._async_read_daily(
                sources, read_from, max(last_end or yesterday, yesterday)
            )

        superseded = find_superseded(usable)
        overlapping = find_overlaps(usable, superseded)

        comparisons: dict[str, dict] = {}
        last_price: float | None = None
        last_price_source: str | None = None
        reliable_price: float | None = None
        for item in usable:
            price, source = resolve_price(
                item["typed"], manual_price=manual_price, default_tax_rate=tax_rate
            )
            # A price from an earlier bill is closer to the truth than an average
            # inflated by fixed charges, even after a change of supplier.
            if (price is None or source == PRICE_ALL_IN) and reliable_price is not None:
                price, source = reliable_price, PRICE_PREVIOUS
            energy = aggregate_period(daily, sources, item["period_start"], item["period_end"])
            comparisons[item["id"]] = compute_comparison(
                item["typed"],
                energy,
                price=price,
                price_source=source,
                export_price=export_price,
                layout=layout,
                whole_home=price_method == PRICE_METHOD_WHOLE_HOME,
            )
            if price is not None and item["id"] not in superseded:
                # Days not billed yet are worth what the latest bill's kWh came to.
                last_price = comparisons[item["id"]]["price_eur_kwh"]
                last_price_source = comparisons[item["id"]]["price_source"]
                if source in (PRICE_MANUAL, PRICE_VARIABLE):
                    reliable_price = price

        counted = [item for item in usable if item["id"] not in superseded]
        totals = {
            "bills": len(counted),
            "savings_eur": 0.0,
            "cost_eur": 0.0,
            "cost_without_plant_eur": 0.0,
            "billed_kwh": 0.0,
            "partial_bills": 0,
        }
        for item in counted:
            comparison = comparisons[item["id"]]
            if comparison["savings_eur"] is None:
                totals["partial_bills"] += 1
                continue
            # Only bills with savings enter the totals, so that "what you paid"
            # and "what you would have paid" describe the same bills.
            totals["savings_eur"] += comparison["savings_eur"]
            totals["cost_eur"] += float(item["typed"]["total_cost"])
            totals["cost_without_plant_eur"] += comparison["cost_without_plant_eur"] or 0.0
            totals["billed_kwh"] += float(item["typed"]["consumption_kwh"])
            if comparison["partial"]:
                totals["partial_bills"] += 1
        totals = {key: round(value, 2) for key, value in totals.items()}

        current = None
        if last_end is not None and last_end < yesterday:
            energy = aggregate_period(daily, sources, last_end + timedelta(days=1), yesterday)
            current = compute_comparison(
                {},
                energy,
                price=last_price,
                price_source=last_price_source,
                export_price=export_price,
                layout=layout,
            )

        plant = None
        measured_days = [day for day in covered_days(daily, sources) if day <= yesterday]
        if measured_days:
            energy = aggregate_period(daily, sources, measured_days[0], measured_days[-1])
            plant = compute_comparison(
                {},
                energy,
                price=last_price,
                price_source=last_price_source,
                export_price=export_price,
                layout=layout,
            )

        bills_out = sorted(
            (self._bill_output(bill, comparisons, superseded, overlapping) for bill in self._bills.values()),
            key=lambda item: (item["values"].get("period_start") or "", item["file"]),
        )
        self._fire_events(bills_out)
        return {
            "bills": bills_out,
            "totals": totals,
            "current_period": current,
            "plant": plant,
            "to_review": sum(1 for bill in self._bills.values() if bill["status"] in _ACTION_NEEDED),
            "ignored": sum(1 for bill in self._bills.values() if bill["status"] == STATUS_IGNORED),
            "bills_path": str(self.bills_dir),
            "layout": layout,
            "price_method": price_method,
            "data_source": options.get(CONF_DATA_SOURCE, DATA_SOURCE_ENTITIES),
            "vrm": {
                "status": self._vrm.status,
                "site": options.get(CONF_VRM_SITE_NAME),
                "last_download": self._vrm.last_download,
            }
            if self._vrm
            else None,
            "sources": {key: list(value) for key, value in vars(sources).items()},
            "templates": [
                {"id": item["id"], "name": item.get("name"), "learned": bool(item.get("learned"))}
                for item in self._templates
            ],
            "updated_at": dt_util.utcnow().isoformat(timespec="seconds"),
        }

    @callback
    def _announce_vrm_status(self) -> None:
        """A refused token needs the user, and it would otherwise only show in the panel."""
        notification_id = f"{DOMAIN}_vrm_auth"
        if self._vrm.status == STATUS_AUTH:
            persistent_notification.async_create(
                self.hass,
                "VRM ha rifiutato il token di accesso: i nuovi dati dell'impianto non vengono "
                "scaricati. Creane uno nuovo su VRM e aggiornalo nelle opzioni dell'integrazione.",
                title="OffGrid2Save: token VRM non valido",
                notification_id=notification_id,
            )
        elif self._vrm.status == STATUS_OK:
            persistent_notification.async_dismiss(self.hass, notification_id)

    @staticmethod
    def _bill_output(bill: dict, comparisons: dict, superseded: set, overlapping: set) -> dict:
        return {
            "id": bill["id"],
            "file": bill["file"],
            "status": bill["status"],
            "supplier": bill.get("supplier") or bill.get("supplier_name"),
            "template_id": bill.get("template_id"),
            "values": bill["values"],
            "issues": bill["issues"],
            "confirmed": bool(bill.get("confirmed")),
            "superseded": bill["id"] in superseded,
            "overlapping": bill["id"] in overlapping,
            "comparison": comparisons.get(bill["id"]),
        }

    @callback
    def _fire_events(self, bills: list[dict]) -> None:
        pending = set(self._pending_events)
        self._pending_events.clear()
        for bill in bills:
            if bill["id"] not in pending:
                continue
            comparison = bill["comparison"] or {}
            self.hass.bus.async_fire(
                EVENT_BILL_PROCESSED,
                {
                    "bill_id": bill["id"],
                    "file": bill["file"],
                    "status": bill["status"],
                    "supplier": bill["supplier"],
                    "period_start": bill["values"].get("period_start"),
                    "period_end": bill["values"].get("period_end"),
                    "total_cost": bill["values"].get("total_cost"),
                    "savings_eur": comparison.get("savings_eur"),
                },
            )
