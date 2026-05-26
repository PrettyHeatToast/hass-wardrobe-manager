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
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_BY_CATEGORY,
    ATTR_BY_LAUNDRY_TYPE,
    ATTR_ITEMS,
    CONF_CATEGORY,
    CONF_ITEM_NAME,
    CONF_KIND,
    CONF_LAUNDRY_TYPE,
    DEFAULT_LAUNDRY_TYPE,
    DOMAIN,
    KIND_SUMMARY,
    STATES,
    SUMMARY_DEVICE_ID,
    SUMMARY_DEVICE_NAME,
)
from .coordinator import WardrobeCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the entities for either a single item or the summary hub."""
    coordinator: WardrobeCoordinator = hass.data[DOMAIN]["shared"]["coordinator"]

    if entry.data.get(CONF_KIND) == KIND_SUMMARY:
        async_add_entities(
            WardrobeSummaryCountSensor(coordinator, state) for state in STATES
        )
        return

    async_add_entities(
        [
            WearsSinceWashSensor(coordinator, entry),
            WearCountTotalSensor(coordinator, entry),
            LastWornAtSensor(coordinator, entry),
            StateChangedAtSensor(coordinator, entry),
        ]
    )


class _WardrobeItemSensorBase(CoordinatorEntity[WardrobeCoordinator], SensorEntity):
    """Shared device-info / unique-id boilerplate for per-item sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WardrobeCoordinator,
        entry: ConfigEntry,
        translation_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{translation_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_ITEM_NAME],
        )

    def _record(self):
        return self.coordinator.get_record(self._entry.entry_id)


class WearsSinceWashSensor(_WardrobeItemSensorBase):
    """Number of wears since the item last entered the laundry state."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:counter"

    def __init__(
        self, coordinator: WardrobeCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry, "wears_since_wash")

    @property
    def native_value(self) -> int:
        return int(self._record()["wears_since_wash"])


class WearCountTotalSensor(_WardrobeItemSensorBase):
    """Lifetime number of wears recorded for this item."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:counter"

    def __init__(
        self, coordinator: WardrobeCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry, "wear_count_total")

    @property
    def native_value(self) -> int:
        return int(self._record()["wear_count_total"])


class LastWornAtSensor(_WardrobeItemSensorBase):
    """Timestamp of the last transition into the worn state."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self, coordinator: WardrobeCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry, "last_worn_at")

    @property
    def native_value(self) -> datetime | None:
        raw = self._record()["last_worn_at"]
        if not raw:
            return None
        return dt_util.parse_datetime(raw)


class StateChangedAtSensor(_WardrobeItemSensorBase):
    """Timestamp of the most recent state transition."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self, coordinator: WardrobeCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry, "state_changed_at")

    @property
    def native_value(self) -> datetime | None:
        raw = self._record()["state_changed_at"]
        if not raw:
            return None
        return dt_util.parse_datetime(raw)


class WardrobeSummaryCountSensor(
    CoordinatorEntity[WardrobeCoordinator], SensorEntity
):
    """Household-wide count of items in a given state."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:wardrobe-outline"

    def __init__(self, coordinator: WardrobeCoordinator, state: str) -> None:
        super().__init__(coordinator)
        self._state = state
        self._attr_translation_key = f"summary_{state}"
        self._attr_unique_id = f"{DOMAIN}_summary_{state}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, SUMMARY_DEVICE_ID)},
            name=SUMMARY_DEVICE_NAME,
            manufacturer="Wardrobe",
            model="Summary",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> int:
        return self.coordinator.count_by_state().get(self._state, 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        items: list[str] = []
        by_category: dict[str, int] = {}
        by_laundry_type: dict[str, int] = {}
        for entry_id, rec in self.coordinator.data.items():
            if rec["state"] != self._state:
                continue
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry is None:
                continue
            items.append(entry.data.get(CONF_ITEM_NAME, entry_id))
            category = entry.data.get(CONF_CATEGORY, "other")
            laundry_type = entry.data.get(CONF_LAUNDRY_TYPE, DEFAULT_LAUNDRY_TYPE)
            by_category[category] = by_category.get(category, 0) + 1
            by_laundry_type[laundry_type] = (
                by_laundry_type.get(laundry_type, 0) + 1
            )
        return {
            ATTR_ITEMS: sorted(items),
            ATTR_BY_CATEGORY: by_category,
            ATTR_BY_LAUNDRY_TYPE: by_laundry_type,
        }
