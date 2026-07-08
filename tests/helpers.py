"""Shared helpers for Wardrobe tests."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wardrobe.const import (
    CONF_CATEGORY,
    CONF_EXTRA_STATES,
    CONF_ITEM_NAME,
    CONF_LAUNDRY_TYPE,
    CONF_NFC_TAG_ID,
    CONF_SCAN_ACTION,
    CONF_WEAR_THRESHOLD,
    DEFAULT_LAUNDRY_TYPE,
    DEFAULT_SCAN_ACTION,
    DOMAIN,
)


def make_item(
    *,
    name: str = "Blue Shirt",
    category: str = "t_shirt",
    laundry_type: str = DEFAULT_LAUNDRY_TYPE,
    nfc_tag_id: str | None = None,
    wear_threshold: int = 0,
    scan_action: str = DEFAULT_SCAN_ACTION,
    extra_states: list[str] | None = None,
    entry_id: str | None = None,
    **details: Any,
) -> MockConfigEntry:
    """Build a MockConfigEntry shaped like a v2 clothing item."""
    data: dict[str, Any] = {
        CONF_ITEM_NAME: name,
        CONF_CATEGORY: category,
        CONF_LAUNDRY_TYPE: laundry_type,
        CONF_NFC_TAG_ID: nfc_tag_id,
        CONF_SCAN_ACTION: scan_action,
        CONF_EXTRA_STATES: extra_states or [],
        CONF_WEAR_THRESHOLD: wear_threshold,
        **details,
    }
    kwargs: dict[str, Any] = {}
    if entry_id is not None:
        kwargs["entry_id"] = entry_id
    return MockConfigEntry(
        domain=DOMAIN,
        title=name,
        unique_id=slugify(name),
        data=data,
        **kwargs,
    )


async def setup_item(hass: HomeAssistant, **kwargs: Any) -> MockConfigEntry:
    """Create, register and fully set up an item entry."""
    entry = make_item(**kwargs)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def entity_id(
    hass: HomeAssistant, platform: str, entry: MockConfigEntry, suffix: str
) -> str:
    """Resolve an item entity's id from its unique id."""
    registry = er.async_get(hass)
    eid = registry.async_get_entity_id(
        platform, DOMAIN, f"{DOMAIN}_{entry.entry_id}_{suffix}"
    )
    assert eid is not None, f"missing {platform} entity {suffix} for {entry.title}"
    return eid


def hub_entity_id(hass: HomeAssistant, platform: str, suffix: str) -> str:
    """Resolve a summary-hub entity's id from its unique id."""
    registry = er.async_get(hass)
    eid = registry.async_get_entity_id(platform, DOMAIN, f"{DOMAIN}_summary_{suffix}")
    assert eid is not None, f"missing hub {platform} entity {suffix}"
    return eid


def coordinator_of(hass: HomeAssistant):
    """Return the shared coordinator."""
    return hass.data[DOMAIN]["shared"]["coordinator"]
