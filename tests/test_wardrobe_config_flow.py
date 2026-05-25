"""Config-flow tests for the Wardrobe integration."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wardrobe.const import (
    CONF_CATEGORY,
    CONF_ITEM_NAME,
    CONF_NFC_TAG_ID,
    DOMAIN,
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
            CONF_NFC_TAG_ID: "04:AB:CD:EF",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Blue Shirt"
    assert result["data"] == {
        CONF_ITEM_NAME: "Blue Shirt",
        CONF_CATEGORY: "shirt",
        CONF_NFC_TAG_ID: "04:AB:CD:EF",
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
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_NFC_TAG_ID] is None


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
            CONF_NFC_TAG_ID: "04:AB:CD:EF",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_NFC_TAG_ID: "tag_exists"}


async def test_options_flow_updates_entry_data(hass: HomeAssistant) -> None:
    """OptionsFlow rewrites category and tag_id in the entry's data dict."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Blue Shirt",
        unique_id="blue_shirt",
        data={
            CONF_ITEM_NAME: "Blue Shirt",
            CONF_CATEGORY: "shirt",
            CONF_NFC_TAG_ID: None,
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
            CONF_NFC_TAG_ID: "new-tag-123",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_CATEGORY] == "jacket"
    assert entry.data[CONF_NFC_TAG_ID] == "new-tag-123"
    # Name is untouched by the OptionsFlow.
    assert entry.data[CONF_ITEM_NAME] == "Blue Shirt"


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
        },
    )
    target.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(target.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_CATEGORY: "shirt",
            CONF_NFC_TAG_ID: "shared-tag",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_NFC_TAG_ID: "tag_exists"}
