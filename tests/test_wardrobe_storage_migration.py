"""Storage migration tests: v1/v2/v3 payloads → v4 records."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.wardrobe.const import STORAGE_KEY

from .helpers import coordinator_of, make_item


def _blob(version: int, entries: dict) -> dict:
    return {
        "version": version,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {"entries": entries},
    }


async def _setup(hass: HomeAssistant, entry_id: str, **kwargs) -> None:
    entry = make_item(entry_id=entry_id, **kwargs)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_v1_state_string_migrates_to_v4(hass: HomeAssistant, hass_storage) -> None:
    hass_storage[STORAGE_KEY] = _blob(1, {"entry-1": "worn"})
    await _setup(hass, "entry-1", wear_threshold=4)

    rec = coordinator_of(hass).get_record("entry-1")
    assert rec["state"] == "worn"
    assert rec["wears_since_wash"] == 0
    assert rec["wear_count_total"] == 0
    assert rec["wash_count"] == 0
    assert rec["last_washed_at"] is None
    # The threshold is adopted from the ConfigEntry on first setup.
    assert rec["wear_threshold"] == 4
    # No weight configured → seeded with the default.
    assert rec["weight"] == 1.0
    assert rec["dirty_count"] == 0


async def test_v1_garbage_state_coerces_to_default(
    hass: HomeAssistant, hass_storage
) -> None:
    hass_storage[STORAGE_KEY] = _blob(1, {"entry-bad": "spaceship"})
    await _setup(hass, "entry-bad", name="Bad Item")
    assert coordinator_of(hass).get_state("entry-bad") == "clean"


async def test_v2_record_gains_new_fields(hass: HomeAssistant, hass_storage) -> None:
    hass_storage[STORAGE_KEY] = _blob(
        2,
        {
            "entry-2": {
                "state": "laundry",
                "wears_since_wash": 3,
                "wear_count_total": 17,
                "last_worn_at": "2026-07-01T10:00:00+00:00",
                "state_changed_at": "2026-07-02T10:00:00+00:00",
            }
        },
    )
    await _setup(hass, "entry-2", name="Old Jeans", wear_threshold=5)

    rec = coordinator_of(hass).get_record("entry-2")
    assert rec["state"] == "laundry"
    assert rec["wears_since_wash"] == 3
    assert rec["wear_count_total"] == 17
    assert rec["wash_count"] == 0
    assert rec["last_washed_at"] is None
    assert rec["last_worn_at"] == "2026-07-01T10:00:00+00:00"
    assert rec["wear_threshold"] == 5


async def test_v3_record_gains_weight_and_dirty_count(
    hass: HomeAssistant, hass_storage
) -> None:
    hass_storage[STORAGE_KEY] = _blob(
        3,
        {
            "entry-v3": {
                "state": "laundry",
                "wears_since_wash": 2,
                "wear_count_total": 9,
                "wash_count": 4,
                "last_worn_at": "2026-07-01T10:00:00+00:00",
                "last_washed_at": "2026-06-20T10:00:00+00:00",
                "state_changed_at": "2026-07-02T10:00:00+00:00",
                "wear_threshold": 3,
            }
        },
    )
    await _setup(hass, "entry-v3", name="Grey Hoodie", weight=1.5)

    rec = coordinator_of(hass).get_record("entry-v3")
    # Existing v3 fields survive untouched.
    assert rec["state"] == "laundry"
    assert rec["wear_threshold"] == 3
    assert rec["wash_count"] == 4
    # New fields: weight seeded from the ConfigEntry, dirty_count defaulted.
    assert rec["weight"] == 1.5
    assert rec["dirty_count"] == 0


async def test_v4_storage_survives_roundtrip(hass: HomeAssistant, hass_storage) -> None:
    await _setup(hass, "entry-3", name="Fresh Item")
    coordinator = coordinator_of(hass)
    await coordinator.async_mark_worn("entry-3")

    saved = hass_storage[STORAGE_KEY]
    assert saved["version"] == 4
    row = saved["data"]["entries"]["entry-3"]
    assert row["state"] == "worn"
    assert row["wear_count_total"] == 1
    assert row["weight"] == 1.0
    assert row["dirty_count"] == 0
