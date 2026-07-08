"""Button platform: quick actions per item, complete-wash on the hub."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_FILTER_LAUNDRY_TYPE,
    CONF_KIND,
    DOMAIN,
    KIND_SUMMARY,
    LAUNDRY_TYPES,
    SERVICE_WASH_LOAD,
    is_bulk_entry,
)
from .coordinator import WardrobeCoordinator
from .entity import WardrobeHubEntity, WardrobeItemEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add buttons for either a single item or the summary hub."""
    coordinator: WardrobeCoordinator = hass.data[DOMAIN]["shared"]["coordinator"]

    if entry.data.get(CONF_KIND) == KIND_SUMMARY:
        async_add_entities(
            [
                WardrobeCompleteWashButton(coordinator),
                *(
                    WardrobeCompleteWashTypeButton(coordinator, lt)
                    for lt in LAUNDRY_TYPES
                ),
            ]
        )
        return

    if is_bulk_entry(entry.data):
        async_add_entities(
            [
                WardrobeWearOneButton(coordinator, entry),
                WardrobeMarkWashedButton(coordinator, entry),
            ]
        )
        return

    async_add_entities(
        [
            WardrobeMarkWornButton(coordinator, entry),
            WardrobeMarkWashedButton(coordinator, entry),
        ]
    )


class WardrobeMarkWornButton(WardrobeItemEntity, ButtonEntity):
    """Record a wear: transition to worn, or count a re-wear."""

    _attr_icon = "mdi:account-check"

    def __init__(self, coordinator: WardrobeCoordinator, entry: ConfigEntry) -> None:
        """Initialize the mark-worn button."""
        super().__init__(coordinator, entry, "mark_worn")

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_mark_worn(self._entry.entry_id)


class WardrobeMarkWashedButton(WardrobeItemEntity, ButtonEntity):
    """Mark the item freshly washed and back in the wardrobe."""

    _attr_icon = "mdi:washing-machine"

    def __init__(self, coordinator: WardrobeCoordinator, entry: ConfigEntry) -> None:
        """Initialize the mark-washed button."""
        super().__init__(coordinator, entry, "mark_washed")

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_mark_washed(self._entry.entry_id)


class WardrobeWearOneButton(WardrobeItemEntity, ButtonEntity):
    """Record putting on one unit of a bulk item (clean → dirty)."""

    _attr_icon = "mdi:tshirt-crew"

    def __init__(self, coordinator: WardrobeCoordinator, entry: ConfigEntry) -> None:
        """Initialize the wear-one button."""
        super().__init__(coordinator, entry, "wear_one")

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_bulk_wear_one(self._entry.entry_id)


class WardrobeCompleteWashButton(WardrobeHubEntity, ButtonEntity):
    """Complete a wash cycle: every dirty item returns to clean."""

    _attr_icon = "mdi:washing-machine"

    def __init__(self, coordinator: WardrobeCoordinator) -> None:
        """Initialize the complete-wash button."""
        super().__init__(coordinator, "complete_wash")

    async def async_press(self) -> None:
        """Run the wash_load service without a laundry-type filter."""
        await self.hass.services.async_call(DOMAIN, SERVICE_WASH_LOAD, {}, blocking=True)


class WardrobeCompleteWashTypeButton(WardrobeHubEntity, ButtonEntity):
    """Complete a wash cycle for a single laundry type."""

    _attr_icon = "mdi:washing-machine"

    def __init__(self, coordinator: WardrobeCoordinator, laundry_type: str) -> None:
        """Initialize the per-type complete-wash button."""
        super().__init__(coordinator, f"complete_wash_{laundry_type}")
        self._laundry_type = laundry_type

    async def async_press(self) -> None:
        """Run the wash_load service filtered to this laundry type."""
        await self.hass.services.async_call(
            DOMAIN,
            SERVICE_WASH_LOAD,
            {ATTR_FILTER_LAUNDRY_TYPE: self._laundry_type},
            blocking=True,
        )
