"""Number platform: live-adjustable wear threshold per item."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import WardrobeCoordinator
from .entity import WardrobeItemEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the wear-threshold number entity for this item."""
    coordinator: WardrobeCoordinator = hass.data[DOMAIN]["shared"]["coordinator"]
    async_add_entities([WardrobeWearThresholdNumber(coordinator, entry)])


class WardrobeWearThresholdNumber(WardrobeItemEntity, NumberEntity):
    """Wears allowed per wash cycle; 0 disables threshold-aware cycling.

    The value lives in the coordinator's storage (not the ConfigEntry), so
    changing it never reloads the entry. The config-flow value only seeds
    the initial threshold when the item is first created.
    """

    _attr_icon = "mdi:counter"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 999
    _attr_native_step = 1

    def __init__(self, coordinator: WardrobeCoordinator, entry: ConfigEntry) -> None:
        """Initialize the wear-threshold number."""
        super().__init__(coordinator, entry, "wear_threshold")

    @property
    def native_value(self) -> int:
        """Return the effective threshold."""
        return self.coordinator.get_threshold(self._entry.entry_id)

    async def async_set_native_value(self, value: float) -> None:
        """Persist the new threshold."""
        await self.coordinator.async_set_threshold(self._entry.entry_id, int(value))
