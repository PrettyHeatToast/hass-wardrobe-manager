"""Binary-sensor platform: needs-washing per item, load-ready per laundry type."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_ITEMS,
    ATTR_THRESHOLD,
    ATTR_TOTAL_WEIGHT,
    ATTR_WEARS_SINCE_WASH,
    CONF_KIND,
    CONF_LOAD_SIZE,
    DIRTY_STATES,
    DOMAIN,
    KIND_SUMMARY,
    LAUNDRY_TYPES,
    is_bulk_entry,
    load_threshold_for,
)
from .coordinator import WardrobeCoordinator
from .entity import WardrobeHubEntity, WardrobeItemEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add binary sensors for either a single item or the summary hub."""
    coordinator: WardrobeCoordinator = hass.data[DOMAIN]["shared"]["coordinator"]

    if entry.data.get(CONF_KIND) == KIND_SUMMARY:
        async_add_entities(
            WardrobeLoadReadyBinarySensor(coordinator, entry, lt)
            for lt in LAUNDRY_TYPES
        )
        return

    if is_bulk_entry(entry.data):
        # Bulk items have no per-item needs-washing indicator; the per-type
        # load-ready sensors cover them.
        return

    async_add_entities([NeedsWashingBinarySensor(coordinator, entry)])


class NeedsWashingBinarySensor(WardrobeItemEntity, BinarySensorEntity):
    """On when the item's per-cycle wear count meets the wear threshold."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: WardrobeCoordinator, entry: ConfigEntry) -> None:
        """Initialize the needs-washing sensor."""
        super().__init__(coordinator, entry, "needs_washing")

    @property
    def is_on(self) -> bool:
        """True when the threshold is reached and the item isn't queued yet."""
        threshold = self.coordinator.get_threshold(self._entry.entry_id)
        if threshold <= 0:
            return False
        rec = self.coordinator.data.get(self._entry.entry_id)
        if rec is None or rec["state"] in DIRTY_STATES:
            return False
        return int(rec["wears_since_wash"]) >= threshold

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the wear count and threshold behind the flag."""
        rec = self._record()
        return {
            ATTR_WEARS_SINCE_WASH: int(rec["wears_since_wash"]),
            ATTR_THRESHOLD: self.coordinator.get_threshold(self._entry.entry_id),
        }


class WardrobeLoadReadyBinarySensor(WardrobeHubEntity, BinarySensorEntity):
    """On when enough items of one laundry type sit in the laundry basket."""

    _attr_icon = "mdi:washing-machine"

    def __init__(
        self,
        coordinator: WardrobeCoordinator,
        hub_entry: ConfigEntry,
        laundry_type: str,
    ) -> None:
        """Initialize the load-ready sensor for one laundry type."""
        super().__init__(coordinator, f"load_ready_{laundry_type}")
        self._hub_entry = hub_entry
        self._laundry_type = laundry_type

    def _threshold(self) -> float:
        """Return the effective weight threshold for this laundry type."""
        return load_threshold_for(self._hub_entry.options, self._laundry_type)

    @property
    def is_on(self) -> bool:
        """True when a full load (by weight) of this laundry type is waiting."""
        _, _, total_weight = self.coordinator.load_for_type(self._laundry_type)
        return total_weight >= self._threshold()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the waiting items, weight and the load threshold."""
        names, units, total_weight = self.coordinator.load_for_type(
            self._laundry_type
        )
        return {
            ATTR_ITEMS: names,
            "count": units,
            ATTR_TOTAL_WEIGHT: round(total_weight, 2),
            CONF_LOAD_SIZE: self._threshold(),
        }
