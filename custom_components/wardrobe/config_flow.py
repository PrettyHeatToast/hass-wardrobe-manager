"""Config flow for the Wardrobe integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    DateSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)
from homeassistant.util import slugify

try:  # HA >= 2024.4
    from homeassistant.config_entries import ConfigFlowResult
except ImportError:  # HA < 2024.4
    from homeassistant.data_entry_flow import FlowResult as ConfigFlowResult

from .const import (
    CATEGORIES,
    CONF_BRAND,
    CONF_CATEGORY,
    CONF_COLOR,
    CONF_EXTRA_STATES,
    CONF_ITEM_NAME,
    CONF_KIND,
    CONF_LAUNDRY_TYPE,
    CONF_LOAD_SIZE,
    CONF_LOCATION,
    CONF_MATERIAL,
    CONF_NFC_TAG_ID,
    CONF_NOTES,
    CONF_PURCHASE_DATE,
    CONF_PURCHASE_PRICE,
    CONF_SCAN_ACTION,
    CONF_SEASONS,
    CONF_SIZE,
    CONF_WEAR_THRESHOLD,
    DEFAULT_CATEGORY,
    DEFAULT_LAUNDRY_TYPE,
    DEFAULT_LOAD_SIZE,
    DEFAULT_SCAN_ACTION,
    DEFAULT_WEAR_THRESHOLD,
    DOMAIN,
    EXTRA_STATES,
    KIND_SUMMARY,
    LAUNDRY_TYPES,
    SCAN_ACTIONS,
    SEASONS,
    SUMMARY_DEVICE_NAME,
    SUMMARY_HUB_UNIQUE_ID,
)

# Optional free-text details collected in the "details" step. Empty strings
# are normalized to absent keys.
_TEXT_DETAILS = (CONF_BRAND, CONF_SIZE, CONF_COLOR, CONF_MATERIAL, CONF_LOCATION)


def _select(options: list[str], key: str, *, multiple: bool = False) -> SelectSelector:
    """Build a translated dropdown selector."""
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            translation_key=key,
            multiple=multiple,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _basics_schema() -> dict[vol.Marker, Any]:
    return {
        vol.Required(CONF_ITEM_NAME): TextSelector(),
        vol.Required(CONF_CATEGORY, default=DEFAULT_CATEGORY): _select(
            CATEGORIES, "category"
        ),
        vol.Required(CONF_LAUNDRY_TYPE, default=DEFAULT_LAUNDRY_TYPE): _select(
            LAUNDRY_TYPES, "laundry_type"
        ),
    }


def _tracking_schema(*, include_threshold: bool) -> dict[vol.Marker, Any]:
    schema: dict[vol.Marker, Any] = {
        vol.Optional(CONF_NFC_TAG_ID, default=""): TextSelector(),
        vol.Required(CONF_SCAN_ACTION, default=DEFAULT_SCAN_ACTION): _select(
            SCAN_ACTIONS, "scan_action"
        ),
        vol.Optional(CONF_EXTRA_STATES, default=[]): _select(
            EXTRA_STATES, "extra_states", multiple=True
        ),
    }
    if include_threshold:
        schema[
            vol.Optional(CONF_WEAR_THRESHOLD, default=DEFAULT_WEAR_THRESHOLD)
        ] = NumberSelector(
            NumberSelectorConfig(min=0, max=999, step=1, mode=NumberSelectorMode.BOX)
        )
    return schema


def _details_schema() -> dict[vol.Marker, Any]:
    return {
        vol.Optional(CONF_BRAND, default=""): TextSelector(),
        vol.Optional(CONF_SIZE, default=""): TextSelector(),
        vol.Optional(CONF_COLOR, default=""): TextSelector(),
        vol.Optional(CONF_MATERIAL, default=""): TextSelector(),
        vol.Optional(CONF_SEASONS, default=[]): _select(
            SEASONS, "seasons", multiple=True
        ),
        vol.Optional(CONF_LOCATION, default=""): TextSelector(),
        vol.Optional(CONF_PURCHASE_DATE): DateSelector(),
        vol.Optional(CONF_PURCHASE_PRICE): NumberSelector(
            NumberSelectorConfig(min=0, step=0.01, mode=NumberSelectorMode.BOX)
        ),
        vol.Optional(CONF_NOTES, default=""): TextSelector(
            TextSelectorConfig(multiline=True)
        ),
    }


def _clean_details(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize the details step: strip text fields, drop empties."""
    out: dict[str, Any] = {}
    for key in _TEXT_DETAILS + (CONF_NOTES,):
        value = (user_input.get(key) or "").strip()
        if value:
            out[key] = value
    seasons = user_input.get(CONF_SEASONS) or []
    if seasons:
        out[CONF_SEASONS] = seasons
    if user_input.get(CONF_PURCHASE_DATE):
        out[CONF_PURCHASE_DATE] = user_input[CONF_PURCHASE_DATE]
    if user_input.get(CONF_PURCHASE_PRICE) is not None:
        out[CONF_PURCHASE_PRICE] = float(user_input[CONF_PURCHASE_PRICE])
    return out


