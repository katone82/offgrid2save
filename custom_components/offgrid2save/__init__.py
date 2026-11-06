"""OffGrid2Save: compare electricity bills with what your plant measured."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from . import api
from .const import DOMAIN, PANEL_COMPONENT, PANEL_URL, SERVICE_RESCAN, STATIC_URL, VERSION
from .manager import BillManager

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.SENSOR]

type OffGrid2SaveConfigEntry = ConfigEntry[BillManager]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register what only has to exist once, surviving reloads of the entry."""
    api.async_register(hass)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), False)]
    )

    async def rescan(_call: ServiceCall) -> None:
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            await entry.runtime_data.async_rescan()

    hass.services.async_register(DOMAIN, SERVICE_RESCAN, rescan)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: OffGrid2SaveConfigEntry) -> bool:
    """Start watching bills and show the panel."""
    manager = BillManager(hass, entry)
    await manager.async_start()
    entry.runtime_data = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_COMPONENT,
        frontend_url_path=PANEL_URL,
        module_url=f"{STATIC_URL}/offgrid2save-panel.js?v={VERSION}",
        sidebar_title="OffGrid2Save",
        sidebar_icon="mdi:solar-power-variant",
        require_admin=False,
    )
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: OffGrid2SaveConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: OffGrid2SaveConfigEntry) -> bool:
    """Remove the panel and the sensors."""
    frontend.async_remove_panel(hass, PANEL_URL)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
