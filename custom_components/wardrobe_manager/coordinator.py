"""Wardrobe Manager data coordinator — shared state and storage."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    EVENT_UNKNOWN_TAG,
    STORAGE_KEY,
    STORAGE_VERSION,
    GarmentState,
    ScannerRole,
)
from .state_machine import GarmentData, WashCycle, transition

_LOGGER = logging.getLogger(__name__)


class WardrobeDataUpdateCoordinator(DataUpdateCoordinator[dict[str, GarmentData]]):
    """Coordinator that holds garment state and persists to HA storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
        )
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY
        )
        self.garments: dict[str, GarmentData] = {}
        self.scanners: dict[str, dict[str, str]] = {}

    async def async_load(self) -> None:
        """Load data from storage."""
        stored: dict[str, Any] | None = await self._store.async_load()
        if stored is None:
            stored = {"scanners": {}, "garments": {}}

        self.scanners = stored.get("scanners", {})
        raw_garments = stored.get("garments", {})
        self.garments = {
            tag_id: GarmentData.from_dict(tag_id, gdata)
            for tag_id, gdata in raw_garments.items()
        }
        self.async_set_updated_data(self.garments)

    async def _async_save(self) -> None:
        """Persist current state to storage."""
        data = {
            "scanners": self.scanners,
            "garments": {
                tag_id: garment.to_dict()
                for tag_id, garment in self.garments.items()
            },
        }
        try:
            await self._store.async_save(data)
        except Exception:
            _LOGGER.error("Failed to save wardrobe data to storage")

    def get_scanner_role(self, scanner_id: str) -> ScannerRole | None:
        """Resolve a scanner_id to its role."""
        scanner = self.scanners.get(scanner_id)
        if scanner is None:
            return None
        try:
            return ScannerRole(scanner["role"])
        except (KeyError, ValueError):
            return None

    async def handle_tag_scanned(self, event: Event) -> None:
        """Handle an ESPhome NFC tag scanned event."""
        tag_id: str | None = event.data.get("tag_id")
        scanner_id: str | None = event.data.get("scanner_id")

        if not tag_id or not scanner_id:
            _LOGGER.debug(
                "Ignoring tag scan event with missing data: %s", event.data
            )
            return

        scanner_role = self.get_scanner_role(scanner_id)
        if scanner_role is None:
            _LOGGER.debug(
                "Ignoring scan from unregistered scanner: %s", scanner_id
            )
            return

        garment = self.garments.get(tag_id)
        if garment is None:
            _LOGGER.warning(
                "Unknown tag %s scanned at %s (%s)", tag_id, scanner_id, scanner_role
            )
            self.hass.bus.async_fire(
                EVENT_UNKNOWN_TAG,
                {"tag_id": tag_id, "scanner_role": scanner_role.value},
            )
            return

        _LOGGER.debug(
            "Tag %s scanned at %s (role=%s, current_state=%s)",
            tag_id,
            scanner_id,
            scanner_role,
            garment.garment_state,
        )

        result = transition(garment, scanner_role, scanner_id)
        if result is None:
            _LOGGER.debug(
                "Invalid transition for %s: %s at %s scanner",
                tag_id,
                garment.garment_state,
                scanner_role,
            )
            return

        await self._async_save()
        self.async_set_updated_data(self.garments)

    async def async_register_garment(
        self,
        tag_id: str,
        name: str,
        category: str,
        color: str,
        needs_washing_threshold: int = 3,
    ) -> GarmentData:
        """Register a new garment."""
        garment = GarmentData(
            tag_id=tag_id,
            name=name,
            category=category,
            color=color,
            needs_washing_threshold=needs_washing_threshold,
        )
        self.garments[tag_id] = garment
        await self._async_save()
        self.async_set_updated_data(self.garments)
        return garment

    async def async_remove_garment(self, tag_id: str) -> bool:
        """Remove a garment. Returns True if it existed."""
        if tag_id not in self.garments:
            return False
        del self.garments[tag_id]
        await self._async_save()
        self.async_set_updated_data(self.garments)
        return True

    async def async_register_scanner(
        self, scanner_id: str, role: str, name: str
    ) -> None:
        """Register or update a scanner."""
        self.scanners[scanner_id] = {"role": role, "name": name}
        await self._async_save()

    async def async_force_state(self, tag_id: str, state: GarmentState) -> bool:
        """Force a garment to a specific state."""
        garment = self.garments.get(tag_id)
        if garment is None:
            return False
        garment.garment_state = state
        await self._async_save()
        self.async_set_updated_data(self.garments)
        return True

    async def async_log_wash_cycle(self, tag_id: str, method: str) -> bool:
        """Manually log a wash cycle without a scanner."""
        garment = self.garments.get(tag_id)
        if garment is None:
            return False
        now = datetime.now(timezone.utc).isoformat()
        garment.garment_state = GarmentState.WASHING
        garment.wear_count_since_wash = 0
        garment.last_washed = now
        garment.wash_cycles.append(WashCycle(timestamp=now, method=method))
        await self._async_save()
        self.async_set_updated_data(self.garments)
        return True
