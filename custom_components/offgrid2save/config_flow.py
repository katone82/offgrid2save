"""Configure where bills live and where energy data comes from."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
import voluptuous as vol

from .billcore.savings import (
    LAYOUT_SEPARATE,
    LAYOUT_THROUGH_PLANT,
    PRICE_METHOD_VARIABLE,
    PRICE_METHOD_WHOLE_HOME,
)
from .billcore.suggest import suggest_layout, suggest_sources
from .const import (
    CONF_BILLS_PATH,
    CONF_CONSUMPTION_ADD,
    CONF_DATA_SOURCE,
    CONF_EXPORT_PRICE,
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
    SOURCE_ROLES,
)
from .manager import resolve_bills_path
from .vrm import VrmAuthError, VrmClient, VrmError

_ENERGY_SENSORS = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="energy", multiple=True)
)
_TOKEN = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))


def _price_selector(unit: str, maximum: float, step: float) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _list_selector(options: list, key: str) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options, mode=selector.SelectSelectorMode.LIST, translation_key=key
        )
    )


_LAYOUT_SELECTOR = _list_selector([LAYOUT_THROUGH_PLANT, LAYOUT_SEPARATE], CONF_GRID_LAYOUT)
_PRICE_METHOD_SELECTOR = _list_selector(
    [PRICE_METHOD_WHOLE_HOME, PRICE_METHOD_VARIABLE], CONF_PRICE_METHOD
)
_DATA_SOURCE_SELECTOR = _list_selector(
    [DATA_SOURCE_VRM, DATA_SOURCE_ENTITIES], CONF_DATA_SOURCE
)


def _folder_schema(default: str) -> vol.Schema:
    return vol.Schema({vol.Required(CONF_BILLS_PATH, default=default): selector.TextSelector()})


def _vrm_schema(layout: str, *, token_required: bool) -> vol.Schema:
    token = vol.Required(CONF_VRM_TOKEN) if token_required else vol.Optional(CONF_VRM_TOKEN)
    return vol.Schema(
        {token: _TOKEN, vol.Required(CONF_GRID_LAYOUT, default=layout): _LAYOUT_SELECTOR}
    )


def _sources_schema(current: dict[str, Any]) -> vol.Schema:
    # Suggested values, not defaults: the form omits a field the user emptied, and
    # a default would silently put back the entity they just removed.
    return vol.Schema(
        {
            vol.Required(
                CONF_GRID_LAYOUT, default=current.get(CONF_GRID_LAYOUT, LAYOUT_THROUGH_PLANT)
            ): _LAYOUT_SELECTOR,
            **{
                vol.Optional(
                    role, description={"suggested_value": current.get(role, [])}
                ): _ENERGY_SENSORS
                for role in SOURCE_ROLES
            },
        }
    )


def _pricing_schema(current: dict[str, Any]) -> vol.Schema:
    method = (
        PRICE_METHOD_VARIABLE
        if current.get(CONF_PRICE_METHOD) == PRICE_METHOD_VARIABLE
        else PRICE_METHOD_WHOLE_HOME
    )
    schema: dict = {
        vol.Required(CONF_PRICE_METHOD, default=method): _PRICE_METHOD_SELECTOR,
        vol.Required(
            CONF_TAX_RATE, default=current.get(CONF_TAX_RATE, DEFAULT_TAX_RATE)
        ): _price_selector("%", 50, 0.5),
        vol.Optional(
            CONF_EXPORT_PRICE, default=current.get(CONF_EXPORT_PRICE, 0.0)
        ): _price_selector("€/kWh", 2, 0.001),
    }
    manual = current.get(CONF_MANUAL_PRICE)
    key = (
        vol.Optional(CONF_MANUAL_PRICE, description={"suggested_value": manual})
        if manual
        else vol.Optional(CONF_MANUAL_PRICE)
    )
    schema[key] = _price_selector("€/kWh", 2, 0.001)
    return vol.Schema(schema)


def _check_folder(hass: HomeAssistant, raw: str) -> str | None:
    """Return an error key, or None if the folder can be used."""
    path = resolve_bills_path(hass, raw.strip())
    if path is None:
        return "path_not_allowed"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".offgrid2save_write_test"
        probe.write_text("")
        probe.unlink()
    except OSError:
        return "path_not_writable"
    return None


def _check_sources(data: dict[str, Any]) -> str | None:
    """Savings need the consumption, read from a meter or derived from an energy balance."""
    if data.get(CONF_CONSUMPTION_ADD):
        return None
    if not data.get(CONF_PV):
        return "consumption_or_grid_required"
    # A balance needs the grid term too, unless the grid never reaches the plant.
    if data.get(CONF_GRID_LAYOUT) != LAYOUT_SEPARATE and not data.get(CONF_GRID_IMPORT):
        return "consumption_or_grid_required"
    return None


class _SharedSteps:
    """The steps a first setup and later changes have in common."""

    _data: dict[str, Any]
    _sites: dict[str, str]
    hass: HomeAssistant

    @property
    def _current(self) -> dict[str, Any]:
        raise NotImplementedError

    def _finish(self) -> ConfigFlowResult:
        raise NotImplementedError

    def _suggested_layout(self) -> str:
        return self._current.get(CONF_GRID_LAYOUT) or suggest_layout(
            {state.entity_id: state.state for state in self.hass.states.async_all("select")}
        )

    async def async_step_source(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_DATA_SOURCE] = user_input[CONF_DATA_SOURCE]
            if user_input[CONF_DATA_SOURCE] == DATA_SOURCE_VRM:
                return await self.async_step_vrm()
            return await self.async_step_sources()
        default = self._current.get(CONF_DATA_SOURCE, DATA_SOURCE_VRM)
        if self._current.get(CONF_PV) and CONF_DATA_SOURCE not in self._current:
            default = DATA_SOURCE_ENTITIES
        return self.async_show_form(
            step_id="source",
            data_schema=vol.Schema(
                {vol.Required(CONF_DATA_SOURCE, default=default): _DATA_SOURCE_SELECTOR}
            ),
        )

    async def async_step_vrm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        saved_token = self._current.get(CONF_VRM_TOKEN)
        if user_input is not None:
            token = (user_input.get(CONF_VRM_TOKEN) or saved_token or "").strip()
            self._data[CONF_GRID_LAYOUT] = user_input[CONF_GRID_LAYOUT]
            try:
                sites = await VrmClient(self.hass, token).async_installations()
            except VrmAuthError:
                errors[CONF_VRM_TOKEN] = "invalid_token"
            except VrmError:
                errors["base"] = "cannot_connect"
            else:
                if not sites:
                    errors["base"] = "no_installations"
                else:
                    self._data[CONF_VRM_TOKEN] = token
                    self._sites = {str(site["idSite"]): site.get("name") or str(site["idSite"]) for site in sites}
                    if len(sites) == 1:
                        return await self.async_step_vrm_site(
                            {CONF_VRM_SITE: next(iter(self._sites))}
                        )
                    return await self.async_step_vrm_site()
        return self.async_show_form(
            step_id="vrm",
            data_schema=_vrm_schema(self._suggested_layout(), token_required=not saved_token),
            errors=errors,
        )

    async def async_step_vrm_site(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            site = user_input[CONF_VRM_SITE]
            self._data[CONF_VRM_SITE] = int(site)
            self._data[CONF_VRM_SITE_NAME] = self._sites[site]
            return await self.async_step_pricing()
        options = [
            selector.SelectOptionDict(value=site, label=name) for site, name in self._sites.items()
        ]
        return self.async_show_form(
            step_id="vrm_site",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_VRM_SITE): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options)
                    )
                }
            ),
        )

    async def async_step_sources(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            error = _check_sources(user_input)
            if error:
                errors["base"] = error
            else:
                self._data.update(user_input)
                return await self.async_step_pricing()
        current = self._current
        if not any(current.get(role) for role in SOURCE_ROLES):
            current = {
                **suggest_sources(self.hass.states.async_entity_ids("sensor")),
                CONF_GRID_LAYOUT: self._suggested_layout(),
            }
        return self.async_show_form(
            step_id="sources", data_schema=_sources_schema(user_input or current), errors=errors
        )

    async def async_step_pricing(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self._finish()
        return self.async_show_form(step_id="pricing", data_schema=_pricing_schema(self._current))


class OffGrid2SaveConfigFlow(_SharedSteps, ConfigFlow, domain=DOMAIN):
    """Short steps: folder, source of the energy data, prices."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._sites: dict[str, str] = {}

    @property
    def _current(self) -> dict[str, Any]:
        return {}

    def _finish(self) -> ConfigFlowResult:
        return self.async_create_entry(title="OffGrid2Save", data=self._data)

    @staticmethod
    @callback
    def async_get_options_flow(_entry: ConfigEntry) -> OptionsFlow:
        return OffGrid2SaveOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self.hass.async_add_executor_job(
                _check_folder, self.hass, user_input[CONF_BILLS_PATH]
            )
            if error:
                errors[CONF_BILLS_PATH] = error
            else:
                self._data.update(user_input)
                return await self.async_step_source()
        return self.async_show_form(
            step_id="user", data_schema=_folder_schema(DEFAULT_BILLS_PATH), errors=errors
        )


class OffGrid2SaveOptionsFlow(_SharedSteps, OptionsFlow):
    """Change the same things later, for instance after replacing hardware."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._sites: dict[str, str] = {}

    @property
    def _current(self) -> dict[str, Any]:
        return dict(self.config_entry.options or self.config_entry.data)

    def _finish(self) -> ConfigFlowResult:
        return self.async_create_entry(data=self._data)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self.hass.async_add_executor_job(
                _check_folder, self.hass, user_input[CONF_BILLS_PATH]
            )
            if error:
                errors[CONF_BILLS_PATH] = error
            else:
                self._data.update(user_input)
                return await self.async_step_source()
        return self.async_show_form(
            step_id="init",
            data_schema=_folder_schema(self._current.get(CONF_BILLS_PATH, DEFAULT_BILLS_PATH)),
            errors=errors,
        )
