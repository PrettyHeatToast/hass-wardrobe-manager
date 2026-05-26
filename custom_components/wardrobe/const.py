"""Constants for the Wardrobe integration."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "wardrobe"
PLATFORMS: Final = [Platform.SELECT, Platform.SENSOR, Platform.BINARY_SENSOR]

STORAGE_KEY: Final = "wardrobe_states"
STORAGE_VERSION: Final = 2

CONF_ITEM_NAME: Final = "name"
CONF_CATEGORY: Final = "category"
CONF_NFC_TAG_ID: Final = "nfc_tag_id"
CONF_LAUNDRY_TYPE: Final = "laundry_type"
CONF_WEAR_THRESHOLD: Final = "wear_threshold"

DEFAULT_WEAR_THRESHOLD: Final = 0

EVENT_STATE_CHANGED: Final = "wardrobe_state_changed"
EVENT_TAG_SCANNED: Final = "tag_scanned"

SERVICE_CYCLE_STATE: Final = "cycle_state"
SERVICE_SET_STATE: Final = "set_state"
SERVICE_BULK_SET_STATE: Final = "bulk_set_state"

ATTR_STATE: Final = "state"
ATTR_NEW_STATE: Final = "new_state"
ATTR_WEARS_SINCE_WASH: Final = "wears_since_wash"
ATTR_WEAR_COUNT_TOTAL: Final = "wear_count_total"
ATTR_LAST_WORN_AT: Final = "last_worn_at"
ATTR_STATE_CHANGED_AT: Final = "state_changed_at"
ATTR_BY_CATEGORY: Final = "by_category"
ATTR_BY_LAUNDRY_TYPE: Final = "by_laundry_type"
ATTR_ITEMS: Final = "items"
ATTR_FILTER_CATEGORY: Final = "category"
ATTR_FILTER_LAUNDRY_TYPE: Final = "laundry_type"
ATTR_FILTER_CURRENT_STATE: Final = "current_state"

SUMMARY_DEVICE_ID: Final = "summary"
SUMMARY_DEVICE_NAME: Final = "Wardrobe Summary"
SUMMARY_HUB_UNIQUE_ID: Final = "_wardrobe_summary_hub"

CONF_KIND: Final = "_kind"
KIND_SUMMARY: Final = "summary"


class WardrobeState(StrEnum):
    """States a clothing item can be in."""

    CLEAN = "clean"
    WORN = "worn"
    LAUNDRY = "laundry"


STATES: Final = [state.value for state in WardrobeState]

STATE_CYCLE: Final = {
    WardrobeState.CLEAN.value: WardrobeState.WORN.value,
    WardrobeState.WORN.value: WardrobeState.LAUNDRY.value,
    WardrobeState.LAUNDRY.value: WardrobeState.CLEAN.value,
}

DEFAULT_STATE: Final = WardrobeState.CLEAN.value


class LaundryType(StrEnum):
    """Wash-load sorting buckets used by the bulk service."""

    DARK = "dark"
    LIGHT = "light"
    COLOR = "color"
    DELICATES = "delicates"


LAUNDRY_TYPES: Final = [lt.value for lt in LaundryType]
DEFAULT_LAUNDRY_TYPE: Final = LaundryType.DARK.value


CATEGORY_ICONS: Final[dict[str, str]] = {
    "shirt": "mdi:tshirt-crew",
    "t_shirt": "mdi:tshirt-v",
    "pants": "mdi:hanger",
    "jeans": "mdi:hanger",
    "shorts": "mdi:hanger",
    "skirt": "mdi:hanger",
    "dress": "mdi:hanger",
    "jacket": "mdi:coat-rack",
    "coat": "mdi:coat-rack",
    "sweater": "mdi:tshirt-crew",
    "hoodie": "mdi:tshirt-crew",
    "shoes": "mdi:shoe-formal",
    "socks": "mdi:sock",
    "hat": "mdi:hat-fedora",
    "scarf": "mdi:scarf",
    "other": "mdi:hanger",
}

LAUNDRY_ICON: Final = "mdi:washing-machine"
DEFAULT_ICON: Final = "mdi:hanger"


def next_state(current: str) -> str:
    """Return the next state in the wardrobe cycle.

    Pure function with no HA dependencies — kept here so tests can exercise
    the cycle without standing up a HomeAssistant instance.
    """
    return STATE_CYCLE[current]
