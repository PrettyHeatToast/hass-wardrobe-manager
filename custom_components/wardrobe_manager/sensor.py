"""Sensor entities for Wardrobe Manager garments."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WardrobeDataUpdateCoordinator
from .state_machine import GarmentData


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    """Parse an ISO timestamp string to a datetime object."""
    if value is None:
        return None
    return datetime.fromisoformat(value)


@dataclass(frozen=True, kw_only=True)
class WardrobeSensorEntityDescription(SensorEntityDescription):
    """Describes a wardrobe sensor entity."""

    value_fn: Callable[[GarmentData], Any]


SENSOR_DESCRIPTIONS: tuple[WardrobeSensorEntityDescription, ...] = (
    WardrobeSensorEntityDescription(
        key="last_worn",
        translation_key="last_worn",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda g: _parse_iso_timestamp(g.last_worn),
    ),
    WardrobeSensorEntityDescription(
        key="last_washed",
        translation_key="last_washed",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda g: _parse_iso_timestamp(g.last_washed),
    ),
    WardrobeSensorEntityDescription(
        key="wear_count_since_wash",
        translation_key="wear_count_since_wash",
        native_unit_of_measurement="wears",
        value_fn=lambda g: g.wear_count_since_wash,
    ),
    WardrobeSensorEntityDescription(
        key="total_wear_count",
        translation_key="total_wear_count",
        native_unit_of_measurement="wears",
        value_fn=lambda g: g.total_wear_count,
    ),
    WardrobeSensorEntityDescription(
        key="last_scanned_at",
        translation_key="last_scanned_at",
        value_fn=lambda g: g.last_scanned_at,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: WardrobeDataUpdateCoordinator = hass.data[DOMAIN]["coordinator"]

    entities: list[WardrobeGarmentSensor] = []
    for garment in coordinator.garments.values():
        for description in SENSOR_DESCRIPTIONS:
            entities.append(
                WardrobeGarmentSensor(coordinator, garment.tag_id, description)
            )
    async_add_entities(entities)

    # Listen for new garments added after setup
    @callback
    def _async_on_data_updated() -> None:
        new_entities: list[WardrobeGarmentSensor] = []
        known_tag_ids = {
            e.tag_id for e in entities if isinstance(e, WardrobeGarmentSensor)
        }
        for tag_id, garment in coordinator.garments.items():
            if tag_id not in known_tag_ids:
                for description in SENSOR_DESCRIPTIONS:
                    entity = WardrobeGarmentSensor(
                        coordinator, tag_id, description
                    )
                    new_entities.append(entity)
                    entities.append(entity)
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(
        coordinator.async_add_listener(_async_on_data_updated)
    )


class WardrobeGarmentSensor(
    CoordinatorEntity[WardrobeDataUpdateCoordinator], SensorEntity
):
    """Sensor entity for a garment attribute."""

    entity_description: WardrobeSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WardrobeDataUpdateCoordinator,
        tag_id: str,
        description: WardrobeSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self.tag_id = tag_id
        self._attr_unique_id = f"{tag_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, tag_id)},
        }

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        garment = self.coordinator.garments.get(self.tag_id)
        if garment is None:
            return None
        return self.entity_description.value_fn(garment)
