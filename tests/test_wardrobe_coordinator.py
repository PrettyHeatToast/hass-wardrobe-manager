"""Coordinator and tag-scan tests for the Wardrobe integration."""

from __future__ import annotations

from homeassistant.core import Event, HomeAssistant, callback

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wardrobe.const import (
    ATTR_LAST_WORN_AT,
    ATTR_STATE_CHANGED_AT,
    ATTR_WEAR_COUNT_TOTAL,
    ATTR_WEARS_SINCE_WASH,
    CONF_CATEGORY,
    CONF_ITEM_NAME,
    CONF_LAUNDRY_TYPE,
    CONF_NFC_TAG_ID,
    CONF_WEAR_THRESHOLD,
    DEFAULT_LAUNDRY_TYPE,
    DEFAULT_WEAR_THRESHOLD,
    DOMAIN,
    EVENT_STATE_CHANGED,
    EVENT_TAG_SCANNED,
)


async def _setup_entry(
    hass: HomeAssistant,
    *,
    name: str = "Blue Shirt",
    category: str = "shirt",
    nfc_tag_id: str | None = None,
    laundry_type: str = DEFAULT_LAUNDRY_TYPE,
    wear_threshold: int = DEFAULT_WEAR_THRESHOLD,
) -> MockConfigEntry:
    """Helper: create a MockConfigEntry, add it, run async_setup_entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=name,
        unique_id=name.lower().replace(" ", "_"),
        data={
            CONF_ITEM_NAME: name,
            CONF_CATEGORY: category,
            CONF_NFC_TAG_ID: nfc_tag_id,
            CONF_LAUNDRY_TYPE: laundry_type,
            CONF_WEAR_THRESHOLD: wear_threshold,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _get_coordinator(hass: HomeAssistant):
    return hass.data[DOMAIN]["shared"]["coordinator"]


async def test_entry_state_seeded_to_clean(hass: HomeAssistant) -> None:
    """A freshly added entry should start in the 'clean' state."""
    entry = await _setup_entry(hass)
    coordinator = _get_coordinator(hass)
    assert coordinator.get_state(entry.entry_id) == "clean"


async def test_entry_record_seeded_with_defaults(hass: HomeAssistant) -> None:
    """Counters and timestamps start at their default values."""
    entry = await _setup_entry(hass)
    coordinator = _get_coordinator(hass)
    rec = coordinator.get_record(entry.entry_id)
    assert rec["state"] == "clean"
    assert rec["wears_since_wash"] == 0
    assert rec["wear_count_total"] == 0
    assert rec["last_worn_at"] is None
    assert rec["state_changed_at"] is None


async def test_cycle_state_wraps(hass: HomeAssistant) -> None:
    """Cycling three times should walk clean → worn → laundry → clean."""
    entry = await _setup_entry(hass)
    coordinator = _get_coordinator(hass)

    assert await coordinator.async_cycle_state(entry.entry_id) == "worn"
    assert await coordinator.async_cycle_state(entry.entry_id) == "laundry"
    assert await coordinator.async_cycle_state(entry.entry_id) == "clean"


async def test_set_state_fires_event(hass: HomeAssistant) -> None:
    """async_set_state should emit wardrobe_state_changed with old + new + counters."""
    entry = await _setup_entry(hass)
    coordinator = _get_coordinator(hass)

    received: list[dict] = []

    @callback
    def _capture(event: Event) -> None:
        received.append(event.data)

    hass.bus.async_listen(EVENT_STATE_CHANGED, _capture)

    await coordinator.async_set_state(entry.entry_id, "worn")
    await hass.async_block_till_done()

    assert len(received) == 1
    payload = received[0]
    assert payload["entry_id"] == entry.entry_id
    assert payload["name"] == "Blue Shirt"
    assert payload["old_state"] == "clean"
    assert payload["new_state"] == "worn"
    assert payload[ATTR_WEARS_SINCE_WASH] == 1
    assert payload[ATTR_WEAR_COUNT_TOTAL] == 1
    assert payload[ATTR_LAST_WORN_AT] is not None
    assert payload[ATTR_STATE_CHANGED_AT] is not None


async def test_tag_scan_matches_entry_and_cycles(hass: HomeAssistant) -> None:
    """Firing tag_scanned with a known tag_id should advance the entry's state."""
    entry = await _setup_entry(hass, nfc_tag_id="abc-123")
    coordinator = _get_coordinator(hass)

    hass.bus.async_fire(EVENT_TAG_SCANNED, {"tag_id": "abc-123"})
    await hass.async_block_till_done()

    assert coordinator.get_state(entry.entry_id) == "worn"


async def test_tag_scan_unmatched_is_ignored(hass: HomeAssistant) -> None:
    """An unmatched tag_id must NOT mutate any entry's state."""
    entry = await _setup_entry(hass, nfc_tag_id="abc-123")
    coordinator = _get_coordinator(hass)

    hass.bus.async_fire(EVENT_TAG_SCANNED, {"tag_id": "different-tag"})
    await hass.async_block_till_done()

    assert coordinator.get_state(entry.entry_id) == "clean"


