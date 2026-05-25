"""The Wardrobe integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback

from .const import (
    ATTR_FILTER_CATEGORY,
    ATTR_FILTER_CURRENT_STATE,
    ATTR_FILTER_LAUNDRY_TYPE,
    ATTR_NEW_STATE,
    CATEGORY_ICONS,
    CONF_CATEGORY,
    CONF_LAUNDRY_TYPE,
    CONF_NFC_TAG_ID,
    DOMAIN,
    EVENT_TAG_SCANNED,
    LAUNDRY_TYPES,
    PLATFORMS,
    SERVICE_BULK_SET_STATE,
    STATES,
)
from .coordinator import WardrobeCoordinator

__all__ = ["async_setup_entry", "async_unload_entry", "async_remove_entry"]

_LOGGER = logging.getLogger(__name__)


_BULK_SET_STATE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_NEW_STATE): vol.In(STATES),
        vol.Optional(ATTR_FILTER_CATEGORY): vol.In(list(CATEGORY_ICONS.keys())),
        vol.Optional(ATTR_FILTER_LAUNDRY_TYPE): vol.In(LAUNDRY_TYPES),
        vol.Optional(ATTR_FILTER_CURRENT_STATE): vol.In(STATES),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a single wardrobe item from a config entry."""
    shared = await _ensure_shared(hass)
    coordinator: WardrobeCoordinator = shared["coordinator"]
    await coordinator.async_ensure_entry(entry.entry_id)
    shared["entry_ids"].add(entry.entry_id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a wardrobe item config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    shared = hass.data.get(DOMAIN, {}).get("shared")
    if shared is None:
        return True

    shared["entry_ids"].discard(entry.entry_id)
    if not shared["entry_ids"]:
        unsub = shared.get("unsub_tag_listener")
        if unsub is not None:
            unsub()
        if shared.get("bulk_service_registered"):
            hass.services.async_remove(DOMAIN, SERVICE_BULK_SET_STATE)
        hass.data[DOMAIN].pop("shared", None)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN, None)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Purge persisted state when a wardrobe item is removed via the UI."""
    shared = hass.data.get(DOMAIN, {}).get("shared")
    if shared is not None:
        await shared["coordinator"].async_remove_entry(entry.entry_id)
        return

    coordinator = WardrobeCoordinator(hass)
    await coordinator.async_load()
    await coordinator.async_remove_entry(entry.entry_id)


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change so icon and tag_id refresh."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _ensure_shared(hass: HomeAssistant) -> dict[str, Any]:
    """Create (or return) the shared coordinator, tag listener and bulk service."""
    bucket = hass.data.setdefault(DOMAIN, {})
    if "shared" in bucket:
        return bucket["shared"]

    coordinator = WardrobeCoordinator(hass)
    await coordinator.async_load()

    shared: dict[str, Any] = {
        "coordinator": coordinator,
        "entry_ids": set(),
    }

    @callback
    def _on_tag_scanned(event: Event) -> None:
        tag_id = event.data.get("tag_id")
        if not tag_id:
            return
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.data.get(CONF_NFC_TAG_ID) == tag_id:
                hass.async_create_task(
                    coordinator.async_cycle_state(entry.entry_id)
                )
                return
        _LOGGER.debug(
            "Ignoring tag scan with no matching wardrobe item: %s", tag_id
        )

    shared["unsub_tag_listener"] = hass.bus.async_listen(
        EVENT_TAG_SCANNED, _on_tag_scanned
    )

    async def _async_bulk_set_state(call: ServiceCall) -> None:
        new_state = call.data[ATTR_NEW_STATE]
        cat_filter = call.data.get(ATTR_FILTER_CATEGORY)
        lt_filter = call.data.get(ATTR_FILTER_LAUNDRY_TYPE)
        cur_filter = call.data.get(ATTR_FILTER_CURRENT_STATE)

        matched = 0
        for entry in hass.config_entries.async_entries(DOMAIN):
            if cat_filter and entry.data.get(CONF_CATEGORY) != cat_filter:
                continue
            if lt_filter and entry.data.get(CONF_LAUNDRY_TYPE) != lt_filter:
                continue
            if cur_filter and coordinator.get_state(entry.entry_id) != cur_filter:
                continue
            await coordinator.async_set_state(entry.entry_id, new_state)
            matched += 1

        _LOGGER.info(
            "wardrobe.bulk_set_state: %d items → %s (cat=%s lt=%s cur=%s)",
            matched,
            new_state,
            cat_filter,
            lt_filter,
            cur_filter,
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_BULK_SET_STATE,
        _async_bulk_set_state,
        schema=_BULK_SET_STATE_SCHEMA,
    )
    shared["bulk_service_registered"] = True

    bucket["shared"] = shared
    return shared
