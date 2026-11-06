"""Constants for OffGrid2Save."""

from __future__ import annotations

DOMAIN = "offgrid2save"
VERSION = "0.3.0"

CONF_BILLS_PATH = "bills_path"
CONF_PV = "pv"
CONF_GRID_IMPORT = "grid_import"
CONF_GRID_EXPORT = "grid_export"
CONF_CONSUMPTION_ADD = "consumption_add"
CONF_CONSUMPTION_SUBTRACT = "consumption_subtract"
CONF_BATTERY_CHARGE = "battery_charge"
CONF_BATTERY_DISCHARGE = "battery_discharge"
CONF_MANUAL_PRICE = "manual_price"
CONF_EXPORT_PRICE = "export_price"
CONF_TAX_RATE = "tax_rate"
CONF_GRID_LAYOUT = "grid_layout"
CONF_DATA_SOURCE = "data_source"
CONF_PRICE_METHOD = "price_method"
CONF_VRM_TOKEN = "vrm_token"
CONF_VRM_SITE = "vrm_site"
CONF_VRM_SITE_NAME = "vrm_site_name"

DATA_SOURCE_VRM = "vrm"
DATA_SOURCE_ENTITIES = "entities"

SOURCE_ROLES = (
    CONF_PV,
    CONF_GRID_IMPORT,
    CONF_GRID_EXPORT,
    CONF_CONSUMPTION_ADD,
    CONF_CONSUMPTION_SUBTRACT,
    CONF_BATTERY_CHARGE,
    CONF_BATTERY_DISCHARGE,
)

DEFAULT_BILLS_PATH = "offgrid2save/bollette"
TEMPLATES_DIR = "offgrid2save/templates"
HISTORY_FILE = "offgrid2save/history.json"
DEFAULT_TAX_RATE = 10.0

EVENT_BILL_PROCESSED = "offgrid2save_bill_processed"
SERVICE_RESCAN = "rescan"

PANEL_URL = "offgrid2save"
PANEL_COMPONENT = "offgrid2save-panel"
STATIC_URL = "/offgrid2save_static"
UPLOAD_URL = "/api/offgrid2save/upload"
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
