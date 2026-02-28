"""The Wardrobe Manager integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_CATEGORY,
    CONF_COLOR,
    CONF_GARMENT_NAME,
    CONF_NEEDS_WASHING_THRESHOLD,
    CONF_SCANNER_ID,
    CONF_SCANNER_NAME,
    CONF_SCANNER_ROLE,
    CONF_TAG_ID,
    DEFAULT_NEEDS_WASHING_THRESHOLD,
    DOMAIN,
    EVENT_NFC_TAG_SCANNED,
    PLATFORMS,
    GarmentState,
    ScannerRole,
)
from .coordinator import WardrobeDataUpdateCoordinator
from .device_registry import (
    async_get_or_create_garment_device,
    async_remove_garment_device,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_REGISTER_GARMENT = "register_garment"
SERVICE_REMOVE_GARMENT = "remove_garment"
SERVICE_REGISTER_SCANNER = "register_scanner"
SERVICE_FORCE_STATE = "force_state"
SERVICE_LOG_WASH_CYCLE = "log_wash_cycle"

REGISTER_GARMENT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TAG_ID): cv.string,
        vol.Required(CONF_GARMENT_NAME): cv.string,
        vol.Required(CONF_CATEGORY): cv.string,
        vol.Optional(CONF_COLOR, default=""): cv.string,
        vol.Optional(
            CONF_NEEDS_WASHING_THRESHOLD,
            default=DEFAULT_NEEDS_WASHING_THRESHOLD,
        ): cv.positive_int,
    }
)

REMOVE_GARMENT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TAG_ID): cv.string,
    }
)

REGISTER_SCANNER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCANNER_ID): cv.string,
        vol.Required(CONF_SCANNER_ROLE): vol.In(
            [role.value for role in ScannerRole]
        ),
        vol.Required(CONF_SCANNER_NAME): cv.string,
    }
)

FORCE_STATE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TAG_ID): cv.string,
        vol.Required("state"): vol.In([s.value for s in GarmentState]),
    }
)

LOG_WASH_CYCLE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TAG_ID): cv.string,
        vol.Required("method"): cv.string,
    }
)


def _get_coordinator(hass: HomeAssistant) -> WardrobeDataUpdateCoordinator:
    """Get the current coordinator from hass.data."""
    return hass.data[DOMAIN]["coordinator"]


def _get_entry_id(hass: HomeAssistant) -> str:
    """Get the current config entry ID from hass.data."""
    return hass.data[DOMAIN]["entry_id"]


def _resolve_tag_id(hass: HomeAssistant, value: str) -> str:
    """Resolve a device_id to a tag_id, or return the value as-is."""
    registry = dr.async_get(hass)
    device = registry.async_get(value)
    if device is not None:
        for domain, identifier in device.identifiers:
            if domain == DOMAIN:
                return identifier
    return value


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Wardrobe Manager from a config entry."""
    coordinator = WardrobeDataUpdateCoordinator(hass)
    await coordinator.async_load()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["coordinator"] = coordinator
    hass.data[DOMAIN]["entry_id"] = entry.entry_id

    # Create devices for all known garments
    for garment in coordinator.garments.values():
        async_get_or_create_garment_device(hass, entry.entry_id, garment)

    # Listen for ESPhome NFC tag events
    entry.async_on_unload(
        hass.bus.async_listen(
            EVENT_NFC_TAG_SCANNED, coordinator.handle_tag_scanned
        )
    )

    # Register services
    _register_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.pop(DOMAIN, None)
    return unload_ok


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services.

    Handlers look up coordinator/entry_id from hass.data at call time
    so they always use the current instance, even after a reload.
    """
    if hass.services.has_service(DOMAIN, SERVICE_REGISTER_GARMENT):
        return

    async def handle_register_garment(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        entry_id = _get_entry_id(hass)
        garment = await coordinator.async_register_garment(
            tag_id=call.data[CONF_TAG_ID],
            name=call.data[CONF_GARMENT_NAME],
            category=call.data[CONF_CATEGORY],
            color=call.data.get(CONF_COLOR, ""),
            needs_washing_threshold=call.data.get(
                CONF_NEEDS_WASHING_THRESHOLD, DEFAULT_NEEDS_WASHING_THRESHOLD
            ),
        )
        async_get_or_create_garment_device(hass, entry_id, garment)

    async def handle_remove_garment(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        tag_id = _resolve_tag_id(hass, call.data[CONF_TAG_ID])
        await coordinator.async_remove_garment(tag_id)
        async_remove_garment_device(hass, tag_id)

    async def handle_register_scanner(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        await coordinator.async_register_scanner(
            scanner_id=call.data[CONF_SCANNER_ID],
            role=call.data[CONF_SCANNER_ROLE],
            name=call.data[CONF_SCANNER_NAME],
        )

    async def handle_force_state(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        await coordinator.async_force_state(
            tag_id=_resolve_tag_id(hass, call.data[CONF_TAG_ID]),
            state=GarmentState(call.data["state"]),
        )

    async def handle_log_wash_cycle(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        await coordinator.async_log_wash_cycle(
            tag_id=_resolve_tag_id(hass, call.data[CONF_TAG_ID]),
            method=call.data["method"],
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_REGISTER_GARMENT,
        handle_register_garment,
        schema=REGISTER_GARMENT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_GARMENT,
        handle_remove_garment,
        schema=REMOVE_GARMENT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REGISTER_SCANNER,
        handle_register_scanner,
        schema=REGISTER_SCANNER_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_FORCE_STATE,
        handle_force_state,
        schema=FORCE_STATE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LOG_WASH_CYCLE,
        handle_log_wash_cycle,
        schema=LOG_WASH_CYCLE_SCHEMA,
    )
