"""Binary-sensor tests: needs-washing per item, load-ready on the hub."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from homeassistant.helpers import entity_registry as er

from custom_components.wardrobe.const import (
    CONF_KIND,
    CONF_LOAD_SIZE,
    DOMAIN,
    KIND_SUMMARY,
    load_size_key,
)

from .helpers import (
    coordinator_of,
    entity_id,
    hub_entity_id,
    setup_bulk_item,
    setup_item,
)


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


async def test_load_ready_sums_weights_with_per_type_override(
    hass: HomeAssistant,
) -> None:
    towel = await setup_item(
        hass, name="Wool Towel", laundry_type="wool", weight=1.5
    )
    socks = await setup_bulk_item(
        hass, name="Wool Socks", laundry_type="wool", quantity=4, weight=0.5
    )
    coordinator = coordinator_of(hass)

    hub = next(
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.data.get(CONF_KIND) == KIND_SUMMARY
    )
    # Global default stays 5; wool gets a smaller per-type threshold.
    result = await hass.config_entries.options.async_init(hub.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_LOAD_SIZE: 5, load_size_key("wool"): 2.5}
    )
    await hass.async_block_till_done()

    eid = hub_entity_id(hass, "binary_sensor", "load_ready_wool")
    assert hass.states.get(eid).state == "off"

    # 1.5 of 2.5 — not enough yet.
    await coordinator.async_set_state(towel.entry_id, "laundry")
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "off"

    # Two dirty socks add 2 × 0.5 → 2.5 total, threshold reached.
    await coordinator.async_set_clean_remaining(socks.entry_id, 2)
    await hass.async_block_till_done()
    state = hass.states.get(eid)
    assert state.state == "on"
    assert state.attributes["items"] == ["Wool Socks", "Wool Towel"]
    assert state.attributes["count"] == 3
    assert state.attributes["total_weight"] == 2.5
    assert state.attributes["load_size"] == 2.5


async def test_bulk_item_creates_no_binary_sensor(hass: HomeAssistant) -> None:
    entry = await setup_bulk_item(hass)
    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id(
            "binary_sensor", DOMAIN, f"{DOMAIN}_{entry.entry_id}_needs_washing"
        )
        is None
    )
