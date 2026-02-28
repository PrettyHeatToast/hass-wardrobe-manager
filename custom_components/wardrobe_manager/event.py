"""Event entities for garment state changes."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
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
    """Set up event entities."""
    coordinator: WardrobeDataUpdateCoordinator = hass.data[DOMAIN]["coordinator"]

    entities: list[GarmentStateChangeEvent] = [
        GarmentStateChangeEvent(coordinator, tag_id)
        for tag_id in coordinator.garments
    ]
    async_add_entities(entities)

    @callback
    def _async_on_data_updated() -> None:
        new_entities: list[GarmentStateChangeEvent] = []
        known = {e.tag_id for e in entities}
        for tag_id in coordinator.garments:
            if tag_id not in known:
                entity = GarmentStateChangeEvent(coordinator, tag_id)
                new_entities.append(entity)
                entities.append(entity)
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(
        coordinator.async_add_listener(_async_on_data_updated)
    )


class GarmentStateChangeEvent(
    CoordinatorEntity[WardrobeDataUpdateCoordinator], EventEntity
):
    """Event entity that fires when a garment changes state."""

    _attr_has_entity_name = True
    _attr_translation_key = "state_change"
    _attr_event_types = [state.value for state in GarmentState]

    def __init__(
        self,
        coordinator: WardrobeDataUpdateCoordinator,
        tag_id: str,
    ) -> None:
        """Initialize the event entity."""
        super().__init__(coordinator)
        self.tag_id = tag_id
        self._attr_unique_id = f"{tag_id}_state_change"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, tag_id)},
        }
        self._last_state: str | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Trigger event when garment state changes."""
        garment = self.coordinator.garments.get(self.tag_id)
        if garment is None:
            return

        current = garment.garment_state.value
        if self._last_state is not None and current != self._last_state:
            self._trigger_event(
                current,
                {"previous_state": self._last_state, "new_state": current},
            )
        self._last_state = current
        self.async_write_ha_state()
