"""Constants for the Wardrobe integration."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "wardrobe"
PLATFORMS: Final = [Platform.SELECT]

STORAGE_KEY: Final = "wardrobe_states"
STORAGE_VERSION: Final = 1

CONF_ITEM_NAME: Final = "name"
CONF_CATEGORY: Final = "category"
CONF_NFC_TAG_ID: Final = "nfc_tag_id"

EVENT_STATE_CHANGED: Final = "wardrobe_state_changed"
EVENT_TAG_SCANNED: Final = "tag_scanned"

SERVICE_CYCLE_STATE: Final = "cycle_state"
SERVICE_SET_STATE: Final = "set_state"

ATTR_STATE: Final = "state"


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