def _tag_in_use(hass_entries: list[ConfigEntry], tag: str, own_id: str | None) -> bool:
    """Return True if a different entry already claims this NFC tag."""
    for entry in hass_entries:
        if own_id is not None and entry.entry_id == own_id:
            continue
        if entry.data.get(CONF_NFC_TAG_ID) == tag:
            return True
    return False


class WardrobeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Multi-step flow that adds a single wardrobe item."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow state carried across steps."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1 — basics: name, category and laundry type."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input[CONF_ITEM_NAME].strip()
            if not name:
                errors[CONF_ITEM_NAME] = "name_required"
            else:
                await self.async_set_unique_id(slugify(name))
                self._abort_if_unique_id_configured()
                self._data = {
                    CONF_ITEM_NAME: name,
                    CONF_CATEGORY: user_input[CONF_CATEGORY],
                    CONF_LAUNDRY_TYPE: user_input[CONF_LAUNDRY_TYPE],
                }
                return await self.async_step_tracking()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(_basics_schema()), user_input
            ),
            errors=errors,
        )

    async def async_step_tracking(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2 — tracking: NFC tag, scan action, extra states, threshold."""
        errors: dict[str, str] = {}

        if user_input is not None:
            tag = (user_input.get(CONF_NFC_TAG_ID) or "").strip() or None
            if tag and _tag_in_use(self._async_current_entries(), tag, None):
                errors[CONF_NFC_TAG_ID] = "tag_exists"

            if not errors:
                self._data.update(
                    {
                        CONF_NFC_TAG_ID: tag,
                        CONF_SCAN_ACTION: user_input[CONF_SCAN_ACTION],
                        CONF_EXTRA_STATES: user_input.get(CONF_EXTRA_STATES) or [],
                        CONF_WEAR_THRESHOLD: int(
                            user_input.get(CONF_WEAR_THRESHOLD, DEFAULT_WEAR_THRESHOLD)
                        ),
                    }
                )
                return await self.async_step_details()

        return self.async_show_form(
            step_id="tracking",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(_tracking_schema(include_threshold=True)), user_input
            ),
            errors=errors,
        )

    async def async_step_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3 — optional details: brand, size, seasons, purchase info…"""
        if user_input is not None:
            self._data.update(_clean_details(user_input))
            return self.async_create_entry(
                title=self._data[CONF_ITEM_NAME], data=self._data
            )

        return self.async_show_form(
            step_id="details", data_schema=vol.Schema(_details_schema())
        )

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
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler for an existing entry."""
        if config_entry.data.get(CONF_KIND) == KIND_SUMMARY:
            return WardrobeHubOptionsFlow(config_entry)
        return WardrobeOptionsFlow(config_entry)


class WardrobeOptionsFlow(OptionsFlow):
    """Menu-based editor for an existing clothing item."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Store the entry being edited (compatible with old and new cores)."""
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the section menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["basics", "tracking", "details"],
        )

    async def async_step_basics(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit category and laundry type (the name identifies the entry)."""
        if user_input is not None:
            return self._save(
                {
                    CONF_CATEGORY: user_input[CONF_CATEGORY],
                    CONF_LAUNDRY_TYPE: user_input[CONF_LAUNDRY_TYPE],
                }
            )

        schema = {
            vol.Required(
                CONF_CATEGORY,
                default=self._entry.data.get(CONF_CATEGORY, DEFAULT_CATEGORY),
            ): _select(CATEGORIES, "category"),
            vol.Required(
                CONF_LAUNDRY_TYPE,
                default=self._entry.data.get(CONF_LAUNDRY_TYPE, DEFAULT_LAUNDRY_TYPE),
            ): _select(LAUNDRY_TYPES, "laundry_type"),
        }
        return self.async_show_form(step_id="basics", data_schema=vol.Schema(schema))

    async def async_step_tracking(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit NFC tag, scan action and extra states.

        The wear threshold is not offered here — after creation it is owned
        by the item's number entity.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            tag = (user_input.get(CONF_NFC_TAG_ID) or "").strip() or None
            if tag and _tag_in_use(
                self.hass.config_entries.async_entries(DOMAIN),
                tag,
                self._entry.entry_id,
            ):
                errors[CONF_NFC_TAG_ID] = "tag_exists"

            if not errors:
                return self._save(
                    {
                        CONF_NFC_TAG_ID: tag,
                        CONF_SCAN_ACTION: user_input[CONF_SCAN_ACTION],
                        CONF_EXTRA_STATES: user_input.get(CONF_EXTRA_STATES) or [],
                    }
                )

        current = {
            CONF_NFC_TAG_ID: self._entry.data.get(CONF_NFC_TAG_ID) or "",
            CONF_SCAN_ACTION: self._entry.data.get(
                CONF_SCAN_ACTION, DEFAULT_SCAN_ACTION
            ),
            CONF_EXTRA_STATES: self._entry.data.get(CONF_EXTRA_STATES) or [],
        }
        return self.async_show_form(
            step_id="tracking",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(_tracking_schema(include_threshold=False)),
                user_input or current,
            ),
            errors=errors,
        )

    async def async_step_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the optional metadata fields."""
        if user_input is not None:
            # Rebuild details from scratch so cleared fields are removed.
            new_data = {
                k: v
                for k, v in self._entry.data.items()
                if k
                not in (
                    *_TEXT_DETAILS,
                    CONF_NOTES,
                    CONF_SEASONS,
                    CONF_PURCHASE_DATE,
                    CONF_PURCHASE_PRICE,
                )
            }
            new_data.update(_clean_details(user_input))
            self.hass.config_entries.async_update_entry(self._entry, data=new_data)
            return self.async_create_entry(title="", data={})

        current = {
            key: self._entry.data[key]
            for key in (
                *_TEXT_DETAILS,
                CONF_NOTES,
                CONF_SEASONS,
                CONF_PURCHASE_DATE,
                CONF_PURCHASE_PRICE,
            )
            if key in self._entry.data
        }
        return self.async_show_form(
            step_id="details",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(_details_schema()), current
            ),
        )

    def _save(self, updates: dict[str, Any]) -> ConfigFlowResult:
        """Merge updates into entry.data and finish the flow."""
        self.hass.config_entries.async_update_entry(
            self._entry, data={**self._entry.data, **updates}
        )
        return self.async_create_entry(title="", data={})


class WardrobeHubOptionsFlow(OptionsFlow):
    """Options for the summary hub: laundry load size."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Store the hub entry being edited."""
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the number of dirty items that makes a load 'ready'."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={CONF_LOAD_SIZE: int(user_input[CONF_LOAD_SIZE])},
            )

        schema = {
            vol.Required(
                CONF_LOAD_SIZE,
                default=self._entry.options.get(CONF_LOAD_SIZE, DEFAULT_LOAD_SIZE),
            ): NumberSelector(
                NumberSelectorConfig(min=1, max=100, step=1, mode=NumberSelectorMode.BOX)
            )
        }
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
