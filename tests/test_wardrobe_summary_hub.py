"""Singleton Summary hub: auto-discovery on item add + v1.1 migration."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wardrobe.const import (
    CONF_CATEGORY,
    CONF_ITEM_NAME,
    CONF_KIND,
    CONF_LAUNDRY_TYPE,
    CONF_NFC_TAG_ID,
    CONF_WEAR_THRESHOLD,
    DEFAULT_LAUNDRY_TYPE,
    DOMAIN,
    KIND_SUMMARY,
    STATES,
    SUMMARY_DEVICE_ID,
    SUMMARY_DEVICE_NAME,
)


def _make_item(name: str, *, tag: str | None = None) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=name,
        unique_id=name.lower().replace(" ", "_"),
        data={
            CONF_ITEM_NAME: name,
            CONF_CATEGORY: "shirt",
            CONF_NFC_TAG_ID: tag,
            CONF_LAUNDRY_TYPE: DEFAULT_LAUNDRY_TYPE,
            CONF_WEAR_THRESHOLD: 0,
        },
    )


def _hubs(hass: HomeAssistant) -> list[MockConfigEntry]:
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.data.get(CONF_KIND) == KIND_SUMMARY
    ]


async def test_first_item_setup_auto_creates_hub(hass: HomeAssistant) -> None:
    """Setting up an item triggers integration-discovery and creates one hub."""
    item = _make_item("First")
    item.add_to_hass(hass)
    assert await hass.config_entries.async_setup(item.entry_id)
    await hass.async_block_till_done()

    hubs = _hubs(hass)
    assert len(hubs) == 1
    assert hubs[0].title == SUMMARY_DEVICE_NAME


async def test_multiple_items_only_create_one_hub(hass: HomeAssistant) -> None:
    """Subsequent items reuse the existing hub — no duplicates."""
    for name in ("A", "B", "C"):
        entry = _make_item(name)
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert len(_hubs(hass)) == 1


async def test_migration_moves_summary_entities_to_hub(
    hass: HomeAssistant,
) -> None:
    """v1.1 layout: summary entities + device linked to an item entry.

    After v1.2 setup the entities must be reassociated to the hub, entity_ids
    preserved, and the summary device must no longer reference the item entry.
    """
    item = _make_item("OG Shirt")
    item.add_to_hass(hass)

    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    summary_device = dev_reg.async_get_or_create(
        config_entry_id=item.entry_id,
        identifiers={(DOMAIN, SUMMARY_DEVICE_ID)},
        name=SUMMARY_DEVICE_NAME,
    )

    pre_entity_ids: dict[str, str] = {}
    for state in STATES:
        unique_id = f"{DOMAIN}_summary_{state}"
        rec = ent_reg.async_get_or_create(
            domain="sensor",
            platform=DOMAIN,
            unique_id=unique_id,
            config_entry=item,
            device_id=summary_device.id,
            suggested_object_id=f"wardrobe_summary_{state}",
        )
        pre_entity_ids[state] = rec.entity_id
        assert rec.config_entry_id == item.entry_id

    assert await hass.config_entries.async_setup(item.entry_id)
    await hass.async_block_till_done()

    hubs = _hubs(hass)
    assert len(hubs) == 1
    hub = hubs[0]

    for state in STATES:
        unique_id = f"{DOMAIN}_summary_{state}"
        eid = ent_reg.async_get_entity_id("sensor", DOMAIN, unique_id)
        assert eid == pre_entity_ids[state]
        rec = ent_reg.async_get(eid)
        assert rec is not None
        assert rec.config_entry_id == hub.entry_id

    updated_device = dev_reg.async_get_device(
        identifiers={(DOMAIN, SUMMARY_DEVICE_ID)}
    )
    assert updated_device is not None
    assert hub.entry_id in updated_device.config_entries
    assert item.entry_id not in updated_device.config_entries
