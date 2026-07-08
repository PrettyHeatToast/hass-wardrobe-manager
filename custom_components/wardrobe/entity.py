"""Shared entity bases for the Wardrobe integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_BRAND,
    CONF_CATEGORY,
    CONF_ITEM_NAME,
    DOMAIN,
    SUMMARY_DEVICE_ID,
    SUMMARY_DEVICE_NAME,
)
from .coordinator import WardrobeCoordinator, WardrobeRecord


def item_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Build the DeviceInfo for a clothing-item entry."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data[CONF_ITEM_NAME],
        manufacturer=entry.data.get(CONF_BRAND) or "Wardrobe",
        model=entry.data.get(CONF_CATEGORY) or "other",
    )


def hub_device_info() -> DeviceInfo:
    """Build the DeviceInfo for the summary hub."""
    return DeviceInfo(
        identifiers={(DOMAIN, SUMMARY_DEVICE_ID)},
        name=SUMMARY_DEVICE_NAME,
        manufacturer="Wardrobe",
        model="Summary",
        entry_type=DeviceEntryType.SERVICE,
    )


class WardrobeItemEntity(CoordinatorEntity[WardrobeCoordinator]):
    """Base for per-item entities: device info, unique id, record access."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WardrobeCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        """Wire the entity to its item's device."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{key}"
        self._attr_device_info = item_device_info(entry)

    def _record(self) -> WardrobeRecord:
        """Return the coordinator record for this item."""
        return self.coordinator.get_record(self._entry.entry_id)


class WardrobeHubEntity(CoordinatorEntity[WardrobeCoordinator]):
    """Base for summary-hub entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WardrobeCoordinator,
        key: str,
        unique_suffix: str | None = None,
    ) -> None:
        """Wire the entity to the summary device.

        ``unique_suffix`` lets keys like ``summary_clean`` keep the pre-2.0
        unique id ``wardrobe_summary_clean`` instead of doubling the prefix.
        """
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = f"{DOMAIN}_summary_{unique_suffix or key}"
        self._attr_device_info = hub_device_info()
