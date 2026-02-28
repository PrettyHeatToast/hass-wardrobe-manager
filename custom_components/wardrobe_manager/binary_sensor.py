"""Binary sensor entity — needs_washing indicator."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WardrobeDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities."""
    coordinator: WardrobeDataUpdateCoordinator = hass.data[DOMAIN]["coordinator"]

    entities: list[NeedsWashingBinarySensor] = [
        NeedsWashingBinarySensor(coordinator, tag_id)
        for tag_id in coordinator.garments
    ]
    async_add_entities(entities)

    @callback
    def _async_on_data_updated() -> None:
        new_entities: list[NeedsWashingBinarySensor] = []
        known = {e.tag_id for e in entities}
        for tag_id in coordinator.garments:
            if tag_id not in known:
                entity = NeedsWashingBinarySensor(coordinator, tag_id)
                new_entities.append(entity)
                entities.append(entity)
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(
        coordinator.async_add_listener(_async_on_data_updated)
    )


class NeedsWashingBinarySensor(
    CoordinatorEntity[WardrobeDataUpdateCoordinator], BinarySensorEntity
):
    """Binary sensor that indicates whether a garment needs washing."""

    _attr_has_entity_name = True
    _attr_translation_key = "needs_washing"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: WardrobeDataUpdateCoordinator,
        tag_id: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.tag_id = tag_id
        self._attr_unique_id = f"{tag_id}_needs_washing"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, tag_id)},
        }

    @property
    def is_on(self) -> bool | None:
        """Return True if garment needs washing."""
        garment = self.coordinator.garments.get(self.tag_id)
        if garment is None:
            return None
        return garment.wear_count_since_wash >= garment.needs_washing_threshold
