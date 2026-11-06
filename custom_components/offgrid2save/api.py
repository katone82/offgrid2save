"""The API the panel talks to."""

from __future__ import annotations

from http import HTTPStatus

from aiohttp import web
from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .billcore.fields import FIELDS
from .const import DOMAIN, MAX_UPLOAD_BYTES, UPLOAD_URL
from .manager import BillManager, BillNotFound

ERROR_NOT_READY = "not_ready"
ERROR_NOT_FOUND = "not_found"


def _manager(hass: HomeAssistant) -> BillManager | None:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    return entries[0].runtime_data if entries else None


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the websocket commands and the upload endpoint."""
    websocket_api.async_register_command(hass, ws_overview)
    websocket_api.async_register_command(hass, ws_detail)
    websocket_api.async_register_command(hass, ws_confirm)
    websocket_api.async_register_command(hass, ws_rescan)
    hass.http.register_view(UploadView())


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/overview"})
@callback
def ws_overview(hass, connection, msg) -> None:
    """Return everything the dashboard shows."""
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], ERROR_NOT_READY, "OffGrid2Save is not set up")
        return
    connection.send_result(msg["id"], manager.data)


# Details expose the full text of a bill and confirming changes what gets
# counted, so unlike the dashboard these are for administrators only.
@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/detail", vol.Required("bill_id"): cv.string}
)
@websocket_api.async_response
async def ws_detail(hass, connection, msg) -> None:
    """Return a bill with its text, for review."""
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], ERROR_NOT_READY, "OffGrid2Save is not set up")
        return
    try:
        connection.send_result(msg["id"], await manager.async_detail(msg["bill_id"]))
    except BillNotFound:
        connection.send_error(msg["id"], ERROR_NOT_FOUND, "Bill not found")


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/confirm",
        vol.Required("bill_id"): cv.string,
        vol.Required("supplier"): vol.All(cv.string, vol.Length(min=2, max=80)),
        vol.Required("values"): {vol.In(list(FIELDS)): vol.Any(None, str, int, float)},
    }
)
@websocket_api.async_response
async def ws_confirm(hass, connection, msg) -> None:
    """Confirm the values of a bill and learn its layout."""
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], ERROR_NOT_READY, "OffGrid2Save is not set up")
        return
    try:
        result = await manager.async_confirm(msg["bill_id"], msg["supplier"], msg["values"])
    except BillNotFound:
        connection.send_error(msg["id"], ERROR_NOT_FOUND, "Bill not found")
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_value", str(err))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/rescan"})
@websocket_api.async_response
async def ws_rescan(hass, connection, msg) -> None:
    """Check the folder for new bills now."""
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], ERROR_NOT_READY, "OffGrid2Save is not set up")
        return
    await manager.async_rescan()
    connection.send_result(msg["id"], manager.data)


class UploadView(HomeAssistantView):
    """Receive a bill from the panel."""

    url = UPLOAD_URL
    name = "api:offgrid2save:upload"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Save an uploaded PDF in the bills folder."""
        if not request["hass_user"].is_admin:
            return self.json_message("Admin required", HTTPStatus.FORBIDDEN)
        hass: HomeAssistant = request.app["hass"]
        manager = _manager(hass)
        if manager is None:
            return self.json_message("Not set up", HTTPStatus.SERVICE_UNAVAILABLE)

        reader = await request.multipart()
        part = await reader.next()
        if part is None or part.name != "file":
            return self.json_message("Missing file", HTTPStatus.BAD_REQUEST)
        data = bytearray()
        while chunk := await part.read_chunk():
            data.extend(chunk)
            if len(data) > MAX_UPLOAD_BYTES:
                return self.json_message("File too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        if b"%PDF-" not in data[:1024]:
            return self.json_message("Not a PDF", HTTPStatus.UNSUPPORTED_MEDIA_TYPE)

        result = await manager.async_add_upload(part.filename or "bolletta.pdf", bytes(data))
        return self.json(result)
