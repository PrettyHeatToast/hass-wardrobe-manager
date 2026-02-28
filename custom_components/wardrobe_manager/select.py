"""Select entity for garment state (with manual override)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, GarmentState
from .coordinator import WardrobeDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities."""
    coordinator: WardrobeDataUpdateCoordinator = hass.data[DOMAIN]["coordinator"]

    entities: list[GarmentStateSelect] = [
        GarmentStateSelect(coordinator, tag_id)
        for tag_id in coordinator.garments
    ]
    async_add_entities(entities)

    @callback
    def _async_on_data_updated() -> None:
        new_entities: list[GarmentStateSelect] = []
        known = {e.tag_id for e in entities}
        for tag_id in coordinator.garments:
            if tag_id not in known:
                entity = GarmentStateSelect(coordinator, tag_id)
                new_entities.append(entity)
                entities.append(entity)
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(
        coordinator.async_add_listener(_async_on_data_updated)
    )


class GarmentStateSelect(
    CoordinatorEntity[WardrobeDataUpdateCoordinator], SelectEntity
):
    """Select entity allowing garment state to be viewed and overridden."""

    _attr_has_entity_name = True
    _attr_translation_key = "garment_state"
    _attr_options = [state.value for state in GarmentState]

    def __init__(
        self,
        coordinator: WardrobeDataUpdateCoordinator,
        tag_id: str,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self.tag_id = tag_id
        self._attr_unique_id = f"{tag_id}_garment_state"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, tag_id)},
        }

    @property
    def current_option(self) -> str | None:
        """Return the current garment state."""
        garment = self.coordinator.garments.get(self.tag_id)
        if garment is None:
            return None
        return garment.garment_state.value

    async def async_select_option(self, option: str) -> None:
        """Change the garment state (manual override)."""
        await self.coordinator.async_force_state(
            self.tag_id, GarmentState(option)
        )
