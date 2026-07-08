"""Binary-sensor tests: needs-washing per item, load-ready on the hub."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.wardrobe.const import (
    CONF_KIND,
    CONF_LOAD_SIZE,
    DOMAIN,
    KIND_SUMMARY,
)

from .helpers import coordinator_of, entity_id, hub_entity_id, setup_item


async def test_needs_washing_off_when_threshold_disabled(
    hass: HomeAssistant,
) -> None:
    entry = await setup_item(hass)  # threshold 0
    coordinator = coordinator_of(hass)
    eid = entity_id(hass, "binary_sensor", entry, "needs_washing")

    for _ in range(5):
        await coordinator.async_mark_worn(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "off"


async def test_needs_washing_follows_threshold(hass: HomeAssistant) -> None:
    entry = await setup_item(hass, wear_threshold=2)
    coordinator = coordinator_of(hass)
    eid = entity_id(hass, "binary_sensor", entry, "needs_washing")

    await coordinator.async_mark_worn(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "off"

    await coordinator.async_mark_worn(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "on"

    # Queued in the basket → the flag clears.
    await coordinator.async_set_state(entry.entry_id, "laundry")
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "off"

    # Washed → counters reset, stays off.
    await coordinator.async_mark_washed(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "off"


async def test_load_ready_uses_configured_load_size(hass: HomeAssistant) -> None:
    a = await setup_item(hass, name="Black Jeans", laundry_type="dark")
    b = await setup_item(hass, name="Navy Hoodie", laundry_type="dark")
    coordinator = coordinator_of(hass)

    hub = next(
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.data.get(CONF_KIND) == KIND_SUMMARY
    )
    # Shrink the load size from the default 5 to 2 via the hub options flow.
    result = await hass.config_entries.options.async_init(hub.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_LOAD_SIZE: 2}
    )
    await hass.async_block_till_done()

    eid = hub_entity_id(hass, "binary_sensor", "load_ready_dark")
    assert hass.states.get(eid).state == "off"

    await coordinator.async_set_state(a.entry_id, "laundry")
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "off"

    await coordinator.async_set_state(b.entry_id, "laundry")
    await hass.async_block_till_done()
    state = hass.states.get(eid)
    assert state.state == "on"
    assert state.attributes["items"] == ["Black Jeans", "Navy Hoodie"]
    assert state.attributes["load_size"] == 2
