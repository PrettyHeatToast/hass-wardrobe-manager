"""Config flow for the Wardrobe integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util import slugify

from .const import (
    CATEGORY_ICONS,
    CONF_CATEGORY,
    CONF_ITEM_NAME,
    CONF_NFC_TAG_ID,
    DOMAIN,
)


def _category_selector() -> SelectSelector:
    """Build the dropdown selector for the category field."""
    return SelectSelector(
        SelectSelectorConfig(
            options=list(CATEGORY_ICONS.keys()),
            translation_key="category",
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


class WardrobeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the user-initiated flow that adds a single wardrobe item."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the name, category and (optional) NFC tag for a new item."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input[CONF_ITEM_NAME].strip()
            await self.async_set_unique_id(slugify(name))
            self._abort_if_unique_id_configured()

            tag = (user_input.get(CONF_NFC_TAG_ID) or "").strip() or None
            if tag and self._tag_in_use(tag):
                errors[CONF_NFC_TAG_ID] = "tag_exists"

            if not errors:
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_ITEM_NAME: name,
                        CONF_CATEGORY: user_input[CONF_CATEGORY],
                        CONF_NFC_TAG_ID: tag,
                    },
                )

        suggested = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ITEM_NAME,
                    default=suggested.get(CONF_ITEM_NAME, vol.UNDEFINED),
                ): str,
                vol.Required(
                    CONF_CATEGORY,
                    default=suggested.get(CONF_CATEGORY, "shirt"),
                ): _category_selector(),
                vol.Optional(
                    CONF_NFC_TAG_ID,
                    default=suggested.get(CONF_NFC_TAG_ID, ""),
                ): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    def _tag_in_use(self, tag: str) -> bool:
        """Return True if any existing entry already claims this NFC tag."""
        for entry in self._async_current_entries():
            if entry.data.get(CONF_NFC_TAG_ID) == tag:
                return True
        return False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> WardrobeOptionsFlow:
        """Return the options flow handler for an existing entry."""
        return WardrobeOptionsFlow()


class WardrobeOptionsFlow(OptionsFlow):
    """Edit the category and NFC tag ID of a previously registered item."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the edit form and persist changes back to ``entry.data``."""
        errors: dict[str, str] = {}

        if user_input is not None:
            tag = (user_input.get(CONF_NFC_TAG_ID) or "").strip() or None

            if tag and self._tag_in_use(tag):
                errors[CONF_NFC_TAG_ID] = "tag_exists"

            if not errors:
                new_data = {
                    **self.config_entry.data,
                    CONF_CATEGORY: user_input[CONF_CATEGORY],
                    CONF_NFC_TAG_ID: tag,
                }
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=new_data
                )
                return self.async_create_entry(title="", data={})

        current = self.config_entry.data
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CATEGORY,
                    default=current.get(CONF_CATEGORY, "shirt"),
                ): _category_selector(),
                vol.Optional(
                    CONF_NFC_TAG_ID,
                    default=current.get(CONF_NFC_TAG_ID) or "",
                ): str,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )

    def _tag_in_use(self, tag: str) -> bool:
        """Return True if a *different* entry already claims this NFC tag."""
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.entry_id == self.config_entry.entry_id:
                continue
            if entry.data.get(CONF_NFC_TAG_ID) == tag:
                return True
        return False
