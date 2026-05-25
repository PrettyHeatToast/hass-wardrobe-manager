"""Coordinator and tag-scan tests for the Wardrobe integration."""

from __future__ import annotations

from homeassistant.core import Event, HomeAssistant, callback

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wardrobe.const import (
    CONF_CATEGORY,
    CONF_ITEM_NAME,
    CONF_NFC_TAG_ID,
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


async def test_cycle_state_wraps(hass: HomeAssistant) -> None:
    """Cycling three times should walk clean → worn → laundry → clean."""
    entry = await _setup_entry(hass)
    coordinator = _get_coordinator(hass)

    assert await coordinator.async_cycle_state(entry.entry_id) == "worn"
    assert await coordinator.async_cycle_state(entry.entry_id) == "laundry"
    assert await coordinator.async_cycle_state(entry.entry_id) == "clean"


async def test_set_state_fires_event(hass: HomeAssistant) -> None:
    """async_set_state should emit wardrobe_state_changed with old + new."""
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
    assert received[0]["entry_id"] == entry.entry_id
    assert received[0]["name"] == "Blue Shirt"
    assert received[0]["old_state"] == "clean"
    assert received[0]["new_state"] == "worn"


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

    # entry2 keeps the shared bucket alive so the same coordinator object
    # remains the source of truth after entry1 is removed.
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
