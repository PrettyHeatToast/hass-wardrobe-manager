"""Config-flow and options-flow tests."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.wardrobe.const import (
    CONF_BRAND,
    CONF_CATEGORY,
    CONF_EXTRA_STATES,
    CONF_ITEM_NAME,
    CONF_KIND,
    CONF_LAUNDRY_TYPE,
    CONF_LOAD_SIZE,
    CONF_NFC_TAG_ID,
    CONF_NOTES,
    CONF_PURCHASE_PRICE,
    CONF_QUANTITY,
    CONF_SCAN_ACTION,
    CONF_SEASONS,
    CONF_TRACKING_MODE,
    CONF_WEAR_THRESHOLD,
    CONF_WEIGHT,
    DOMAIN,
    KIND_SUMMARY,
    TrackingMode,
    load_size_key,
)

from .helpers import setup_bulk_item, setup_item

BASICS = {
    CONF_ITEM_NAME: "White Tee",
    CONF_CATEGORY: "t_shirt",
    CONF_LAUNDRY_TYPE: "light",
}
TRACKING = {
    CONF_NFC_TAG_ID: "tag-42",
    CONF_SCAN_ACTION: "cycle",
    CONF_EXTRA_STATES: ["washing"],
    CONF_WEAR_THRESHOLD: 3,
}
DETAILS = {
    CONF_BRAND: "  Acme  ",
    "size": "M",
    "color": "",
    CONF_SEASONS: ["summer"],
    CONF_PURCHASE_PRICE: 19.99,
    CONF_NOTES: "",
}


async def _walk_create_flow(hass: HomeAssistant, details: dict | None = None):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], BASICS
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "tracking"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], TRACKING
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "details"

    return await hass.config_entries.flow.async_configure(
        result["flow_id"], details if details is not None else DETAILS
    )


async def test_full_three_step_creation(hass: HomeAssistant) -> None:
    result = await _walk_create_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "White Tee"

    data = result["data"]
    assert data[CONF_CATEGORY] == "t_shirt"
    assert data[CONF_LAUNDRY_TYPE] == "light"
    assert data[CONF_NFC_TAG_ID] == "tag-42"
    assert data[CONF_EXTRA_STATES] == ["washing"]
    assert data[CONF_WEAR_THRESHOLD] == 3
    # Details normalization: strip whitespace, drop empties.
    assert data[CONF_BRAND] == "Acme"
    assert data["size"] == "M"
    assert "color" not in data
    assert CONF_NOTES not in data
    assert data[CONF_SEASONS] == ["summer"]
    assert data[CONF_PURCHASE_PRICE] == 19.99


async def test_duplicate_name_aborts(hass: HomeAssistant) -> None:
    await setup_item(hass, name="White Tee")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], BASICS
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_duplicate_tag_shows_error(hass: HomeAssistant) -> None:
    await setup_item(hass, name="Other Item", nfc_tag_id="tag-42")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], BASICS
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], TRACKING
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "tracking"
    assert result["errors"] == {CONF_NFC_TAG_ID: "tag_exists"}


async def test_hub_is_auto_created_once(hass: HomeAssistant) -> None:
    await setup_item(hass, name="Item One")
    await setup_item(hass, name="Item Two")

    hubs = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.data.get(CONF_KIND) == KIND_SUMMARY
    ]
    assert len(hubs) == 1


async def test_options_menu_basics(hass: HomeAssistant) -> None:
    entry = await setup_item(hass, category="t_shirt")

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "basics"}
    )
    assert result["step_id"] == "basics"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_CATEGORY: "jeans", CONF_LAUNDRY_TYPE: "dark"},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.data[CONF_CATEGORY] == "jeans"


async def test_options_tracking_rejects_taken_tag(hass: HomeAssistant) -> None:
    await setup_item(hass, name="Owner", nfc_tag_id="tag-9")
    entry = await setup_item(hass, name="Editme")

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "tracking"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_NFC_TAG_ID: "tag-9", CONF_SCAN_ACTION: "cycle", CONF_EXTRA_STATES: []},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_NFC_TAG_ID: "tag_exists"}


async def test_options_details_can_clear_fields(hass: HomeAssistant) -> None:
    entry = await setup_item(hass, brand="Acme", notes="old note")

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "details"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_BRAND: "", CONF_NOTES: "", "size": "L"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert CONF_BRAND not in entry.data
    assert CONF_NOTES not in entry.data
    assert entry.data["size"] == "L"
    # Non-details keys are untouched.
    assert entry.data[CONF_ITEM_NAME] == "Blue Shirt"


async def test_hub_options_set_load_size(hass: HomeAssistant) -> None:
    await setup_item(hass)
    hub = next(
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.data.get(CONF_KIND) == KIND_SUMMARY
    )

    result = await hass.config_entries.options.async_init(hub.entry_id)
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_LOAD_SIZE: 3}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hub.options[CONF_LOAD_SIZE] == 3


async def test_full_creation_persists_weight(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], BASICS)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**TRACKING, CONF_WEIGHT: 1.5}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_WEIGHT] == 1.5
    assert result["data"][CONF_TRACKING_MODE] == TrackingMode.INDIVIDUAL


async def test_bulk_creation_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ITEM_NAME: "Black Socks",
            CONF_CATEGORY: "socks",
            CONF_LAUNDRY_TYPE: "dark",
            CONF_TRACKING_MODE: TrackingMode.BULK.value,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "bulk"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_QUANTITY: 8, CONF_WEIGHT: 0.5}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "details"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY

    data = result["data"]
    assert data[CONF_TRACKING_MODE] == TrackingMode.BULK
    assert data[CONF_QUANTITY] == 8
    assert data[CONF_WEIGHT] == 0.5
    # Neutral tracking defaults so downstream lookups stay uniform.
    assert data[CONF_NFC_TAG_ID] is None
    assert data[CONF_EXTRA_STATES] == []
    assert data[CONF_WEAR_THRESHOLD] == 0


async def test_bulk_options_menu_has_no_tracking(hass: HomeAssistant) -> None:
    entry = await setup_bulk_item(hass, quantity=10)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert result["menu_options"] == ["basics", "details"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "basics"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_CATEGORY: "socks", CONF_LAUNDRY_TYPE: "color", CONF_QUANTITY: 12},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.data[CONF_QUANTITY] == 12
    assert entry.data[CONF_LAUNDRY_TYPE] == "color"


async def test_hub_options_per_type_overrides(hass: HomeAssistant) -> None:
    await setup_item(hass)
    hub = next(
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.data.get(CONF_KIND) == KIND_SUMMARY
    )

    result = await hass.config_entries.options.async_init(hub.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_LOAD_SIZE: 4, load_size_key("wool"): 1.5}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert hub.options[CONF_LOAD_SIZE] == 4
    assert hub.options[load_size_key("wool")] == 1.5
    # Types left blank get no override key → they fall back to the default.
    assert load_size_key("dark") not in hub.options