async def test_set_state_rejects_invalid_state(hass: HomeAssistant) -> None:
    """An invalid state value should raise rather than silently corrupt data."""
    entry = await _setup_entry(hass)
    coordinator = _get_coordinator(hass)

    try:
        await coordinator.async_set_state(entry.entry_id, "spaceship")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for invalid state")

    assert coordinator.get_state(entry.entry_id) == "clean"


async def test_removing_entry_purges_storage(hass: HomeAssistant) -> None:
    """Removing one of multiple entries should drop only that row."""
    entry1 = await _setup_entry(hass, name="Item One", nfc_tag_id="t1")
    entry2 = await _setup_entry(hass, name="Item Two", nfc_tag_id="t2")
    coordinator = _get_coordinator(hass)

    assert entry1.entry_id in coordinator.data
    assert entry2.entry_id in coordinator.data

    await hass.config_entries.async_remove(entry1.entry_id)
    await hass.async_block_till_done()

    assert entry1.entry_id not in coordinator.data
    assert entry2.entry_id in coordinator.data


async def test_last_entry_removal_tears_down_shared_bucket(
    hass: HomeAssistant,
) -> None:
    """Removing the final entry should remove the shared singleton entirely."""
    entry = await _setup_entry(hass, nfc_tag_id="only-tag")

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert "shared" not in hass.data.get(DOMAIN, {})


async def test_clean_to_worn_increments_both_counters(hass: HomeAssistant) -> None:
    """Transitioning into worn from a different state bumps both counters."""
    entry = await _setup_entry(hass)
    coordinator = _get_coordinator(hass)

    await coordinator.async_set_state(entry.entry_id, "worn")
    rec = coordinator.get_record(entry.entry_id)
    assert rec["wears_since_wash"] == 1
    assert rec["wear_count_total"] == 1
    assert rec["last_worn_at"] is not None


async def test_worn_to_worn_is_noop_for_counters(hass: HomeAssistant) -> None:
    """A repeated set_state(worn) must not double-count."""
    entry = await _setup_entry(hass)
    coordinator = _get_coordinator(hass)

    await coordinator.async_set_state(entry.entry_id, "worn")
    rec_after_first = coordinator.get_record(entry.entry_id)
    last_worn = rec_after_first["last_worn_at"]
    state_changed = rec_after_first["state_changed_at"]

    await coordinator.async_set_state(entry.entry_id, "worn")
    rec_after_second = coordinator.get_record(entry.entry_id)

    assert rec_after_second["wears_since_wash"] == 1
    assert rec_after_second["wear_count_total"] == 1
    assert rec_after_second["last_worn_at"] == last_worn
    assert rec_after_second["state_changed_at"] == state_changed


async def test_into_laundry_resets_wears_since_wash(hass: HomeAssistant) -> None:
    """Entering laundry resets the per-cycle counter but preserves the lifetime one."""
    entry = await _setup_entry(hass)
    coordinator = _get_coordinator(hass)

    await coordinator.async_set_state(entry.entry_id, "worn")
    await coordinator.async_set_state(entry.entry_id, "laundry")

    rec = coordinator.get_record(entry.entry_id)
    assert rec["wears_since_wash"] == 0
    assert rec["wear_count_total"] == 1


async def test_lifetime_counter_accumulates_across_cycles(
    hass: HomeAssistant,
) -> None:
    """wear_count_total is monotonic across multiple wash cycles."""
    entry = await _setup_entry(hass)
    coordinator = _get_coordinator(hass)

    # clean → worn → laundry → clean → worn → laundry
    for state in ("worn", "laundry", "clean", "worn", "laundry"):
        await coordinator.async_set_state(entry.entry_id, state)

    rec = coordinator.get_record(entry.entry_id)
    assert rec["wear_count_total"] == 2
    assert rec["wears_since_wash"] == 0


async def test_state_changed_at_updates_on_every_transition(
    hass: HomeAssistant,
) -> None:
    """state_changed_at advances when state changes, holds when it doesn't."""
    entry = await _setup_entry(hass)
    coordinator = _get_coordinator(hass)

    await coordinator.async_set_state(entry.entry_id, "worn")
    first = coordinator.get_record(entry.entry_id)["state_changed_at"]

    # No-op transition: timestamp should not advance.
    await coordinator.async_set_state(entry.entry_id, "worn")
    same = coordinator.get_record(entry.entry_id)["state_changed_at"]
    assert same == first

    # Real transition: timestamp must advance.
    await coordinator.async_set_state(entry.entry_id, "laundry")
    later = coordinator.get_record(entry.entry_id)["state_changed_at"]
    assert later is not None and first is not None
    assert later > first
