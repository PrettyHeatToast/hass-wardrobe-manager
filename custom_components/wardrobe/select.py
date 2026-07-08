"""Select platform: one state-select entity per wardrobe item."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ALL_STATES,
    ATTR_STATE,
    CATEGORY_ICONS,
    CONF_BRAND,
    CONF_CATEGORY,
    CONF_COLOR,
    CONF_EXTRA_STATES,
    CONF_LAUNDRY_TYPE,
    CONF_LOCATION,
    CONF_MATERIAL,
    CONF_NFC_TAG_ID,
    CONF_NOTES,
    CONF_PURCHASE_DATE,
    CONF_PURCHASE_PRICE,
    CONF_SCAN_ACTION,
    CONF_SEASONS,
    CONF_SIZE,
    DEFAULT_ICON,
    DEFAULT_LAUNDRY_TYPE,
    DEFAULT_SCAN_ACTION,
    DOMAIN,
    SERVICE_CYCLE_STATE,
    SERVICE_MARK_WASHED,
    SERVICE_MARK_WORN,
    SERVICE_RESET_STATISTICS,
    SERVICE_SET_STATE,
    STATE_ICONS,
    selectable_states,
)
from .coordinator import WardrobeCoordinator
from .entity import WardrobeItemEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the select entity for this clothing item and (re-)register services."""
    coordinator: WardrobeCoordinator = hass.data[DOMAIN]["shared"]["coordinator"]
    async_add_entities([WardrobeStateSelect(coordinator, entry)])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_CYCLE_STATE, {}, "async_cycle_state_service"
    )
    platform.async_register_entity_service(
        SERVICE_SET_STATE,
        {vol.Required(ATTR_STATE): vol.In(ALL_STATES)},
        "async_set_state_service",
    )
    platform.async_register_entity_service(
        SERVICE_MARK_WORN, {}, "async_mark_worn_service"
    )
    platform.async_register_entity_service(
        SERVICE_MARK_WASHED, {}, "async_mark_washed_service"
    )
    platform.async_register_entity_service(
        SERVICE_RESET_STATISTICS, {}, "async_reset_statistics_service"
    )


class WardrobeStateSelect(WardrobeItemEntity, SelectEntity):
    """Select entity representing the current state of a single garment."""

    def __init__(self, coordinator: WardrobeCoordinator, entry: ConfigEntry) -> None:
        """Initialize the select entity for a wardrobe item."""
        super().__init__(coordinator, entry, "state")
        # The unique-id suffix ("state") predates the translation key.
        self._attr_translation_key = "wardrobe_state"

    @property
    def options(self) -> list[str]:
        """States offered for this item, honoring its enabled extra states.

        The current state is always included so an item stranded in a state
        whose extra was later disabled stays representable.
        """
        opts = selectable_states(self._entry.data.get(CONF_EXTRA_STATES))
        current = self.coordinator.get_state(self._entry.entry_id)
        if current not in opts:
            opts = [*opts, current]
        return opts

    @property
    def current_option(self) -> str | None:
        """Return the current state of the garment."""
        return self.coordinator.get_state(self._entry.entry_id)

    @property
    def icon(self) -> str:
        """State-specific icon when dirty/parked, category icon otherwise."""
        state = self.coordinator.get_state(self._entry.entry_id)
        if state in STATE_ICONS:
            return STATE_ICONS[state]
        category = self._entry.data.get(CONF_CATEGORY, "other")
        return CATEGORY_ICONS.get(category, DEFAULT_ICON)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the item's metadata for dashboards and templates."""
        data = self._entry.data
        attrs: dict[str, Any] = {
            CONF_CATEGORY: data.get(CONF_CATEGORY),
            CONF_LAUNDRY_TYPE: data.get(CONF_LAUNDRY_TYPE, DEFAULT_LAUNDRY_TYPE),
            CONF_SCAN_ACTION: data.get(CONF_SCAN_ACTION, DEFAULT_SCAN_ACTION),
            CONF_NFC_TAG_ID: data.get(CONF_NFC_TAG_ID),
        }
        for key in (
            CONF_BRAND,
            CONF_SIZE,
            CONF_COLOR,
            CONF_MATERIAL,
            CONF_SEASONS,
            CONF_LOCATION,
            CONF_PURCHASE_DATE,
            CONF_PURCHASE_PRICE,
            CONF_NOTES,
        ):
            if key in data:
                attrs[key] = data[key]
        return attrs

    async def async_select_option(self, option: str) -> None:
        """Update the wardrobe state from the UI dropdown."""
        await self.coordinator.async_set_state(self._entry.entry_id, option)

    async def async_cycle_state_service(self) -> None:
        """Service handler: advance the garment to its next state."""
        await self.coordinator.async_cycle_state(self._entry.entry_id)

    async def async_set_state_service(self, state: str) -> None:
        """Service handler: jump the garment to a specific state."""
        await self.coordinator.async_set_state(self._entry.entry_id, state)

    async def async_mark_worn_service(self) -> None:
        """Service handler: record a wear (transition or re-wear)."""
        await self.coordinator.async_mark_worn(self._entry.entry_id)

    async def async_mark_washed_service(self) -> None:
        """Service handler: mark the garment freshly washed."""
        await self.coordinator.async_mark_washed(self._entry.entry_id)

    async def async_reset_statistics_service(self) -> None:
        """Service handler: zero the garment's counters and timestamps."""
        await self.coordinator.async_reset_statistics(self._entry.entry_id)
