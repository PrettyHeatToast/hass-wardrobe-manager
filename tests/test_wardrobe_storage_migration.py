"""Storage migration tests: v1 (raw state string) → v2 (full record dict)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wardrobe.const import (
    CONF_CATEGORY,
    CONF_ITEM_NAME,
    CONF_LAUNDRY_TYPE,
    CONF_NFC_TAG_ID,
    CONF_WEAR_THRESHOLD,
    DEFAULT_LAUNDRY_TYPE,
    DOMAIN,
    STORAGE_KEY,
)


def _v1_blob(entries: dict[str, str]) -> dict:
    return {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {"entries": entries},
    }


def _make_entry(entry_id: str, *, name: str = "Item") -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        title=name,
        unique_id=name.lower().replace(" ", "_"),
        data={
            CONF_ITEM_NAME: name,
            CONF_CATEGORY: "shirt",
            CONF_NFC_TAG_ID: None,
            CONF_LAUNDRY_TYPE: DEFAULT_LAUNDRY_TYPE,
            CONF_WEAR_THRESHOLD: 0,
        },
    )


async def test_v1_state_string_migrates_to_v2_record(
    hass: HomeAssistant, hass_storage
) -> None:
    """Each v1 row (just a state string) becomes a full v2 record."""
    hass_storage[STORAGE_KEY] = _v1_blob({"entry-1": "worn"})
    entry = _make_entry("entry-1", name="Blue Shirt")
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN]["shared"]["coordinator"]
    rec = coordinator.get_record("entry-1")
    assert rec["state"] == "worn"
    assert rec["wears_since_wash"] == 0
    assert rec["wear_count_total"] == 0
    assert rec["last_worn_at"] is None
    assert rec["state_changed_at"] is None


async def test_v1_garbage_state_coerces_to_default(
    hass: HomeAssistant, hass_storage
) -> None:
    """Unknown state strings in v1 storage migrate to the default state."""
    hass_storage[STORAGE_KEY] = _v1_blob({"entry-bad": "spaceship"})
    entry = _make_entry("entry-bad", name="Bad Item")
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN]["shared"]["coordinator"]
    assert coordinator.get_state("entry-bad") == "clean"


async def test_v1_storage_persists_at_v2_after_save(
    hass: HomeAssistant, hass_storage
) -> None:
    """After any state change, storage is rewritten with version=2 and v2 records."""
    hass_storage[STORAGE_KEY] = _v1_blob({"entry-keep": "laundry"})
    entry = _make_entry("entry-keep", name="Keep Item")
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN]["shared"]["coordinator"]
    # Trigger a save by cycling the state.
    await coordinator.async_set_state("entry-keep", "clean")
    await hass.async_block_till_done()

    stored = hass_storage[STORAGE_KEY]
    assert stored["version"] == 2
    entries = stored["data"]["entries"]
    assert isinstance(entries["entry-keep"], dict)
    assert entries["entry-keep"]["state"] == "clean"
    assert "wears_since_wash" in entries["entry-keep"]
    assert "wear_count_total" in entries["entry-keep"]
