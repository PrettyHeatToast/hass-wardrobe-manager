"""Domain- and entity-service tests."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.wardrobe.const import (
    DOMAIN,
    EVENT_WASH_COMPLETED,
    SERVICE_BULK_SET_STATE,
    SERVICE_MARK_WASHED,
    SERVICE_MARK_WORN,
    SERVICE_RESET_STATISTICS,
    SERVICE_SET_STATE,
    SERVICE_WASH_LOAD,
)

from .helpers import coordinator_of, entity_id, setup_item


async def test_bulk_set_state_with_filters(hass: HomeAssistant) -> None:
    tee = await setup_item(hass, name="Tee", category="t_shirt", laundry_type="light")
    jeans = await setup_item(hass, name="Jeans", category="jeans", laundry_type="dark")
    coordinator = coordinator_of(hass)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_BULK_SET_STATE,
        {"new_state": "laundry", "laundry_type": "dark"},
        blocking=True,
    )
    assert coordinator.get_state(jeans.entry_id) == "laundry"
    assert coordinator.get_state(tee.entry_id) == "clean"

    await hass.services.async_call(
        DOMAIN,
        SERVICE_BULK_SET_STATE,
        {"new_state": "worn", "current_state": "clean"},
        blocking=True,
    )
    assert coordinator.get_state(tee.entry_id) == "worn"
    assert coordinator.get_state(jeans.entry_id) == "laundry"


async def test_wash_load_completes_dirty_items(hass: HomeAssistant) -> None:
    dark = await setup_item(hass, name="Jeans", laundry_type="dark")
    light = await setup_item(hass, name="Tee", laundry_type="light")
    coordinator = coordinator_of(hass)
    await coordinator.async_set_state(dark.entry_id, "laundry")
    await coordinator.async_set_state(light.entry_id, "laundry")

    events = async_capture_events(hass, EVENT_WASH_COMPLETED)

    await hass.services.async_call(
        DOMAIN, SERVICE_WASH_LOAD, {"laundry_type": "dark"}, blocking=True
    )
    await hass.async_block_till_done()

    assert coordinator.get_state(dark.entry_id) == "clean"
    assert coordinator.get_record(dark.entry_id)["wash_count"] == 1
    # The light item stays in the basket.
    assert coordinator.get_state(light.entry_id) == "laundry"

    assert len(events) == 1
    assert events[0].data["count"] == 1
    assert events[0].data["items"] == ["Jeans"]
    assert events[0].data["laundry_type"] == "dark"


async def test_entity_services_roundtrip(hass: HomeAssistant) -> None:
    entry = await setup_item(hass)
    coordinator = coordinator_of(hass)
    select_eid = entity_id(hass, "select", entry, "state")

    await hass.services.async_call(
        DOMAIN,
        SERVICE_MARK_WORN,
        {"entity_id": select_eid},
        blocking=True,
    )
    assert coordinator.get_state(entry.entry_id) == "worn"

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_STATE,
        {"entity_id": select_eid, "state": "laundry"},
        blocking=True,
    )
    assert coordinator.get_state(entry.entry_id) == "laundry"

    await hass.services.async_call(
        DOMAIN,
        SERVICE_MARK_WASHED,
        {"entity_id": select_eid},
        blocking=True,
    )
    rec = coordinator.get_record(entry.entry_id)
    assert rec["state"] == "clean"
    assert rec["wash_count"] == 1

    await hass.services.async_call(
        DOMAIN,
        SERVICE_RESET_STATISTICS,
        {"entity_id": select_eid},
        blocking=True,
    )
    rec = coordinator.get_record(entry.entry_id)
    assert rec["wear_count_total"] == 0
    assert rec["wash_count"] == 0


async def test_select_entity_reflects_and_sets_state(hass: HomeAssistant) -> None:
    entry = await setup_item(hass, extra_states=["washing", "storage"])
    coordinator = coordinator_of(hass)
    select_eid = entity_id(hass, "select", entry, "state")

    state = hass.states.get(select_eid)
    assert state.state == "clean"
    assert state.attributes["options"] == [
        "clean",
        "worn",
        "laundry",
        "washing",
        "storage",
    ]

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": select_eid, "option": "storage"},
        blocking=True,
    )
    assert coordinator.get_state(entry.entry_id) == "storage"
    assert hass.states.get(select_eid).state == "storage"
