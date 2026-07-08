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
    ATTR_WEARS_SINCE_WASH,
    CONF_ITEM_NAME,
    CONF_KIND,
    CONF_LAUNDRY_TYPE,
    CONF_LOAD_SIZE,
    DEFAULT_LAUNDRY_TYPE,
    DEFAULT_LOAD_SIZE,
    DIRTY_STATES,
    DOMAIN,
    KIND_SUMMARY,
    LAUNDRY_TYPES,
    WardrobeState,
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

    def _load_size(self) -> int:
        """Return the configured items-per-load threshold."""
        return int(self._hub_entry.options.get(CONF_LOAD_SIZE, DEFAULT_LOAD_SIZE))

    def _waiting_items(self) -> list[str]:
        """Names of items of this type currently in the laundry basket."""
        items: list[str] = []
        for entry_id, rec in self.coordinator.data.items():
            if rec["state"] != WardrobeState.LAUNDRY.value:
                continue
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry is None or entry.data.get(CONF_KIND) == KIND_SUMMARY:
                continue
            if (
                entry.data.get(CONF_LAUNDRY_TYPE, DEFAULT_LAUNDRY_TYPE)
                != self._laundry_type
            ):
                continue
            items.append(entry.data.get(CONF_ITEM_NAME, entry_id))
        return sorted(items)

    @property
    def is_on(self) -> bool:
        """True when a full load of this laundry type is waiting."""
        return len(self._waiting_items()) >= self._load_size()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the waiting items and the load size."""
        items = self._waiting_items()
        return {
            ATTR_ITEMS: items,
            "count": len(items),
            CONF_LOAD_SIZE: self._load_size(),
        }
