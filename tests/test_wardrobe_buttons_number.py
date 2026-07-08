"""Button and number entity tests."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .helpers import coordinator_of, entity_id, hub_entity_id, setup_item


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
