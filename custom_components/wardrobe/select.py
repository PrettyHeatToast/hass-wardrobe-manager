"""Select platform: one state-select entity per wardrobe item."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_STATE,
    CATEGORY_ICONS,
    CONF_CATEGORY,
    CONF_ITEM_NAME,
    DEFAULT_ICON,
    DOMAIN,
    LAUNDRY_ICON,
    SERVICE_CYCLE_STATE,
    SERVICE_SET_STATE,
    STATES,
    WardrobeState,
)
from .coordinator import WardrobeCoordinator


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
        SERVICE_CYCLE_STATE,
        {},
        "async_cycle_state_service",
    )
    platform.async_register_entity_service(
        SERVICE_SET_STATE,
        {vol.Required(ATTR_STATE): vol.In(STATES)},
        "async_set_state_service",
    )


class WardrobeStateSelect(CoordinatorEntity[WardrobeCoordinator], SelectEntity):
    """Select entity representing the current state of a single garment."""

    _attr_has_entity_name = True
    _attr_translation_key = "wardrobe_state"
    _attr_options = STATES

    def __init__(
        self,
        coordinator: WardrobeCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the select entity for a wardrobe item."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_state"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_ITEM_NAME],
            manufacturer="Wardrobe",
            model=entry.data.get(CONF_CATEGORY) or "other",
        )

    @property
    def current_option(self) -> str | None:
        """Return the current state of the garment."""
        return self.coordinator.get_state(self._entry.entry_id)

    @property
    def icon(self) -> str:
        """Return the icon: laundry overlay when dirty, category icon otherwise."""
        if self.current_option == WardrobeState.LAUNDRY.value:
            return LAUNDRY_ICON
        category = self._entry.data.get(CONF_CATEGORY, "other")
        return CATEGORY_ICONS.get(category, DEFAULT_ICON)

    async def async_select_option(self, option: str) -> None:
        """Update the wardrobe state from the UI dropdown."""
        await self.coordinator.async_set_state(self._entry.entry_id, option)

    async def async_cycle_state_service(self) -> None:
        """Service handler: advance the garment to its next state."""
        await self.coordinator.async_cycle_state(self._entry.entry_id)

    async def async_set_state_service(self, state: str) -> None:
        """Service handler: jump the garment to a specific state."""
        await self.coordinator.async_set_state(self._entry.entry_id, state)
