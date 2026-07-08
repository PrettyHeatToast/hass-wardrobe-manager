"""Sensor platform: per-item counters/timestamps and household summary sensors."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_BY_CATEGORY,
    ATTR_BY_LAUNDRY_TYPE,
    ATTR_ITEMS,
    CONF_CATEGORY,
    CONF_ITEM_NAME,
    CONF_KIND,
    CONF_LAUNDRY_TYPE,
    CONF_PURCHASE_PRICE,
    CORE_CYCLE,
    DEFAULT_LAUNDRY_TYPE,
    DIRTY_STATES,
    DOMAIN,
    KIND_SUMMARY,
    LAUNDRY_TYPES,
    WardrobeState,
)
from .coordinator import WardrobeCoordinator
from .entity import WardrobeHubEntity, WardrobeItemEntity

# Hub count sensors: the three core states plus the wash pipeline as one bucket.
_PIPELINE_KEY = "in_wash"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the sensors for either a single item or the summary hub."""
    coordinator: WardrobeCoordinator = hass.data[DOMAIN]["shared"]["coordinator"]

    if entry.data.get(CONF_KIND) == KIND_SUMMARY:
        entities: list[SensorEntity] = [
            WardrobeSummaryCountSensor(coordinator, state) for state in CORE_CYCLE
        ]
        entities.append(WardrobePipelineCountSensor(coordinator))
        entities.append(WardrobeTotalItemsSensor(coordinator))
        entities.append(WardrobeNeedsWashCountSensor(coordinator))
        entities.extend(
            WardrobeLaundryLoadSensor(coordinator, lt) for lt in LAUNDRY_TYPES
        )
        async_add_entities(entities)
        return

    item_entities: list[SensorEntity] = [
        WardrobeCounterSensor(coordinator, entry, "wears_since_wash"),
        WardrobeCounterSensor(
            coordinator, entry, "wear_count_total", SensorStateClass.TOTAL_INCREASING
        ),
        WardrobeCounterSensor(
            coordinator, entry, "wash_count", SensorStateClass.TOTAL_INCREASING
        ),
        WardrobeTimestampSensor(coordinator, entry, "last_worn_at"),
        WardrobeTimestampSensor(coordinator, entry, "last_washed_at"),
        WardrobeTimestampSensor(coordinator, entry, "state_changed_at"),
    ]
    if entry.data.get(CONF_PURCHASE_PRICE) is not None:
        item_entities.append(WardrobeCostPerWearSensor(coordinator, entry))
    async_add_entities(item_entities)


# ---------------------------------------------------------------------------
# Per-item sensors
# ---------------------------------------------------------------------------


class WardrobeCounterSensor(WardrobeItemEntity, SensorEntity):
    """Integer counter read straight from the item's record."""

    _attr_icon = "mdi:counter"

    def __init__(
        self,
        coordinator: WardrobeCoordinator,
        entry: ConfigEntry,
        key: str,
        state_class: SensorStateClass = SensorStateClass.MEASUREMENT,
    ) -> None:
        """Initialize a counter sensor for one record field."""
        super().__init__(coordinator, entry, key)
        self._key = key
        self._attr_state_class = state_class

    @property
    def native_value(self) -> int:
        """Return the counter value."""
        return int(self._record()[self._key])  # type: ignore[literal-required]


class WardrobeTimestampSensor(WardrobeItemEntity, SensorEntity):
    """Timestamp read straight from the item's record."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self, coordinator: WardrobeCoordinator, entry: ConfigEntry, key: str
    ) -> None:
        """Initialize a timestamp sensor for one record field."""
        super().__init__(coordinator, entry, key)
        self._key = key

    @property
    def native_value(self) -> datetime | None:
        """Return the parsed timestamp, or None if never set."""
        raw = self._record()[self._key]  # type: ignore[literal-required]
        if not raw:
            return None
        return dt_util.parse_datetime(raw)


class WardrobeCostPerWearSensor(WardrobeItemEntity, SensorEntity):
    """Purchase price divided by lifetime wears (only when a price is set)."""

    _attr_icon = "mdi:cash"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: WardrobeCoordinator, entry: ConfigEntry) -> None:
        """Initialize the cost-per-wear sensor."""
        super().__init__(coordinator, entry, "cost_per_wear")

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Use the household currency."""
        return self.hass.config.currency

    @property
    def native_value(self) -> float:
        """Return price / wears (the full price while never worn)."""
        price = float(self._entry.data[CONF_PURCHASE_PRICE])
        wears = int(self._record()["wear_count_total"])
        return round(price / wears, 2) if wears > 0 else price


# ---------------------------------------------------------------------------
# Summary hub sensors
# ---------------------------------------------------------------------------


