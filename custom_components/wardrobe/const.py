"""Constants for the Wardrobe integration."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Final

from homeassistant.const import Platform

DOMAIN: Final = "wardrobe"

# Platforms forwarded for a normal clothing-item entry.
PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]

# Platforms forwarded for the singleton summary hub entry.
HUB_PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
]

STORAGE_KEY: Final = "wardrobe_states"
STORAGE_VERSION: Final = 4

# ---------------------------------------------------------------------------
# ConfigEntry data keys
# ---------------------------------------------------------------------------

CONF_ITEM_NAME: Final = "name"
CONF_CATEGORY: Final = "category"
CONF_NFC_TAG_ID: Final = "nfc_tag_id"
CONF_LAUNDRY_TYPE: Final = "laundry_type"
CONF_WEAR_THRESHOLD: Final = "wear_threshold"
CONF_SCAN_ACTION: Final = "scan_action"
CONF_EXTRA_STATES: Final = "extra_states"
CONF_BRAND: Final = "brand"
CONF_SIZE: Final = "size"
CONF_COLOR: Final = "color"
CONF_MATERIAL: Final = "material"
CONF_SEASONS: Final = "seasons"
CONF_LOCATION: Final = "location"
CONF_PURCHASE_DATE: Final = "purchase_date"
CONF_PURCHASE_PRICE: Final = "purchase_price"
CONF_NOTES: Final = "notes"
CONF_WEIGHT: Final = "weight"
CONF_TRACKING_MODE: Final = "tracking_mode"
CONF_QUANTITY: Final = "quantity"

# How much a single unit of an item weighs toward a laundry load.
DEFAULT_WEIGHT: Final = 1.0
DEFAULT_QUANTITY: Final = 10

# Hub option keys. CONF_LOAD_SIZE is the global default load threshold
# (a weight sum); per-type overrides live under load_size_<laundry_type>.
CONF_LOAD_SIZE: Final = "load_size"
DEFAULT_LOAD_SIZE: Final = 5


def load_size_key(laundry_type: str) -> str:
    """Return the hub-options key holding the per-type load threshold."""
    return f"{CONF_LOAD_SIZE}_{laundry_type}"


def load_threshold_for(options: Mapping[str, Any], laundry_type: str) -> float:
    """Return the effective load threshold (weight sum) for a laundry type.

    Pure function: per-type override wins, then the global ``load_size``
    option, then the built-in default.
    """
    value = options.get(
        load_size_key(laundry_type), options.get(CONF_LOAD_SIZE, DEFAULT_LOAD_SIZE)
    )
    return float(value)

DEFAULT_WEAR_THRESHOLD: Final = 0  # 0 disables threshold-aware cycling

# Marker distinguishing the summary hub entry from item entries.
CONF_KIND: Final = "_kind"
KIND_SUMMARY: Final = "summary"

SUMMARY_DEVICE_ID: Final = "summary"
SUMMARY_DEVICE_NAME: Final = "Wardrobe Summary"
SUMMARY_HUB_UNIQUE_ID: Final = "_wardrobe_summary_hub"

# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

EVENT_STATE_CHANGED: Final = "wardrobe_state_changed"
EVENT_NEEDS_WASH: Final = "wardrobe_needs_wash"
EVENT_WASH_COMPLETED: Final = "wardrobe_wash_completed"
# Fired on every NFC scan that matches an item, carrying the resolved item so
# front-ends can focus/open it (see the ``open`` scan action).
EVENT_ITEM_SCANNED: Final = "wardrobe_item_scanned"
EVENT_TAG_SCANNED: Final = "tag_scanned"  # fired by HA's built-in tag integration

# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

SERVICE_CYCLE_STATE: Final = "cycle_state"
SERVICE_SET_STATE: Final = "set_state"
SERVICE_MARK_WORN: Final = "mark_worn"
SERVICE_MARK_WASHED: Final = "mark_washed"
SERVICE_RESET_STATISTICS: Final = "reset_statistics"
SERVICE_BULK_SET_STATE: Final = "bulk_set_state"
SERVICE_WASH_LOAD: Final = "wash_load"

ATTR_STATE: Final = "state"
ATTR_NEW_STATE: Final = "new_state"
ATTR_WEARS_SINCE_WASH: Final = "wears_since_wash"
ATTR_WEAR_COUNT_TOTAL: Final = "wear_count_total"
ATTR_WASH_COUNT: Final = "wash_count"
ATTR_LAST_WORN_AT: Final = "last_worn_at"
ATTR_LAST_WASHED_AT: Final = "last_washed_at"
ATTR_STATE_CHANGED_AT: Final = "state_changed_at"
ATTR_THRESHOLD: Final = "threshold"
ATTR_ITEMS: Final = "items"
ATTR_BY_CATEGORY: Final = "by_category"
ATTR_BY_LAUNDRY_TYPE: Final = "by_laundry_type"
ATTR_FILTER_CATEGORY: Final = "category"
ATTR_FILTER_LAUNDRY_TYPE: Final = "laundry_type"
ATTR_FILTER_CURRENT_STATE: Final = "current_state"
ATTR_TOTAL_WEIGHT: Final = "total_weight"
ATTR_LOAD_THRESHOLD: Final = "load_threshold"
ATTR_DIRTY_COUNT: Final = "dirty_count"
ATTR_CLEAN_REMAINING: Final = "clean_remaining"
ATTR_QUANTITY: Final = "quantity"


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------


class WardrobeState(StrEnum):
    """States a clothing item can be in."""

    CLEAN = "clean"
    WORN = "worn"
    LAUNDRY = "laundry"
    WASHING = "washing"
    DRYING = "drying"
    IRONING = "ironing"
    REPAIR = "repair"
    STORAGE = "storage"


# The core cycle every item participates in.
CORE_CYCLE: Final[list[str]] = [
    WardrobeState.CLEAN.value,
    WardrobeState.WORN.value,
    WardrobeState.LAUNDRY.value,
]

# Optional pipeline states, inserted between laundry and clean in this order.
PIPELINE_STATES: Final[list[str]] = [
    WardrobeState.WASHING.value,
    WardrobeState.DRYING.value,
    WardrobeState.IRONING.value,
]

# Optional parked states: selectable but outside the cycle. Cycling from a
# parked state returns the item to clean.
PARKED_STATES: Final[list[str]] = [
    WardrobeState.REPAIR.value,
    WardrobeState.STORAGE.value,
]

# Extra states a user may enable per item (pipeline + parked).
EXTRA_STATES: Final[list[str]] = PIPELINE_STATES + PARKED_STATES

ALL_STATES: Final[list[str]] = CORE_CYCLE + PIPELINE_STATES + PARKED_STATES

# States meaning "this item is dirty / being washed". Transitioning from one
# of these into clean counts as a completed wash.
DIRTY_STATES: Final[frozenset[str]] = frozenset(
    [WardrobeState.LAUNDRY.value, *PIPELINE_STATES]
)

DEFAULT_STATE: Final = WardrobeState.CLEAN.value


def build_cycle(extra_states: list[str] | None = None) -> list[str]:
    """Return the ordered state cycle for an item.

    Pure function with no HA dependencies — kept here so tests can exercise
    the cycle without standing up a HomeAssistant instance. Parked states
    (repair/storage) never join the cycle.
    """
    extras = set(extra_states or [])
    cycle = list(CORE_CYCLE)
    cycle.extend(s for s in PIPELINE_STATES if s in extras)
    return cycle


def next_state_in(cycle: list[str], current: str) -> str:
    """Return the state following ``current`` in ``cycle``.

    States outside the cycle (parked states, or pipeline states that were
    disabled after the item entered them) resolve to clean.
    """
    try:
        idx = cycle.index(current)
    except ValueError:
        return DEFAULT_STATE
    return cycle[(idx + 1) % len(cycle)]


def selectable_states(extra_states: list[str] | None = None) -> list[str]:
    """Return the states offered by an item's select entity."""
    extras = set(extra_states or [])
    return build_cycle(extra_states) + [s for s in PARKED_STATES if s in extras]


