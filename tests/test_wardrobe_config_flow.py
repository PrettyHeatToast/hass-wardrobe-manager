"""Config-flow tests for the Wardrobe integration."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

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
)


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """User-step happy path: form opens, submit creates an entry with all fields."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_ITEM_NAME: "Blue Shirt",
            CONF_CATEGORY: "shirt",
            CONF_LAUNDRY_TYPE: "color",
            CONF_WEAR_THRESHOLD: 5,
            CONF_NFC_TAG_ID: "04:AB:CD:EF",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Blue Shirt"
    assert result["data"] == {
        CONF_ITEM_NAME: "Blue Shirt",
        CONF_CATEGORY: "shirt",
        CONF_NFC_TAG_ID: "04:AB:CD:EF",
        CONF_LAUNDRY_TYPE: "color",
        CONF_WEAR_THRESHOLD: 5,
    }


async def test_user_flow_allows_missing_tag(hass: HomeAssistant) -> None:
    """The NFC tag is optional and stored as None when omitted."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_ITEM_NAME: "Yellow Pants",
            CONF_CATEGORY: "pants",
            CONF_LAUNDRY_TYPE: "light",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_NFC_TAG_ID] is None
    assert result["data"][CONF_LAUNDRY_TYPE] == "light"
    assert result["data"][CONF_WEAR_THRESHOLD] == 0


async def test_duplicate_name_aborts(hass: HomeAssistant) -> None:
    """Adding a second item with the same slugified name aborts the flow."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        title="Blue Shirt",
        unique_id="blue_shirt",
        data={
            CONF_ITEM_NAME: "Blue Shirt",
            CONF_CATEGORY: "shirt",
            CONF_NFC_TAG_ID: None,
            CONF_LAUNDRY_TYPE: DEFAULT_LAUNDRY_TYPE,
            CONF_WEAR_THRESHOLD: 0,
        },
    )
    existing.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_ITEM_NAME: "Blue Shirt",
            CONF_CATEGORY: "shirt",
            CONF_LAUNDRY_TYPE: DEFAULT_LAUNDRY_TYPE,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_duplicate_tag_shows_error(hass: HomeAssistant) -> None:
    """A second item attempting to claim the same NFC tag should error in-form."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        title="Existing Item",
        unique_id="existing_item",
        data={
            CONF_ITEM_NAME: "Existing Item",
            CONF_CATEGORY: "shirt",
            CONF_NFC_TAG_ID: "04:AB:CD:EF",
            CONF_LAUNDRY_TYPE: DEFAULT_LAUNDRY_TYPE,
            CONF_WEAR_THRESHOLD: 0,
        },
    )
    existing.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_ITEM_NAME: "New Item",
            CONF_CATEGORY: "shirt",
            CONF_LAUNDRY_TYPE: DEFAULT_LAUNDRY_TYPE,
            CONF_NFC_TAG_ID: "04:AB:CD:EF",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_NFC_TAG_ID: "tag_exists"}


async def test_options_flow_updates_entry_data(hass: HomeAssistant) -> None:
    """OptionsFlow rewrites category, laundry_type, threshold and tag_id."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Blue Shirt",
        unique_id="blue_shirt",
        data={
            CONF_ITEM_NAME: "Blue Shirt",
            CONF_CATEGORY: "shirt",
            CONF_NFC_TAG_ID: None,
            CONF_LAUNDRY_TYPE: "dark",
            CONF_WEAR_THRESHOLD: 0,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_CATEGORY: "jacket",
            CONF_LAUNDRY_TYPE: "delicates",
            CONF_WEAR_THRESHOLD: 3,
            CONF_NFC_TAG_ID: "new-tag-123",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_CATEGORY] == "jacket"
    assert entry.data[CONF_LAUNDRY_TYPE] == "delicates"
    assert entry.data[CONF_WEAR_THRESHOLD] == 3
    assert entry.data[CONF_NFC_TAG_ID] == "new-tag-123"
    assert entry.data[CONF_ITEM_NAME] == "Blue Shirt"


async def test_integration_discovery_creates_singleton_hub(
    hass: HomeAssistant,
) -> None:
    """The integration_discovery step creates exactly one Wardrobe Summary hub."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
        data={},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Wardrobe Summary"
    assert result["data"] == {CONF_KIND: KIND_SUMMARY}

    # A second discovery must abort — only one hub may exist.
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
        data={},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_aborts_for_hub(hass: HomeAssistant) -> None:
    """The Wardrobe Summary hub has no editable options."""
    hub = MockConfigEntry(
        domain=DOMAIN,
        title="Wardrobe Summary",
        unique_id="_wardrobe_summary_hub",
        data={CONF_KIND: KIND_SUMMARY},
    )
    hub.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(hub.entry_id)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_options"


async def test_options_flow_rejects_duplicate_tag(hass: HomeAssistant) -> None:
    """OptionsFlow should not let one entry steal another entry's tag."""
    other = MockConfigEntry(
        domain=DOMAIN,
        title="Other",
        unique_id="other",
        data={
            CONF_ITEM_NAME: "Other",
            CONF_CATEGORY: "shirt",
            CONF_NFC_TAG_ID: "shared-tag",
            CONF_LAUNDRY_TYPE: DEFAULT_LAUNDRY_TYPE,
            CONF_WEAR_THRESHOLD: 0,
        },
    )
    other.add_to_hass(hass)

    target = MockConfigEntry(
        domain=DOMAIN,
        title="Target",
        unique_id="target",
        data={
            CONF_ITEM_NAME: "Target",
            CONF_CATEGORY: "shirt",
            CONF_NFC_TAG_ID: None,
            CONF_LAUNDRY_TYPE: DEFAULT_LAUNDRY_TYPE,
            CONF_WEAR_THRESHOLD: 0,
        },
    )
    target.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(target.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_CATEGORY: "shirt",
            CONF_LAUNDRY_TYPE: DEFAULT_LAUNDRY_TYPE,
            CONF_NFC_TAG_ID: "shared-tag",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_NFC_TAG_ID: "tag_exists"}
