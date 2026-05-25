"""Binary-sensor platform: one needs-washing sensor per item."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_WEARS_SINCE_WASH,
    CONF_ITEM_NAME,
    CONF_WEAR_THRESHOLD,
    DEFAULT_WEAR_THRESHOLD,
    DOMAIN,
    WardrobeState,
)
from .coordinator import WardrobeCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the needs-washing binary sensor for this item."""
    coordinator: WardrobeCoordinator = hass.data[DOMAIN]["shared"]["coordinator"]
    async_add_entities([NeedsWashingBinarySensor(coordinator, entry)])


class NeedsWashingBinarySensor(
    CoordinatorEntity[WardrobeCoordinator], BinarySensorEntity
):
    """On when the item's per-cycle wear count meets the configured threshold."""

    _attr_has_entity_name = True
    _attr_translation_key = "needs_washing"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self, coordinator: WardrobeCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_needs_washing"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_ITEM_NAME],
        )

    def _threshold(self) -> int:
        return int(
            self._entry.data.get(CONF_WEAR_THRESHOLD, DEFAULT_WEAR_THRESHOLD) or 0
        )

    @property
    def is_on(self) -> bool:
        threshold = self._threshold()
        if threshold <= 0:
            return False
        rec = self.coordinator.data.get(self._entry.entry_id)
        if rec is None:
            return False
        if rec["state"] == WardrobeState.LAUNDRY.value:
            return False
        return int(rec["wears_since_wash"]) >= threshold

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        rec = self.coordinator.data.get(self._entry.entry_id) or {}
        return {
            ATTR_WEARS_SINCE_WASH: int(rec.get("wears_since_wash", 0)),
            "threshold": self._threshold(),
        }
