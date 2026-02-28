"""Button entities for manual state overrides."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, GarmentState
from .coordinator import WardrobeDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class WardrobeButtonEntityDescription(ButtonEntityDescription):
    """Describes a wardrobe button entity."""

    target_state: GarmentState


BUTTON_DESCRIPTIONS: tuple[WardrobeButtonEntityDescription, ...] = (
    WardrobeButtonEntityDescription(
        key="mark_clean",
        translation_key="mark_clean",
        target_state=GarmentState.CLEAN,
    ),
    WardrobeButtonEntityDescription(
        key="mark_worn",
        translation_key="mark_worn",
        target_state=GarmentState.WORN,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entities."""
    coordinator: WardrobeDataUpdateCoordinator = hass.data[DOMAIN]["coordinator"]

    entities: list[GarmentButton] = []
    for tag_id in coordinator.garments:
        for description in BUTTON_DESCRIPTIONS:
            entities.append(GarmentButton(coordinator, tag_id, description))
    async_add_entities(entities)

    @callback
    def _async_on_data_updated() -> None:
        new_entities: list[GarmentButton] = []
        known = {e.tag_id for e in entities}
        for tag_id in coordinator.garments:
            if tag_id not in known:
                for description in BUTTON_DESCRIPTIONS:
                    entity = GarmentButton(coordinator, tag_id, description)
                    new_entities.append(entity)
                    entities.append(entity)
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(
        coordinator.async_add_listener(_async_on_data_updated)
    )


class GarmentButton(
    CoordinatorEntity[WardrobeDataUpdateCoordinator], ButtonEntity
):
    """Button to force a garment into a specific state."""

    entity_description: WardrobeButtonEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WardrobeDataUpdateCoordinator,
        tag_id: str,
        description: WardrobeButtonEntityDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.entity_description = description
        self.tag_id = tag_id
        self._attr_unique_id = f"{tag_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, tag_id)},
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_force_state(
            self.tag_id, self.entity_description.target_state
        )
