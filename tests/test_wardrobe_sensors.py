"""Sensor platform tests: per-item sensors + household summary sensors."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wardrobe.const import (
    ATTR_BY_CATEGORY,
    ATTR_BY_LAUNDRY_TYPE,
    ATTR_ITEMS,
    CONF_CATEGORY,
    CONF_ITEM_NAME,
    CONF_KIND,
    CONF_LAUNDRY_TYPE,
    CONF_NFC_TAG_ID,
    CONF_WEAR_THRESHOLD,
    DEFAULT_LAUNDRY_TYPE,
    DOMAIN,
    KIND_SUMMARY,
)


async def _setup_item(
    hass: HomeAssistant,
    *,
    name: str,
    category: str = "shirt",
    laundry_type: str = DEFAULT_LAUNDRY_TYPE,
    wear_threshold: int = 0,
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=name,
        unique_id=name.lower().replace(" ", "_"),
        data={
            CONF_ITEM_NAME: name,
            CONF_CATEGORY: category,
            CONF_NFC_TAG_ID: None,
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


async def test_per_item_sensors_registered(hass: HomeAssistant) -> None:
    """Every item gets four sensors (counter ×2, timestamp ×2)."""
    entry = await _setup_item(hass, name="Blue Shirt")

    registry = er.async_get(hass)
    for suffix in (
        "wears_since_wash",
        "wear_count_total",
        "last_worn_at",
        "state_changed_at",
    ):
        unique_id = f"{DOMAIN}_{entry.entry_id}_{suffix}"
        entry_in_reg = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        assert entry_in_reg is not None, f"missing sensor for {suffix}"


async def test_wears_since_wash_sensor_value_updates(hass: HomeAssistant) -> None:
    """The wears_since_wash sensor reflects coordinator state after a transition."""
    entry = await _setup_item(hass, name="Blue Shirt")
    coordinator = _get_coordinator(hass)

    await coordinator.async_set_state(entry.entry_id, "worn")
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    eid = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{DOMAIN}_{entry.entry_id}_wears_since_wash"
    )
    state = hass.states.get(eid)
    assert state is not None
    assert state.state == "1"


async def test_last_worn_at_sensor_populated_after_wear(
    hass: HomeAssistant,
) -> None:
    """last_worn_at sensor becomes a real timestamp after entering 'worn'."""
    entry = await _setup_item(hass, name="Blue Shirt")
    coordinator = _get_coordinator(hass)

    await coordinator.async_set_state(entry.entry_id, "worn")
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    eid = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{DOMAIN}_{entry.entry_id}_last_worn_at"
    )
    state = hass.states.get(eid)
    assert state is not None
    # Timestamp device class renders as ISO 8601 string, not "unknown".
    assert state.state not in ("unknown", "unavailable", "")


async def test_summary_sensors_added_once_across_entries(
    hass: HomeAssistant,
) -> None:
    """Three summary sensors total, regardless of how many items are added."""
    await _setup_item(hass, name="Item A")
    await _setup_item(hass, name="Item B")
    await _setup_item(hass, name="Item C")

    registry = er.async_get(hass)
    summary_ids = [
        registry.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_summary_{state}")
        for state in ("clean", "worn", "laundry")
    ]
    assert all(s is not None for s in summary_ids)


async def test_summary_sensor_counts_and_breakdowns(hass: HomeAssistant) -> None:
    """Summary 'worn' sensor reflects count and breakdown attributes."""
    a = await _setup_item(hass, name="Shirt A", category="shirt", laundry_type="dark")
    b = await _setup_item(hass, name="Shirt B", category="shirt", laundry_type="dark")
    c = await _setup_item(hass, name="Pants C", category="pants", laundry_type="light")

    coordinator = _get_coordinator(hass)
    for entry in (a, b, c):
        await coordinator.async_set_state(entry.entry_id, "worn")
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    eid = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{DOMAIN}_summary_worn"
    )
    state = hass.states.get(eid)
    assert state is not None
    assert state.state == "3"
    assert state.attributes[ATTR_BY_CATEGORY] == {"shirt": 2, "pants": 1}
    assert state.attributes[ATTR_BY_LAUNDRY_TYPE] == {"dark": 2, "light": 1}
    assert state.attributes[ATTR_ITEMS] == ["Pants C", "Shirt A", "Shirt B"]


async def test_summary_sensors_belong_to_hub_entry(hass: HomeAssistant) -> None:
    """Summary entities are registered against the auto-created hub entry."""
    await _setup_item(hass, name="Item Z")

    hub_entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.data.get(CONF_KIND) == KIND_SUMMARY
    ]
    assert len(hub_entries) == 1
    hub = hub_entries[0]

    registry = er.async_get(hass)
    for state in ("clean", "worn", "laundry"):
        eid = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{DOMAIN}_summary_{state}"
        )
        assert eid is not None
        rec = registry.async_get(eid)
        assert rec is not None
        assert rec.config_entry_id == hub.entry_id


async def test_summary_sensors_track_state_changes(hass: HomeAssistant) -> None:
    """When an item changes state, the relevant summary counts move."""
    entry = await _setup_item(hass, name="Sock")
    coordinator = _get_coordinator(hass)

    registry = er.async_get(hass)
    clean_id = registry.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_summary_clean")
    laundry_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{DOMAIN}_summary_laundry"
    )

    assert hass.states.get(clean_id).state == "1"
    assert hass.states.get(laundry_id).state == "0"

    await coordinator.async_set_state(entry.entry_id, "laundry")
    await hass.async_block_till_done()

    assert hass.states.get(clean_id).state == "0"
    assert hass.states.get(laundry_id).state == "1"
