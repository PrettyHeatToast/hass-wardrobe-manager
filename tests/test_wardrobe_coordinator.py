"""Coordinator tests: accounting, thresholds, extra states, tag scans."""

from __future__ import annotations

import pytest

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.wardrobe.const import (
    CONF_WEIGHT,
    EVENT_ITEM_SCANNED,
    EVENT_NEEDS_WASH,
    EVENT_STATE_CHANGED,
    EVENT_TAG_SCANNED,
)

from .helpers import coordinator_of, entity_id, setup_bulk_item, setup_item


async def test_weight_config_seed_and_runtime_override(hass: HomeAssistant) -> None:
    entry = await setup_item(hass, weight=1.5)
    coordinator = coordinator_of(hass)
    assert coordinator.get_weight(entry.entry_id) == 1.5

    await coordinator.async_set_weight(entry.entry_id, 2.0)
    assert coordinator.get_weight(entry.entry_id) == 2.0
    # The runtime value lives in storage; the ConfigEntry seed is untouched.
    assert entry.data[CONF_WEIGHT] == 1.5


async def test_weight_defaults_to_one(hass: HomeAssistant) -> None:
    entry = await setup_item(hass)
    assert coordinator_of(hass).get_weight(entry.entry_id) == 1.0


async def test_bulk_clean_remaining_wear_and_correction(hass: HomeAssistant) -> None:
    entry = await setup_bulk_item(hass, quantity=5)
    coordinator = coordinator_of(hass)
    assert coordinator.get_clean_remaining(entry.entry_id) == 5

    # Lowering the clean count records wears.
    await coordinator.async_set_clean_remaining(entry.entry_id, 3)
    rec = coordinator.get_record(entry.entry_id)
    assert rec["dirty_count"] == 2
    assert rec["wear_count_total"] == 2
    assert rec["last_worn_at"] is not None

    # Raising it is a silent correction: dirty shrinks, stats untouched.
    await coordinator.async_set_clean_remaining(entry.entry_id, 4)
    rec = coordinator.get_record(entry.entry_id)
    assert rec["dirty_count"] == 1
    assert rec["wear_count_total"] == 2

    # Values clamp to 0..quantity.
    await coordinator.async_set_clean_remaining(entry.entry_id, 99)
    assert coordinator.get_record(entry.entry_id)["dirty_count"] == 0


async def test_bulk_wear_one_clamps_when_drawer_empty(hass: HomeAssistant) -> None:
    entry = await setup_bulk_item(hass, quantity=1)
    coordinator = coordinator_of(hass)

    await coordinator.async_bulk_wear_one(entry.entry_id)
    await coordinator.async_bulk_wear_one(entry.entry_id)  # nothing clean left

    rec = coordinator.get_record(entry.entry_id)
    assert rec["dirty_count"] == 1
    assert rec["wear_count_total"] == 1
    assert coordinator.get_clean_remaining(entry.entry_id) == 0


async def test_bulk_mark_washed_resets_dirty_pile(hass: HomeAssistant) -> None:
    entry = await setup_bulk_item(hass, quantity=4)
    coordinator = coordinator_of(hass)
    await coordinator.async_set_clean_remaining(entry.entry_id, 1)

    assert await coordinator.async_bulk_mark_washed(entry.entry_id) is True
    rec = coordinator.get_record(entry.entry_id)
    assert rec["dirty_count"] == 0
    assert rec["wash_count"] == 1
    assert rec["last_washed_at"] is not None

    # Nothing dirty → nothing washed.
    assert await coordinator.async_bulk_mark_washed(entry.entry_id) is False
    assert coordinator.get_record(entry.entry_id)["wash_count"] == 1


async def test_bulk_mark_washed_dispatch(hass: HomeAssistant) -> None:
    """The generic mark_washed routes bulk entries to the counter reset."""
    entry = await setup_bulk_item(hass, quantity=3)
    coordinator = coordinator_of(hass)
    await coordinator.async_bulk_wear_one(entry.entry_id)

    await coordinator.async_mark_washed(entry.entry_id)
    rec = coordinator.get_record(entry.entry_id)
    assert rec["dirty_count"] == 0
    assert rec["wash_count"] == 1
    # No state machine involved: the record state never left clean.
    assert rec["state"] == "clean"