class _HubSensorBase(WardrobeHubEntity, SensorEntity):
    """Shared helpers for hub sensors that enumerate items."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:wardrobe-outline"

    def _matching_entries(self) -> list[tuple[ConfigEntry, dict[str, Any]]]:
        """Yield (entry, record) pairs this sensor counts."""
        out: list[tuple[ConfigEntry, dict[str, Any]]] = []
        for entry_id, rec in self.coordinator.data.items():
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry is None or entry.data.get(CONF_KIND) == KIND_SUMMARY:
                continue
            if self._matches(entry, rec):
                out.append((entry, rec))
        return out

    def _matches(self, entry: ConfigEntry, rec: dict[str, Any]) -> bool:
        """Return True when the item belongs in this sensor's count."""
        raise NotImplementedError

    @property
    def native_value(self) -> int:
        """Return the number of matching items."""
        return len(self._matching_entries())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Break the count down by name, category and laundry type."""
        items: list[str] = []
        by_category: dict[str, int] = {}
        by_laundry_type: dict[str, int] = {}
        for entry, _rec in self._matching_entries():
            items.append(entry.data.get(CONF_ITEM_NAME, entry.entry_id))
            category = entry.data.get(CONF_CATEGORY, "other")
            laundry_type = entry.data.get(CONF_LAUNDRY_TYPE, DEFAULT_LAUNDRY_TYPE)
            by_category[category] = by_category.get(category, 0) + 1
            by_laundry_type[laundry_type] = by_laundry_type.get(laundry_type, 0) + 1
        return {
            ATTR_ITEMS: sorted(items),
            ATTR_BY_CATEGORY: by_category,
            ATTR_BY_LAUNDRY_TYPE: by_laundry_type,
        }


class WardrobeSummaryCountSensor(_HubSensorBase):
    """Household-wide count of items in a given state."""

    def __init__(self, coordinator: WardrobeCoordinator, state: str) -> None:
        """Initialize the count sensor for one state."""
        # unique_suffix keeps the pre-2.0 unique id wardrobe_summary_<state>.
        super().__init__(coordinator, f"summary_{state}", state)
        self._state = state

    def _matches(self, entry: ConfigEntry, rec: dict[str, Any]) -> bool:
        return rec["state"] == self._state


class WardrobePipelineCountSensor(_HubSensorBase):
    """Count of items currently in the wash pipeline (washing/drying/ironing)."""

    _attr_icon = "mdi:washing-machine"

    def __init__(self, coordinator: WardrobeCoordinator) -> None:
        """Initialize the pipeline count sensor."""
        super().__init__(coordinator, f"summary_{_PIPELINE_KEY}", _PIPELINE_KEY)

    def _matches(self, entry: ConfigEntry, rec: dict[str, Any]) -> bool:
        return rec["state"] in DIRTY_STATES and rec["state"] != (
            WardrobeState.LAUNDRY.value
        )


class WardrobeTotalItemsSensor(_HubSensorBase):
    """Total number of tracked clothing items."""

    def __init__(self, coordinator: WardrobeCoordinator) -> None:
        """Initialize the total-items sensor."""
        super().__init__(coordinator, "summary_total", "total")

    def _matches(self, entry: ConfigEntry, rec: dict[str, Any]) -> bool:
        return True


class WardrobeNeedsWashCountSensor(_HubSensorBase):
    """Count of items that reached their wear threshold but aren't queued yet."""

    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator: WardrobeCoordinator) -> None:
        """Initialize the needs-wash count sensor."""
        super().__init__(coordinator, "summary_needs_washing", "needs_washing")

    def _matches(self, entry: ConfigEntry, rec: dict[str, Any]) -> bool:
        threshold = self.coordinator.get_threshold(entry.entry_id)
        if threshold <= 0 or rec["state"] in DIRTY_STATES:
            return False
        return int(rec["wears_since_wash"]) >= threshold


class WardrobeLaundryLoadSensor(_HubSensorBase):
    """Number of items of one laundry type waiting in the laundry basket."""

    _attr_icon = "mdi:basket"

    def __init__(self, coordinator: WardrobeCoordinator, laundry_type: str) -> None:
        """Initialize the load sensor for one laundry type."""
        super().__init__(coordinator, f"load_{laundry_type}")
        self._laundry_type = laundry_type

    def _matches(self, entry: ConfigEntry, rec: dict[str, Any]) -> bool:
        return (
            rec["state"] == WardrobeState.LAUNDRY.value
            and entry.data.get(CONF_LAUNDRY_TYPE, DEFAULT_LAUNDRY_TYPE)
            == self._laundry_type
        )
