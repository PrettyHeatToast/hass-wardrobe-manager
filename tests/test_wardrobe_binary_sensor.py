"""Binary sensor tests: needs_washing per-item."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wardrobe.const import (
    CONF_CATEGORY,
    CONF_ITEM_NAME,
    CONF_LAUNDRY_TYPE,
    CONF_NFC_TAG_ID,
    CONF_WEAR_THRESHOLD,
    DEFAULT_LAUNDRY_TYPE,
    DOMAIN,
)


async def _setup_item(
    hass: HomeAssistant, *, name: str, wear_threshold: int
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=name,
        unique_id=name.lower().replace(" ", "_"),
        data={
            CONF_ITEM_NAME: name,
            CONF_CATEGORY: "shirt",
            CONF_NFC_TAG_ID: None,
            CONF_LAUNDRY_TYPE: DEFAULT_LAUNDRY_TYPE,
            CONF_WEAR_THRESHOLD: wear_threshold,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _binary_eid(hass: HomeAssistant, entry_id: str) -> str:
    registry = er.async_get(hass)
    eid = registry.async_get_entity_id(
        "binary_sensor", DOMAIN, f"{DOMAIN}_{entry_id}_needs_washing"
    )
    assert eid is not None
    return eid


def _coordinator(hass: HomeAssistant):
    return hass.data[DOMAIN]["shared"]["coordinator"]


async def test_off_when_threshold_zero(hass: HomeAssistant) -> None:
    """A zero threshold means the sensor is always off, regardless of wears."""
    entry = await _setup_item(hass, name="Zero T", wear_threshold=0)
    coord = _coordinator(hass)

    for _ in range(5):
        await coord.async_set_state(entry.entry_id, "worn")
        await coord.async_set_state(entry.entry_id, "clean")
    await hass.async_block_till_done()

    assert hass.states.get(_binary_eid(hass, entry.entry_id)).state == "off"


async def test_on_when_threshold_reached(hass: HomeAssistant) -> None:
    """When wears_since_wash hits the threshold and state isn't laundry, on."""
    entry = await _setup_item(hass, name="Tee", wear_threshold=2)
    coord = _coordinator(hass)

    # clean → worn (wears=1) → clean → worn (wears=2)
    await coord.async_set_state(entry.entry_id, "worn")
    await coord.async_set_state(entry.entry_id, "clean")
    await coord.async_set_state(entry.entry_id, "worn")
    await hass.async_block_till_done()

    assert hass.states.get(_binary_eid(hass, entry.entry_id)).state == "on"


async def test_off_while_in_laundry(hass: HomeAssistant) -> None:
    """Even if wear count is high, the sensor is off while the item is in laundry."""
    entry = await _setup_item(hass, name="Tee", wear_threshold=1)
    coord = _coordinator(hass)

    await coord.async_set_state(entry.entry_id, "worn")
    await hass.async_block_till_done()
    assert hass.states.get(_binary_eid(hass, entry.entry_id)).state == "on"

    await coord.async_set_state(entry.entry_id, "laundry")
    await hass.async_block_till_done()
    assert hass.states.get(_binary_eid(hass, entry.entry_id)).state == "off"


async def test_recovers_after_wash_cycle(hass: HomeAssistant) -> None:
    """After laundry → clean, wears_since_wash resets so the sensor stays off
    until the threshold is re-reached."""
    entry = await _setup_item(hass, name="Tee", wear_threshold=2)
    coord = _coordinator(hass)

    # Trip the threshold once.
    await coord.async_set_state(entry.entry_id, "worn")
    await coord.async_set_state(entry.entry_id, "clean")
    await coord.async_set_state(entry.entry_id, "worn")
    await coord.async_set_state(entry.entry_id, "laundry")
    await coord.async_set_state(entry.entry_id, "clean")
    await hass.async_block_till_done()

    eid = _binary_eid(hass, entry.entry_id)
    assert hass.states.get(eid).state == "off"

    # One wear is below the threshold of 2.
    await coord.async_set_state(entry.entry_id, "worn")
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "off"

    # Second wear (after another wash-to-clean would reset) — but here we just
    # go clean → worn again so wears_since_wash = 2.
    await coord.async_set_state(entry.entry_id, "clean")
    await coord.async_set_state(entry.entry_id, "worn")
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "on"