# ---------------------------------------------------------------------------
# Scan actions
# ---------------------------------------------------------------------------


class ScanAction(StrEnum):
    """What scanning an item's NFC tag does."""

    CYCLE = "cycle"
    MARK_WORN = "mark_worn"
    MARK_WASHED = "mark_washed"
    OPEN = "open"  # focus the item / open its dashboard, without changing state


SCAN_ACTIONS: Final = [action.value for action in ScanAction]
DEFAULT_SCAN_ACTION: Final = ScanAction.CYCLE.value


# ---------------------------------------------------------------------------
# Tracking modes
# ---------------------------------------------------------------------------


class TrackingMode(StrEnum):
    """How an item is tracked.

    ``individual`` items run the full state machine; ``bulk`` items (socks,
    underwear, ...) are owned in quantity and tracked by a clean/dirty counter.
    """

    INDIVIDUAL = "individual"
    BULK = "bulk"


TRACKING_MODES: Final = [mode.value for mode in TrackingMode]
DEFAULT_TRACKING_MODE: Final = TrackingMode.INDIVIDUAL.value


def is_bulk_entry(data: Mapping[str, Any]) -> bool:
    """Return True when a ConfigEntry's data marks it as a bulk item."""
    return data.get(CONF_TRACKING_MODE, DEFAULT_TRACKING_MODE) == TrackingMode.BULK


