"""Number platform: live-adjustable wear threshold, weight and bulk counter."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_DIRTY_COUNT,
    ATTR_QUANTITY,
    CONF_QUANTITY,
    DOMAIN,
    is_bulk_entry,
)
from .coordinator import WardrobeCoordinator
from .entity import WardrobeItemEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the number entities for this item."""
    coordinator: WardrobeCoordinator = hass.data[DOMAIN]["shared"]["coordinator"]
    if is_bulk_entry(entry.data):
        async_add_entities(
            [
                WardrobeWeightNumber(coordinator, entry),
                WardrobeCleanRemainingNumber(coordinator, entry),
            ]
        )
        return
    async_add_entities(
        [
            WardrobeWearThresholdNumber(coordinator, entry),
            WardrobeWeightNumber(coordinator, entry),
        ]
    )


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


class WardrobeWeightNumber(WardrobeItemEntity, NumberEntity):
    """How much one unit of this item weighs toward a laundry load.

    Like the wear threshold, the value lives in the coordinator's storage —
    the config-flow value only seeds it at creation and changes never reload
    the entry.
    """

    _attr_icon = "mdi:weight"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0.1
    _attr_native_max_value = 100
    _attr_native_step = 0.1

    def __init__(self, coordinator: WardrobeCoordinator, entry: ConfigEntry) -> None:
        """Initialize the weight number."""
        super().__init__(coordinator, entry, "weight")

    @property
    def native_value(self) -> float:
        """Return the effective per-unit weight."""
        return self.coordinator.get_weight(self._entry.entry_id)

    async def async_set_native_value(self, value: float) -> None:
        """Persist the new weight."""
        await self.coordinator.async_set_weight(self._entry.entry_id, float(value))


class WardrobeCleanRemainingNumber(WardrobeItemEntity, NumberEntity):
    """Clean units of a bulk item remaining in the drawer.

    Lowering the value records wears (the difference lands in the dirty
    pile); raising it is a silent correction. Washing resets the dirty pile
    via the mark-washed button or the wash_load service.
    """

    _attr_icon = "mdi:counter"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_step = 1

    def __init__(self, coordinator: WardrobeCoordinator, entry: ConfigEntry) -> None:
        """Initialize the clean-remaining number."""
        super().__init__(coordinator, entry, "clean_remaining")

    @property
    def native_max_value(self) -> float:
        """The owned quantity caps the clean count."""
        return float(self._entry.data.get(CONF_QUANTITY, 1))

    @property
    def native_value(self) -> int:
        """Return how many clean units remain."""
        return self.coordinator.get_clean_remaining(self._entry.entry_id)

    async def async_set_native_value(self, value: float) -> None:
        """Persist the new clean count (lowering counts as wears)."""
        await self.coordinator.async_set_clean_remaining(
            self._entry.entry_id, int(value)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the owned quantity and the dirty pile."""
        rec = self._record()
        return {
            ATTR_QUANTITY: self._entry.data.get(CONF_QUANTITY, 1),
            ATTR_DIRTY_COUNT: int(rec["dirty_count"]),
        }
