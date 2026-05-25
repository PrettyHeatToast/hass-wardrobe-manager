"""Coordinator for the Wardrobe integration — shared state and persistence."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_ITEM_NAME,
    DEFAULT_STATE,
    DOMAIN,
    EVENT_STATE_CHANGED,
    STATES,
    STORAGE_KEY,
    STORAGE_VERSION,
    next_state,
)

_LOGGER = logging.getLogger(__name__)


class WardrobeCoordinator(DataUpdateCoordinator[dict[str, str]]):
    """Holds the wardrobe state for every configured item and persists it.

    Despite subclassing ``DataUpdateCoordinator`` (per the spec), this is not a
    polling coordinator — there is no remote source to poll. ``async_set_updated_data``
    is used to notify ``CoordinatorEntity`` listeners after mutations.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the coordinator."""
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY
        )
        self.data: dict[str, str] = {}

    async def async_load(self) -> None:
        """Read persisted state from storage."""
        stored = await self._store.async_load()
        if stored is None:
            self.data = {}
        else:
            entries = stored.get("entries", {})
            self.data = {
                entry_id: (state if state in STATES else DEFAULT_STATE)
                for entry_id, state in entries.items()
            }
        self.async_set_updated_data(self.data)

    async def _async_save(self) -> None:
        """Persist the current state to storage."""
        try:
            await self._store.async_save({"entries": self.data})
        except Exception:
            _LOGGER.error("Failed to save wardrobe state", exc_info=True)

    async def async_ensure_entry(self, entry_id: str) -> None:
        """Seed an entry's state to the default if it hasn't been seen before."""
        if entry_id not in self.data:
            self.data[entry_id] = DEFAULT_STATE
            await self._async_save()
            self.async_set_updated_data(self.data)

    def get_state(self, entry_id: str) -> str:
        """Return the current state for an entry."""
        return self.data.get(entry_id, DEFAULT_STATE)

    def get_all_items(self) -> dict[str, str]:
        """Return a snapshot of all entry → state mappings."""
        return dict(self.data)

    async def async_set_state(self, entry_id: str, new_state: str) -> None:
        """Set an entry's state, persist, and fire the state-changed event."""
        if new_state not in STATES:
            raise ValueError(f"Invalid wardrobe state: {new_state!r}")

        old_state = self.data.get(entry_id, DEFAULT_STATE)
        self.data[entry_id] = new_state
        await self._async_save()
        self.async_set_updated_data(self.data)

        entry = self.hass.config_entries.async_get_entry(entry_id)
        name = entry.data.get(CONF_ITEM_NAME) if entry is not None else None
        self.hass.bus.async_fire(
            EVENT_STATE_CHANGED,
            {
                "entry_id": entry_id,
                "name": name,
                "old_state": old_state,
                "new_state": new_state,
            },
        )
        _LOGGER.debug(
            "Wardrobe state changed: %s (%s) %s -> %s",
            name,
            entry_id,
            old_state,
            new_state,
        )

    async def async_cycle_state(self, entry_id: str) -> str:
        """Advance an entry to its next state in the cycle."""
        current = self.data.get(entry_id, DEFAULT_STATE)
        new = next_state(current)
        await self.async_set_state(entry_id, new)
        return new

    async def async_remove_entry(self, entry_id: str) -> None:
        """Drop an entry's state from storage when its ConfigEntry is removed."""
        if entry_id in self.data:
            del self.data[entry_id]
            await self._async_save()
            self.async_set_updated_data(self.data)
