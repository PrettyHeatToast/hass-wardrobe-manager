"""Diagnostics support for the Wardrobe integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_KIND, CONF_NFC_TAG_ID, DOMAIN, KIND_SUMMARY
from .coordinator import WardrobeCoordinator

TO_REDACT = {CONF_NFC_TAG_ID}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: WardrobeCoordinator = hass.data[DOMAIN]["shared"]["coordinator"]

    if entry.data.get(CONF_KIND) == KIND_SUMMARY:
        return {
            "kind": "summary_hub",
            "options": dict(entry.options),
            "counts_by_state": coordinator.count_by_state(),
            "tracked_items": len(coordinator.data),
        }

    return {
        "kind": "item",
        "config": async_redact_data(dict(entry.data), TO_REDACT),
        "record": coordinator.get_record(entry.entry_id),
        "effective_threshold": coordinator.get_threshold(entry.entry_id),
    }
