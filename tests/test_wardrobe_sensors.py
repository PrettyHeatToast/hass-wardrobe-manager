"""Sensor tests: per-item counters/timestamps/cost and hub aggregates."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.wardrobe.const import CONF_PURCHASE_PRICE, DOMAIN

from .helpers import coordinator_of, entity_id, hub_entity_id, setup_item


async def test_item_counter_sensors(hass: HomeAssistant) -> None:
    entry = await setup_item(hass)
    coordinator = coordinator_of(hass)

    await coordinator.async_mark_worn(entry.entry_id)
    await coordinator.async_mark_worn(entry.entry_id)
    await coordinator.async_mark_washed(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id(hass, "sensor", entry, "wears_since_wash")).state == "0"
    assert hass.states.get(entity_id(hass, "sensor", entry, "wear_count_total")).state == "2"
    assert hass.states.get(entity_id(hass, "sensor", entry, "wash_count")).state == "1"


async def test_item_timestamp_sensors(hass: HomeAssistant) -> None:
    entry = await setup_item(hass)
    coordinator = coordinator_of(hass)

    last_worn = entity_id(hass, "sensor", entry, "last_worn_at")
    last_washed = entity_id(hass, "sensor", entry, "last_washed_at")
    assert hass.states.get(last_worn).state == "unknown"
    assert hass.states.get(last_washed).state == "unknown"

    await coordinator.async_mark_worn(entry.entry_id)
    await coordinator.async_mark_washed(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(last_worn).state != "unknown"
    assert hass.states.get(last_washed).state != "unknown"


async def test_cost_per_wear_only_with_price(hass: HomeAssistant) -> None:
    priced = await setup_item(
        hass, name="Fancy Coat", **{CONF_PURCHASE_PRICE: 100.0}
    )
    plain = await setup_item(hass, name="Plain Tee")
    coordinator = coordinator_of(hass)

    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id(
            "sensor", DOMAIN, f"{DOMAIN}_{plain.entry_id}_cost_per_wear"
        )
        is None
    )

    cpw = entity_id(hass, "sensor", priced, "cost_per_wear")
    # Never worn: the full price.
    assert float(hass.states.get(cpw).state) == 100.0

    await coordinator.async_mark_worn(priced.entry_id)
    await coordinator.async_mark_washed(priced.entry_id)
    await coordinator.async_mark_worn(priced.entry_id)
    await hass.async_block_till_done()
    assert float(hass.states.get(cpw).state) == 50.0


async def test_hub_state_counts(hass: HomeAssistant) -> None:
    a = await setup_item(hass, name="Item A")
    b = await setup_item(hass, name="Item B")
    c = await setup_item(hass, name="Item C", extra_states=["washing"])
    coordinator = coordinator_of(hass)

    await coordinator.async_set_state(a.entry_id, "worn")
    await coordinator.async_set_state(b.entry_id, "laundry")
    await coordinator.async_set_state(c.entry_id, "washing")
    await hass.async_block_till_done()

    assert hass.states.get(hub_entity_id(hass, "sensor", "clean")).state == "0"
    assert hass.states.get(hub_entity_id(hass, "sensor", "worn")).state == "1"
    assert hass.states.get(hub_entity_id(hass, "sensor", "laundry")).state == "1"
    assert hass.states.get(hub_entity_id(hass, "sensor", "in_wash")).state == "1"
    assert hass.states.get(hub_entity_id(hass, "sensor", "total")).state == "3"


async def test_hub_laundry_load_sensor_and_attributes(hass: HomeAssistant) -> None:
    dark1 = await setup_item(hass, name="Black Jeans", laundry_type="dark")
    dark2 = await setup_item(hass, name="Navy Hoodie", laundry_type="dark")
    light = await setup_item(hass, name="White Tee", laundry_type="light")
    coordinator = coordinator_of(hass)

    for e in (dark1, dark2, light):
        await coordinator.async_set_state(e.entry_id, "laundry")
    await hass.async_block_till_done()

    dark_load = hass.states.get(hub_entity_id(hass, "sensor", "load_dark"))
    assert dark_load.state == "2"
    assert dark_load.attributes["items"] == ["Black Jeans", "Navy Hoodie"]

    light_load = hass.states.get(hub_entity_id(hass, "sensor", "load_light"))
    assert light_load.state == "1"


async def test_hub_needs_wash_count(hass: HomeAssistant) -> None:
    entry = await setup_item(hass, wear_threshold=1)
    await setup_item(hass, name="No Threshold")
    coordinator = coordinator_of(hass)

    needs = hub_entity_id(hass, "sensor", "needs_washing")
    assert hass.states.get(needs).state == "0"

    await coordinator.async_mark_worn(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(needs).state == "1"

    # Once it's queued in the basket, it no longer "needs washing".
    await coordinator.async_set_state(entry.entry_id, "laundry")
    await hass.async_block_till_done()
    assert hass.states.get(needs).state == "0"
