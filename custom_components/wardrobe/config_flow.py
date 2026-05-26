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
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util import slugify

from .const import (
    CATEGORY_ICONS,
    CONF_CATEGORY,
    CONF_ITEM_NAME,
    CONF_KIND,
    CONF_LAUNDRY_TYPE,
    CONF_NFC_TAG_ID,
    CONF_WEAR_THRESHOLD,
    DEFAULT_LAUNDRY_TYPE,
    DEFAULT_WEAR_THRESHOLD,
    DOMAIN,
    KIND_SUMMARY,
    LAUNDRY_TYPES,
    SUMMARY_DEVICE_NAME,
    SUMMARY_HUB_UNIQUE_ID,
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


def _laundry_type_selector() -> SelectSelector:
    """Build the dropdown selector for the laundry-type field."""
    return SelectSelector(
        SelectSelectorConfig(
            options=LAUNDRY_TYPES,
            translation_key="laundry_type",
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _wear_threshold_selector() -> NumberSelector:
    """Build the numeric input for the wear-threshold field."""
    return NumberSelector(
        NumberSelectorConfig(
            min=0,
            max=999,
            step=1,
            mode=NumberSelectorMode.BOX,
        )
    )


class WardrobeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the user-initiated flow that adds a single wardrobe item."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the name, category, laundry type and (optional) NFC tag."""
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
                        CONF_LAUNDRY_TYPE: user_input[CONF_LAUNDRY_TYPE],
                        CONF_WEAR_THRESHOLD: int(
                            user_input.get(CONF_WEAR_THRESHOLD, DEFAULT_WEAR_THRESHOLD)
                        ),
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
                vol.Required(
                    CONF_LAUNDRY_TYPE,
                    default=suggested.get(CONF_LAUNDRY_TYPE, DEFAULT_LAUNDRY_TYPE),
                ): _laundry_type_selector(),
                vol.Optional(
                    CONF_WEAR_THRESHOLD,
                    default=suggested.get(CONF_WEAR_THRESHOLD, DEFAULT_WEAR_THRESHOLD),
                ): _wear_threshold_selector(),
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

    async def async_step_integration_discovery(
        self, discovery_info: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Auto-create the singleton Wardrobe Summary hub entry.

        Triggered from ``__init__.py`` when the first item entry is set up
        without an existing hub. ``unique_id`` enforces single-instance.
        """
        await self.async_set_unique_id(SUMMARY_HUB_UNIQUE_ID)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=SUMMARY_DEVICE_NAME,
            data={CONF_KIND: KIND_SUMMARY},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> WardrobeOptionsFlow:
        """Return the options flow handler for an existing entry."""
        return WardrobeOptionsFlow()


class WardrobeOptionsFlow(OptionsFlow):
    """Edit the category, laundry type, threshold and NFC tag of an item."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the edit form and persist changes back to ``entry.data``."""
        if self.config_entry.data.get(CONF_KIND) == KIND_SUMMARY:
            return self.async_abort(reason="no_options")

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
                    CONF_LAUNDRY_TYPE: user_input[CONF_LAUNDRY_TYPE],
                    CONF_WEAR_THRESHOLD: int(
                        user_input.get(CONF_WEAR_THRESHOLD, DEFAULT_WEAR_THRESHOLD)
                    ),
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
                vol.Required(
                    CONF_LAUNDRY_TYPE,
                    default=current.get(CONF_LAUNDRY_TYPE, DEFAULT_LAUNDRY_TYPE),
                ): _laundry_type_selector(),
                vol.Optional(
                    CONF_WEAR_THRESHOLD,
                    default=current.get(CONF_WEAR_THRESHOLD, DEFAULT_WEAR_THRESHOLD),
                ): _wear_threshold_selector(),
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
