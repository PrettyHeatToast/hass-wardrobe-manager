"""Helpers for managing garment devices in the HA device registry."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .state_machine import GarmentData


def async_get_or_create_garment_device(
    hass: HomeAssistant,
    config_entry_id: str,
    garment: GarmentData,
) -> dr.DeviceEntry:
    """Ensure a device exists for the given garment."""
    registry = dr.async_get(hass)
    return registry.async_get_or_create(
        config_entry_id=config_entry_id,
        identifiers={(DOMAIN, garment.tag_id)},
        name=garment.name,
        model=garment.category,
        manufacturer="Wardrobe Manager",
    )


def async_remove_garment_device(
    hass: HomeAssistant,
    tag_id: str,
) -> None:
    """Remove a garment's device from the registry."""
    registry = dr.async_get(hass)
    device = registry.async_get_device(identifiers={(DOMAIN, tag_id)})
    if device is not None:
        registry.async_remove_device(device.id)