async def test_bulk_ignores_state_machine(hass: HomeAssistant) -> None:
    entry = await setup_bulk_item(hass)
    coordinator = coordinator_of(hass)
    events = async_capture_events(hass, EVENT_STATE_CHANGED)

    await coordinator.async_set_state(entry.entry_id, "worn")
    assert coordinator.get_state(entry.entry_id) == "clean"
    assert await coordinator.async_cycle_state(entry.entry_id) == "clean"
    await coordinator.async_mark_worn(entry.entry_id)
    await hass.async_block_till_done()

    rec = coordinator.get_record(entry.entry_id)
    assert rec["wear_count_total"] == 0
    assert not events


async def test_load_for_type_mixes_individual_and_bulk(hass: HomeAssistant) -> None:
    towel = await setup_item(hass, name="Towel", laundry_type="light", weight=1.5)
    socks = await setup_bulk_item(
        hass, name="White Socks", laundry_type="light", quantity=6, weight=0.5
    )
    other = await setup_item(hass, name="Black Tee", laundry_type="dark")
    coordinator = coordinator_of(hass)

    await coordinator.async_set_state(towel.entry_id, "laundry")
    await coordinator.async_set_state(other.entry_id, "laundry")
    await coordinator.async_set_clean_remaining(socks.entry_id, 2)  # 4 dirty

    names, units, total_weight = coordinator.load_for_type("light")
    assert names == ["Towel", "White Socks"]
    assert units == 5  # 1 towel + 4 socks
    assert total_weight == pytest.approx(3.5)  # 1.5 + 4 × 0.5


async def test_new_item_starts_clean(hass: HomeAssistant) -> None:
    entry = await setup_item(hass)
    coordinator = coordinator_of(hass)
    rec = coordinator.get_record(entry.entry_id)
    assert rec["state"] == "clean"
    assert rec["wears_since_wash"] == 0
    assert rec["wear_count_total"] == 0
    assert rec["wash_count"] == 0
    assert rec["last_worn_at"] is None
    assert rec["last_washed_at"] is None


async def test_core_cycle_with_accounting(hass: HomeAssistant) -> None:
    """clean → worn counts a wear; laundry → clean counts a wash."""
    entry = await setup_item(hass)
    coordinator = coordinator_of(hass)

    assert await coordinator.async_cycle_state(entry.entry_id) == "worn"
    rec = coordinator.get_record(entry.entry_id)
    assert rec["wears_since_wash"] == 1
    assert rec["wear_count_total"] == 1
    assert rec["last_worn_at"] is not None

    assert await coordinator.async_cycle_state(entry.entry_id) == "laundry"
    # Wears survive the trip to the basket; they reset when washed.
    assert coordinator.get_record(entry.entry_id)["wears_since_wash"] == 1

    assert await coordinator.async_cycle_state(entry.entry_id) == "clean"
    rec = coordinator.get_record(entry.entry_id)
    assert rec["wash_count"] == 1
    assert rec["wears_since_wash"] == 0
    assert rec["last_washed_at"] is not None
    assert rec["wear_count_total"] == 1


async def test_threshold_keeps_item_worn(hass: HomeAssistant) -> None:
    """With threshold 2, the second cycle records a re-wear instead of moving on."""
    entry = await setup_item(hass, wear_threshold=2)
    coordinator = coordinator_of(hass)

    assert await coordinator.async_cycle_state(entry.entry_id) == "worn"
    assert await coordinator.async_cycle_state(entry.entry_id) == "worn"
    assert coordinator.get_record(entry.entry_id)["wears_since_wash"] == 2
    assert await coordinator.async_cycle_state(entry.entry_id) == "laundry"


async def test_needs_wash_event_fires_once_at_threshold(hass: HomeAssistant) -> None:
    entry = await setup_item(hass, wear_threshold=2)
    coordinator = coordinator_of(hass)
    events = async_capture_events(hass, EVENT_NEEDS_WASH)

    await coordinator.async_cycle_state(entry.entry_id)  # worn, wears=1
    await hass.async_block_till_done()
    assert len(events) == 0

    await coordinator.async_cycle_state(entry.entry_id)  # re-wear, wears=2
    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0].data["wears_since_wash"] == 2

    # Going past the threshold via mark_worn does not re-fire.
    await coordinator.async_mark_worn(entry.entry_id)
    await hass.async_block_till_done()
    assert len(events) == 1


