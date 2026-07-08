"""Button and number entity tests."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.wardrobe.const import CONF_WEIGHT

from .helpers import (
    coordinator_of,
    entity_id,
    hub_entity_id,
    setup_bulk_item,
    setup_item,
)


async def test_mark_worn_button(hass: HomeAssistant) -> None:
    entry = await setup_item(hass)
    coordinator = coordinator_of(hass)
    eid = entity_id(hass, "button", entry, "mark_worn")

    await hass.services.async_call(
        "button", "press", {"entity_id": eid}, blocking=True
    )
    rec = coordinator.get_record(entry.entry_id)
    assert rec["state"] == "worn"
    assert rec["wear_count_total"] == 1


async def test_mark_washed_button(hass: HomeAssistant) -> None:
    entry = await setup_item(hass)
    coordinator = coordinator_of(hass)
    await coordinator.async_set_state(entry.entry_id, "laundry")

    eid = entity_id(hass, "button", entry, "mark_washed")
    await hass.services.async_call(
        "button", "press", {"entity_id": eid}, blocking=True
    )
    rec = coordinator.get_record(entry.entry_id)
    assert rec["state"] == "clean"
    assert rec["wash_count"] == 1


async def test_hub_complete_wash_button(hass: HomeAssistant) -> None:
    a = await setup_item(hass, name="Item A")
    b = await setup_item(hass, name="Item B", extra_states=["washing"])
    untouched = await setup_item(hass, name="Item C")
    coordinator = coordinator_of(hass)

    await coordinator.async_set_state(a.entry_id, "laundry")
    await coordinator.async_set_state(b.entry_id, "washing")
    await coordinator.async_set_state(untouched.entry_id, "worn")

    eid = hub_entity_id(hass, "button", "complete_wash")
    await hass.services.async_call(
        "button", "press", {"entity_id": eid}, blocking=True
    )
    await hass.async_block_till_done()

    assert coordinator.get_state(a.entry_id) == "clean"
    assert coordinator.get_state(b.entry_id) == "clean"
    assert coordinator.get_record(a.entry_id)["wash_count"] == 1
    # Worn items are not part of a wash.
    assert coordinator.get_state(untouched.entry_id) == "worn"
    assert coordinator.get_record(untouched.entry_id)["wash_count"] == 0


async def test_wear_threshold_number(hass: HomeAssistant) -> None:
    entry = await setup_item(hass, wear_threshold=1)
    coordinator = coordinator_of(hass)
    eid = entity_id(hass, "number", entry, "wear_threshold")

    assert hass.states.get(eid).state == "1"

    await hass.services.async_call(
        "number", "set_value", {"entity_id": eid, "value": 4}, blocking=True
    )
    assert coordinator.get_threshold(entry.entry_id) == 4
    assert hass.states.get(eid).state == "4"


async def test_weight_number_edits_storage_not_entry(hass: HomeAssistant) -> None:
    entry = await setup_item(hass, weight=1.5)
    coordinator = coordinator_of(hass)
    eid = entity_id(hass, "number", entry, "weight")

    assert hass.states.get(eid).state == "1.5"

    await hass.services.async_call(
        "number", "set_value", {"entity_id": eid, "value": 0.5}, blocking=True
    )
    assert coordinator.get_weight(entry.entry_id) == 0.5
    assert hass.states.get(eid).state == "0.5"
    # No entry reload: the config-flow seed value is untouched.
    assert entry.data[CONF_WEIGHT] == 1.5


async def test_clean_remaining_number_and_wear_one_button(hass: HomeAssistant) -> None:
    entry = await setup_bulk_item(hass, quantity=6)
    coordinator = coordinator_of(hass)
    number_eid = entity_id(hass, "number", entry, "clean_remaining")

    assert hass.states.get(number_eid).state == "6"

    # Lowering the number wears the difference.
    await hass.services.async_call(
        "number", "set_value", {"entity_id": number_eid, "value": 4}, blocking=True
    )
    rec = coordinator.get_record(entry.entry_id)
    assert rec["dirty_count"] == 2
    assert rec["wear_count_total"] == 2

    # The wear-one button decrements by one.
    button_eid = entity_id(hass, "button", entry, "wear_one")
    await hass.services.async_call(
        "button", "press", {"entity_id": button_eid}, blocking=True
    )
    assert hass.states.get(number_eid).state == "3"
    assert coordinator.get_record(entry.entry_id)["wear_count_total"] == 3


async def test_bulk_mark_washed_button_resets_counter(hass: HomeAssistant) -> None:
    entry = await setup_bulk_item(hass, quantity=3)
    coordinator = coordinator_of(hass)
    await coordinator.async_bulk_wear_one(entry.entry_id)

    eid = entity_id(hass, "button", entry, "mark_washed")
    await hass.services.async_call(
        "button", "press", {"entity_id": eid}, blocking=True
    )
    rec = coordinator.get_record(entry.entry_id)
    assert rec["dirty_count"] == 0
    assert rec["wash_count"] == 1


async def test_hub_per_type_wash_button(hass: HomeAssistant) -> None:
    dark = await setup_item(hass, name="Black Jeans", laundry_type="dark")
    light = await setup_item(hass, name="White Tee", laundry_type="light")
    socks = await setup_bulk_item(
        hass, name="Dark Socks", laundry_type="dark", quantity=4
    )
    coordinator = coordinator_of(hass)

    await coordinator.async_set_state(dark.entry_id, "laundry")
    await coordinator.async_set_state(light.entry_id, "laundry")
    await coordinator.async_bulk_wear_one(socks.entry_id)

    eid = hub_entity_id(hass, "button", "complete_wash_dark")
    await hass.services.async_call(
        "button", "press", {"entity_id": eid}, blocking=True
    )
    await hass.async_block_till_done()

    assert coordinator.get_state(dark.entry_id) == "clean"
    assert coordinator.get_record(socks.entry_id)["dirty_count"] == 0
    assert coordinator.get_record(socks.entry_id)["wash_count"] == 1
    # Other types are untouched.
    assert coordinator.get_state(light.entry_id) == "laundry"
