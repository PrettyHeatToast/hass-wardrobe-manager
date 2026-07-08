"""The Wardrobe integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback

from .const import (
    ALL_STATES,
    ATTR_FILTER_CATEGORY,
    ATTR_FILTER_CURRENT_STATE,
    ATTR_FILTER_LAUNDRY_TYPE,
    ATTR_ITEMS,
    ATTR_NEW_STATE,
    CATEGORIES,
    CONF_CATEGORY,
    CONF_ITEM_NAME,
    CONF_KIND,
    CONF_LAUNDRY_TYPE,
    CONF_NFC_TAG_ID,
    CONF_SCAN_ACTION,
    DEFAULT_SCAN_ACTION,
    DIRTY_STATES,
    DOMAIN,
    EVENT_TAG_SCANNED,
    EVENT_WASH_COMPLETED,
    HUB_PLATFORMS,
    KIND_SUMMARY,
    LAUNDRY_TYPES,
    PLATFORMS,
    SERVICE_BULK_SET_STATE,
    SERVICE_WASH_LOAD,
    ScanAction,
    is_bulk_entry,
)
from .coordinator import WardrobeCoordinator

__all__ = ["async_setup_entry", "async_unload_entry", "async_remove_entry"]

_LOGGER = logging.getLogger(__name__)


_BULK_SET_STATE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_NEW_STATE): vol.In(ALL_STATES),
        vol.Optional(ATTR_FILTER_CATEGORY): vol.In(CATEGORIES),
        vol.Optional(ATTR_FILTER_LAUNDRY_TYPE): vol.In(LAUNDRY_TYPES),
        vol.Optional(ATTR_FILTER_CURRENT_STATE): vol.In(ALL_STATES),
    }
)

_WASH_LOAD_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_FILTER_LAUNDRY_TYPE): vol.In(LAUNDRY_TYPES),
    }
)


def _is_hub(entry: ConfigEntry) -> bool:
    """Return True if this ConfigEntry is the singleton summary hub."""
    return entry.data.get(CONF_KIND) == KIND_SUMMARY


def _platforms_for(entry: ConfigEntry) -> list[Platform]:
    """Return the platform list this entry should forward to."""
    return HUB_PLATFORMS if _is_hub(entry) else PLATFORMS


def _existing_hub(hass: HomeAssistant) -> ConfigEntry | None:
    """Return the summary hub entry if one is already configured."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if _is_hub(entry):
            return entry
    return None


def _item_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    """Return all non-hub (clothing item) entries."""
    return [e for e in hass.config_entries.async_entries(DOMAIN) if not _is_hub(e)]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up either a single wardrobe item or the summary hub."""
    shared = await _ensure_shared(hass)
    shared["entry_ids"].add(entry.entry_id)

    if _is_hub(entry):
        await hass.config_entries.async_forward_entry_setups(entry, HUB_PLATFORMS)
        entry.async_on_unload(entry.add_update_listener(_async_options_updated))
        return True

    coordinator: WardrobeCoordinator = shared["coordinator"]
    await coordinator.async_ensure_entry(entry.entry_id)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    if _existing_hub(hass) is None:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_INTEGRATION_DISCOVERY}, data={}
            )
        )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a wardrobe item or the summary hub."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, _platforms_for(entry)
    )
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
        for service in (SERVICE_BULK_SET_STATE, SERVICE_WASH_LOAD):
            hass.services.async_remove(DOMAIN, service)
        hass.data[DOMAIN].pop("shared", None)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN, None)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Purge persisted state when a wardrobe item is removed via the UI."""
    if _is_hub(entry):
        # The hub owns no per-item storage; nothing to purge.
        return

    shared = hass.data.get(DOMAIN, {}).get("shared")
    if shared is not None:
        await shared["coordinator"].async_remove_entry(entry.entry_id)
        return

    coordinator = WardrobeCoordinator(hass)
    await coordinator.async_load()
    await coordinator.async_remove_entry(entry.entry_id)


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when config/options change so entities refresh."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _ensure_shared(hass: HomeAssistant) -> dict[str, Any]:
    """Create (or return) the shared coordinator, tag listener and services."""
    bucket = hass.data.setdefault(DOMAIN, {})
    if "shared" in bucket:
        return bucket["shared"]

    coordinator = WardrobeCoordinator(hass)
    await coordinator.async_load()

    shared: dict[str, Any] = {
        "coordinator": coordinator,
        "entry_ids": set(),
    }

    async def _handle_scan(entry: ConfigEntry) -> None:
        action = entry.data.get(CONF_SCAN_ACTION, DEFAULT_SCAN_ACTION)
        if action == ScanAction.MARK_WORN.value:
            await coordinator.async_mark_worn(entry.entry_id)
        elif action == ScanAction.MARK_WASHED.value:
            await coordinator.async_mark_washed(entry.entry_id)
        else:
            await coordinator.async_cycle_state(entry.entry_id)

    @callback
    def _on_tag_scanned(event: Event) -> None:
        tag_id = event.data.get("tag_id")
        if not tag_id:
            return
        for entry in _item_entries(hass):
            if entry.data.get(CONF_NFC_TAG_ID) == tag_id:
                hass.async_create_task(_handle_scan(entry))
                return
        _LOGGER.debug("Ignoring tag scan with no matching wardrobe item: %s", tag_id)

    shared["unsub_tag_listener"] = hass.bus.async_listen(
        EVENT_TAG_SCANNED, _on_tag_scanned
    )

    async def _async_bulk_set_state(call: ServiceCall) -> None:
        new_state = call.data[ATTR_NEW_STATE]
        cat_filter = call.data.get(ATTR_FILTER_CATEGORY)
        lt_filter = call.data.get(ATTR_FILTER_LAUNDRY_TYPE)
        cur_filter = call.data.get(ATTR_FILTER_CURRENT_STATE)

        matched = 0
        for entry in _item_entries(hass):
            if is_bulk_entry(entry.data):
                continue  # bulk items have no state machine
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

    async def _async_wash_load(call: ServiceCall) -> None:
        """Complete a wash: every dirty item (optionally one laundry type) → clean."""
        lt_filter = call.data.get(ATTR_FILTER_LAUNDRY_TYPE)

        washed: list[str] = []
        for entry in _item_entries(hass):
            if lt_filter and entry.data.get(CONF_LAUNDRY_TYPE) != lt_filter:
                continue
            if is_bulk_entry(entry.data):
                if await coordinator.async_bulk_mark_washed(entry.entry_id):
                    washed.append(entry.data.get(CONF_ITEM_NAME, entry.entry_id))
                continue
            if coordinator.get_state(entry.entry_id) not in DIRTY_STATES:
                continue
            await coordinator.async_mark_washed(entry.entry_id)
            washed.append(entry.data.get(CONF_ITEM_NAME, entry.entry_id))

        hass.bus.async_fire(
            EVENT_WASH_COMPLETED,
            {
                ATTR_FILTER_LAUNDRY_TYPE: lt_filter,
                "count": len(washed),
                ATTR_ITEMS: sorted(washed),
            },
        )
        _LOGGER.info(
            "wardrobe.wash_load: washed %d items (laundry_type=%s)",
            len(washed),
            lt_filter,
        )

    hass.services.async_register(
        DOMAIN, SERVICE_BULK_SET_STATE, _async_bulk_set_state, _BULK_SET_STATE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_WASH_LOAD, _async_wash_load, _WASH_LOAD_SCHEMA
    )
    shared["wash_load"] = _async_wash_load

    bucket["shared"] = shared
    return shared