async def test_extended_pipeline_cycle(hass: HomeAssistant) -> None:
    entry = await setup_item(hass, extra_states=["washing", "drying"])
    coordinator = coordinator_of(hass)

    for expected in ("worn", "laundry", "washing", "drying"):
        assert await coordinator.async_cycle_state(entry.entry_id) == expected
        assert coordinator.get_record(entry.entry_id)["wash_count"] == 0

    assert await coordinator.async_cycle_state(entry.entry_id) == "clean"
    assert coordinator.get_record(entry.entry_id)["wash_count"] == 1


async def test_cycling_from_parked_state_returns_to_clean(
    hass: HomeAssistant,
) -> None:
    entry = await setup_item(hass, extra_states=["repair"])
    coordinator = coordinator_of(hass)
    await coordinator.async_set_state(entry.entry_id, "repair")
    assert await coordinator.async_cycle_state(entry.entry_id) == "clean"
    # Repair → clean is not a wash.
    assert coordinator.get_record(entry.entry_id)["wash_count"] == 0


async def test_mark_worn_transitions_then_rewears(hass: HomeAssistant) -> None:
    entry = await setup_item(hass)
    coordinator = coordinator_of(hass)

    await coordinator.async_mark_worn(entry.entry_id)
    assert coordinator.get_state(entry.entry_id) == "worn"
    assert coordinator.get_record(entry.entry_id)["wear_count_total"] == 1

    await coordinator.async_mark_worn(entry.entry_id)
    assert coordinator.get_state(entry.entry_id) == "worn"
    assert coordinator.get_record(entry.entry_id)["wear_count_total"] == 2


async def test_mark_washed_from_any_state(hass: HomeAssistant) -> None:
    entry = await setup_item(hass)
    coordinator = coordinator_of(hass)
    await coordinator.async_set_state(entry.entry_id, "worn")

    await coordinator.async_mark_washed(entry.entry_id)
    rec = coordinator.get_record(entry.entry_id)
    assert rec["state"] == "clean"
    assert rec["wash_count"] == 1
    assert rec["wears_since_wash"] == 0
    assert rec["last_washed_at"] is not None


async def test_reset_statistics_keeps_state(hass: HomeAssistant) -> None:
    entry = await setup_item(hass)
    coordinator = coordinator_of(hass)
    await coordinator.async_mark_worn(entry.entry_id)
    await coordinator.async_reset_statistics(entry.entry_id)

    rec = coordinator.get_record(entry.entry_id)
    assert rec["state"] == "worn"
    assert rec["wear_count_total"] == 0
    assert rec["wears_since_wash"] == 0
    assert rec["wash_count"] == 0
    assert rec["last_worn_at"] is None


async def test_set_state_rejects_unknown_state(hass: HomeAssistant) -> None:
    entry = await setup_item(hass)
    coordinator = coordinator_of(hass)
    with pytest.raises(ValueError):
        await coordinator.async_set_state(entry.entry_id, "spaceship")


async def test_state_changed_event_payload(hass: HomeAssistant) -> None:
    entry = await setup_item(hass)
    coordinator = coordinator_of(hass)
    events = async_capture_events(hass, EVENT_STATE_CHANGED)

    await coordinator.async_set_state(entry.entry_id, "worn")
    await hass.async_block_till_done()

    assert len(events) == 1
    data = events[0].data
    assert data["entry_id"] == entry.entry_id
    assert data["name"] == "Blue Shirt"
    assert data["old_state"] == "clean"
    assert data["new_state"] == "worn"
    assert data["wears_since_wash"] == 1
    assert data["wear_count_total"] == 1
    assert data["wash_count"] == 0


async def test_tag_scan_cycles_matching_item(hass: HomeAssistant) -> None:
    entry = await setup_item(hass, nfc_tag_id="tag-1")
    other = await setup_item(hass, name="Red Sock", nfc_tag_id="tag-2")
    coordinator = coordinator_of(hass)

    hass.bus.async_fire(EVENT_TAG_SCANNED, {"tag_id": "tag-1"})
    await hass.async_block_till_done()

    assert coordinator.get_state(entry.entry_id) == "worn"
    assert coordinator.get_state(other.entry_id) == "clean"


