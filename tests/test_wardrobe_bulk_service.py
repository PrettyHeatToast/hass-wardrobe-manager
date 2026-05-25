"""Tests for the wardrobe.bulk_set_state service."""

from __future__ import annotations

import pytest
import voluptuous as vol

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wardrobe.const import (
    ATTR_FILTER_CATEGORY,
    ATTR_FILTER_CURRENT_STATE,
    ATTR_FILTER_LAUNDRY_TYPE,
    ATTR_NEW_STATE,
    CONF_CATEGORY,
    CONF_ITEM_NAME,
    CONF_LAUNDRY_TYPE,
    CONF_NFC_TAG_ID,
    CONF_WEAR_THRESHOLD,
    DEFAULT_LAUNDRY_TYPE,
    DOMAIN,
    SERVICE_BULK_SET_STATE,
)


async def _setup_item(
    hass: HomeAssistant,
    *,
    name: str,
    category: str = "shirt",
    laundry_type: str = DEFAULT_LAUNDRY_TYPE,
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=name,
        unique_id=name.lower().replace(" ", "_"),
        data={
            CONF_ITEM_NAME: name,
            CONF_CATEGORY: category,
            CONF_NFC_TAG_ID: None,
            CONF_LAUNDRY_TYPE: laundry_type,
            CONF_WEAR_THRESHOLD: 0,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _coord(hass: HomeAssistant):
    return hass.data[DOMAIN]["shared"]["coordinator"]


async def test_no_filters_affects_all_items(hass: HomeAssistant) -> None:
    """With no filters, every item moves to the new state."""
    a = await _setup_item(hass, name="A")
    b = await _setup_item(hass, name="B")
    c = await _setup_item(hass, name="C")

    await hass.services.async_call(
        DOMAIN,
        SERVICE_BULK_SET_STATE,
        {ATTR_NEW_STATE: "laundry"},
        blocking=True,
    )

    coord = _coord(hass)
    for e in (a, b, c):
        assert coord.get_state(e.entry_id) == "laundry"


async def test_category_filter_scopes_changes(hass: HomeAssistant) -> None:
    """Only items whose category matches the filter are mutated."""
    shirt = await _setup_item(hass, name="Shirt", category="shirt")
    pants = await _setup_item(hass, name="Pants", category="pants")

    await hass.services.async_call(
        DOMAIN,
        SERVICE_BULK_SET_STATE,
        {ATTR_NEW_STATE: "worn", ATTR_FILTER_CATEGORY: "shirt"},
        blocking=True,
    )

    coord = _coord(hass)
    assert coord.get_state(shirt.entry_id) == "worn"
    assert coord.get_state(pants.entry_id) == "clean"


async def test_filters_compose_with_and_semantics(hass: HomeAssistant) -> None:
    """Filters intersect: category=shirt AND laundry_type=dark AND current=worn."""
    a = await _setup_item(hass, name="A", category="shirt", laundry_type="dark")
    b = await _setup_item(hass, name="B", category="shirt", laundry_type="light")
    c = await _setup_item(hass, name="C", category="pants", laundry_type="dark")

    coord = _coord(hass)
    # Put A and B into worn so they're candidates.
    await coord.async_set_state(a.entry_id, "worn")
    await coord.async_set_state(b.entry_id, "worn")
    # C stays clean — its current state will fail the filter.

    await hass.services.async_call(
        DOMAIN,
        SERVICE_BULK_SET_STATE,
        {
            ATTR_NEW_STATE: "laundry",
            ATTR_FILTER_CATEGORY: "shirt",
            ATTR_FILTER_LAUNDRY_TYPE: "dark",
            ATTR_FILTER_CURRENT_STATE: "worn",
        },
        blocking=True,
    )

    assert coord.get_state(a.entry_id) == "laundry"  # matches all filters
    assert coord.get_state(b.entry_id) == "worn"      # wrong laundry_type
    assert coord.get_state(c.entry_id) == "clean"     # wrong category + state


async def test_zero_matches_is_silent_success(hass: HomeAssistant) -> None:
    """A filter that matches nothing succeeds without raising."""
    item = await _setup_item(hass, name="Lonely")

    # No items currently in 'laundry', so this matches nothing.
    await hass.services.async_call(
        DOMAIN,
        SERVICE_BULK_SET_STATE,
        {ATTR_NEW_STATE: "clean", ATTR_FILTER_CURRENT_STATE: "laundry"},
        blocking=True,
    )

    assert _coord(hass).get_state(item.entry_id) == "clean"


async def test_invalid_new_state_raises(hass: HomeAssistant) -> None:
    """An unknown new_state is rejected by the service schema."""
    await _setup_item(hass, name="Item")

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_BULK_SET_STATE,
            {ATTR_NEW_STATE: "spaceship"},
            blocking=True,
        )