# ---------------------------------------------------------------------------
# Laundry types
# ---------------------------------------------------------------------------


class LaundryType(StrEnum):
    """Wash-load sorting buckets."""

    DARK = "dark"
    LIGHT = "light"
    COLOR = "color"
    DELICATES = "delicates"
    WOOL = "wool"
    HAND_WASH = "hand_wash"


LAUNDRY_TYPES: Final = [lt.value for lt in LaundryType]
DEFAULT_LAUNDRY_TYPE: Final = LaundryType.DARK.value


# ---------------------------------------------------------------------------
# Seasons
# ---------------------------------------------------------------------------

SEASONS: Final[list[str]] = ["spring", "summer", "autumn", "winter", "all_year"]


# ---------------------------------------------------------------------------
# Categories & icons
# ---------------------------------------------------------------------------

CATEGORY_ICONS: Final[dict[str, str]] = {
    "t_shirt": "mdi:tshirt-crew",
    "shirt": "mdi:tshirt-crew-outline",
    "polo": "mdi:tshirt-v",
    "blouse": "mdi:tshirt-v-outline",
    "sweater": "mdi:tshirt-crew",
    "hoodie": "mdi:tshirt-crew",
    "cardigan": "mdi:tshirt-v",
    "jacket": "mdi:coat-rack",
    "coat": "mdi:coat-rack",
    "blazer": "mdi:coat-rack",
    "suit": "mdi:account-tie",
    "dress": "mdi:hanger",
    "skirt": "mdi:hanger",
    "pants": "mdi:hanger",
    "jeans": "mdi:hanger",
    "shorts": "mdi:hanger",
    "leggings": "mdi:hanger",
    "underwear": "mdi:hanger",
    "socks": "mdi:sock",
    "pajamas": "mdi:bed",
    "sportswear": "mdi:run",
    "swimwear": "mdi:swim",
    "shoes": "mdi:shoe-formal",
    "sneakers": "mdi:shoe-sneaker",
    "boots": "mdi:shoe-print",
    "sandals": "mdi:shoe-print",
    "hat": "mdi:hat-fedora",
    "cap": "mdi:hat-fedora",
    "scarf": "mdi:hanger",
    "gloves": "mdi:hand-back-right",
    "belt": "mdi:hanger",
    "tie": "mdi:tie",
    "accessory": "mdi:bag-personal",
    "other": "mdi:hanger",
}

CATEGORIES: Final[list[str]] = list(CATEGORY_ICONS.keys())
DEFAULT_CATEGORY: Final = "t_shirt"

# State-specific icons shown by the select entity when the item is not
# simply clean/worn (those show the category icon).
STATE_ICONS: Final[dict[str, str]] = {
    WardrobeState.LAUNDRY.value: "mdi:basket",
    WardrobeState.WASHING.value: "mdi:washing-machine",
    WardrobeState.DRYING.value: "mdi:tumble-dryer",
    WardrobeState.IRONING.value: "mdi:iron",
    WardrobeState.REPAIR.value: "mdi:needle",
    WardrobeState.STORAGE.value: "mdi:package-variant-closed",
}

DEFAULT_ICON: Final = "mdi:hanger"