async def test_tag_scan_respects_scan_action(hass: HomeAssistant) -> None:
    worn_item = await setup_item(
        hass, name="Gym Shirt", nfc_tag_id="tag-w", scan_action="mark_worn"
    )
    washed_item = await setup_item(
        hass, name="Towel", nfc_tag_id="tag-x", scan_action="mark_washed"
    )
    coordinator = coordinator_of(hass)
    await coordinator.async_set_state(washed_item.entry_id, "laundry")

    hass.bus.async_fire(EVENT_TAG_SCANNED, {"tag_id": "tag-w"})
    hass.bus.async_fire(EVENT_TAG_SCANNED, {"tag_id": "tag-w"})
    hass.bus.async_fire(EVENT_TAG_SCANNED, {"tag_id": "tag-x"})
    await hass.async_block_till_done()

    rec = coordinator.get_record(worn_item.entry_id)
    assert rec["state"] == "worn"
    assert rec["wear_count_total"] == 2  # second scan counted a re-wear

    rec = coordinator.get_record(washed_item.entry_id)
    assert rec["state"] == "clean"
    assert rec["wash_count"] == 1


async def test_open_scan_action_focuses_without_mutating(hass: HomeAssistant) -> None:
    entry = await setup_item(
        hass, name="Wool Coat", nfc_tag_id="tag-o", scan_action="open"
    )
    coordinator = coordinator_of(hass)
    scanned = async_capture_events(hass, EVENT_ITEM_SCANNED)
    changed = async_capture_events(hass, EVENT_STATE_CHANGED)

    hass.bus.async_fire(EVENT_TAG_SCANNED, {"tag_id": "tag-o", "device_id": "phone-1"})
    await hass.async_block_till_done()

    # State is untouched...
    assert coordinator.get_state(entry.entry_id) == "clean"
    assert not changed
    # ...but the scan is announced with the resolved item and scanning device.
    assert len(scanned) == 1
    data = scanned[0].data
    assert data["entry_id"] == entry.entry_id
    assert data["name"] == "Wool Coat"
    assert data["entity_id"] == entity_id(hass, "select", entry, "state")
    assert data["device_id"] == "phone-1"


async def test_scan_event_fires_even_when_mutating(hass: HomeAssistant) -> None:
    entry = await setup_item(hass, nfc_tag_id="tag-c", scan_action="mark_worn")
    coordinator = coordinator_of(hass)
    scanned = async_capture_events(hass, EVENT_ITEM_SCANNED)

    hass.bus.async_fire(EVENT_TAG_SCANNED, {"tag_id": "tag-c"})
    await hass.async_block_till_done()

    assert coordinator.get_state(entry.entry_id) == "worn"
    assert len(scanned) == 1
    assert scanned[0].data["entity_id"] == entity_id(hass, "select", entry, "state")


async def test_unmatched_tag_is_ignored(hass: HomeAssistant) -> None:
    entry = await setup_item(hass, nfc_tag_id="tag-1")
    coordinator = coordinator_of(hass)

    hass.bus.async_fire(EVENT_TAG_SCANNED, {"tag_id": "unknown"})
    await hass.async_block_till_done()
    assert coordinator.get_state(entry.entry_id) == "clean"


async def test_threshold_runtime_override(hass: HomeAssistant) -> None:
    """The runtime threshold (number entity backing) beats the config value."""
    entry = await setup_item(hass, wear_threshold=1)
    coordinator = coordinator_of(hass)
    assert coordinator.get_threshold(entry.entry_id) == 1

    await coordinator.async_set_threshold(entry.entry_id, 3)
    assert coordinator.get_threshold(entry.entry_id) == 3

    await coordinator.async_cycle_state(entry.entry_id)  # worn, wears=1
    assert await coordinator.async_cycle_state(entry.entry_id) == "worn"  # re-wear
    assert await coordinator.async_cycle_state(entry.entry_id) == "worn"  # re-wear
    assert await coordinator.async_cycle_state(entry.entry_id) == "laundry"


async def test_remove_entry_purges_record(hass: HomeAssistant) -> None:
    entry = await setup_item(hass)
    coordinator = coordinator_of(hass)
    await coordinator.async_mark_worn(entry.entry_id)
    assert entry.entry_id in coordinator.data

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.entry_id not in coordinator.data
