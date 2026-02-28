"""Constants for the Wardrobe Manager integration."""

from enum import StrEnum
from typing import Final

DOMAIN: Final = "wardrobe_manager"
STORAGE_KEY: Final = f"{DOMAIN}.storage"
STORAGE_VERSION: Final = 1

PLATFORMS: Final = [
    "sensor",
    "select",
    "binary_sensor",
    "button",
    "event",
]

EVENT_NFC_TAG_SCANNED: Final = "esphome.nfc_tag_scanned"
EVENT_UNKNOWN_TAG: Final = f"{DOMAIN}_unknown_tag"

CONF_SCANNER_ID: Final = "scanner_id"
CONF_SCANNER_ROLE: Final = "scanner_role"
CONF_SCANNER_NAME: Final = "scanner_name"
CONF_TAG_ID: Final = "tag_id"
CONF_GARMENT_NAME: Final = "garment_name"
CONF_CATEGORY: Final = "category"
CONF_COLOR: Final = "color"
CONF_NEEDS_WASHING_THRESHOLD: Final = "needs_washing_threshold"

DEFAULT_NEEDS_WASHING_THRESHOLD: Final = 3


class ScannerRole(StrEnum):
    """Roles a scanner can have."""

    CLOSET = "closet"
    LAUNDRY_BIN = "laundry_bin"
    WASHER = "washer"
    DRYER = "dryer"
    IRONING = "ironing"


class GarmentState(StrEnum):
    """States a garment can be in."""

    CLEAN = "clean"
    WORN = "worn"
    IN_LAUNDRY_BIN = "in_laundry_bin"
    WASHING = "washing"
    DRYING = "drying"
    NEEDS_IRONING = "needs_ironing"


GARMENT_CATEGORIES: Final = [
    "shirt",
    "t_shirt",
    "polo",
    "blouse",
    "sweater",
    "hoodie",
    "jacket",
    "coat",
    "jeans",
    "pants",
    "shorts",
    "skirt",
    "dress",
    "suit",
    "underwear",
    "socks",
    "sportswear",
    "other",
]
