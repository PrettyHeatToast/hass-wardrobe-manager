"""Config flow for Wardrobe Manager integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithConfigEntry,
)

from .const import (
    CONF_CATEGORY,
    CONF_COLOR,
    CONF_GARMENT_NAME,
    CONF_NEEDS_WASHING_THRESHOLD,
    CONF_SCANNER_ID,
    CONF_SCANNER_NAME,
    CONF_SCANNER_ROLE,
    CONF_TAG_ID,
    DEFAULT_NEEDS_WASHING_THRESHOLD,
    DOMAIN,
    GARMENT_CATEGORIES,
    ScannerRole,
)


class WardrobeManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Wardrobe Manager."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title="Wardrobe Manager",
                data={},
            )

        return self.async_show_form(
            step_id="user",
            description_placeholders={},
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> WardrobeManagerOptionsFlow:
        """Return the options flow handler."""
        return WardrobeManagerOptionsFlow(config_entry)


class WardrobeManagerOptionsFlow(OptionsFlowWithConfigEntry):
    """Handle options flow for managing scanners and garments."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_scanner",
                "remove_scanner",
                "add_garment",
                "remove_garment",
            ],
        )

    # ── Add scanner ──────────────────────────────────────────────────────

    async def async_step_add_scanner(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle adding a new scanner."""
        if user_input is not None:
            coordinator = self.hass.data[DOMAIN]["coordinator"]
            await coordinator.async_register_scanner(
                scanner_id=user_input[CONF_SCANNER_ID],
                role=user_input[CONF_SCANNER_ROLE],
                name=user_input[CONF_SCANNER_NAME],
            )
            return self.async_create_entry(data=self.options)

        return self.async_show_form(
            step_id="add_scanner",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCANNER_ID): str,
                    vol.Required(CONF_SCANNER_ROLE): vol.In(
                        {role.value: role.value for role in ScannerRole}
                    ),
                    vol.Required(CONF_SCANNER_NAME): str,
                }
            ),
        )

    # ── Remove scanner ───────────────────────────────────────────────────

    async def async_step_remove_scanner(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle removing a scanner."""
        coordinator = self.hass.data[DOMAIN]["coordinator"]

        if not coordinator.scanners:
            return self.async_abort(reason="no_scanners")

        if user_input is not None:
            scanner_id = user_input[CONF_SCANNER_ID]
            coordinator.scanners.pop(scanner_id, None)
            await coordinator._async_save()
            return self.async_create_entry(data=self.options)

        scanner_options = {
            sid: f"{info['name']} ({info['role']})"
            for sid, info in coordinator.scanners.items()
        }

        return self.async_show_form(
            step_id="remove_scanner",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCANNER_ID): vol.In(scanner_options),
                }
            ),
        )

    # ── Add garment ──────────────────────────────────────────────────────

    async def async_step_add_garment(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle adding a new garment."""
        errors: dict[str, str] = {}

        if user_input is not None:
            coordinator = self.hass.data[DOMAIN]["coordinator"]
            tag_id = user_input[CONF_TAG_ID]

            if tag_id in coordinator.garments:
                errors["base"] = "tag_already_registered"
            else:
                garment = await coordinator.async_register_garment(
                    tag_id=tag_id,
                    name=user_input[CONF_GARMENT_NAME],
                    category=user_input[CONF_CATEGORY],
                    color=user_input.get(CONF_COLOR, ""),
                    needs_washing_threshold=user_input.get(
                        CONF_NEEDS_WASHING_THRESHOLD,
                        DEFAULT_NEEDS_WASHING_THRESHOLD,
                    ),
                )
                from .device_registry import async_get_or_create_garment_device

                async_get_or_create_garment_device(
                    self.hass, self.config_entry.entry_id, garment
                )
                return self.async_create_entry(data=self.options)

        return self.async_show_form(
            step_id="add_garment",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TAG_ID): str,
                    vol.Required(CONF_GARMENT_NAME): str,
                    vol.Required(CONF_CATEGORY): vol.In(
                        {cat: cat for cat in GARMENT_CATEGORIES}
                    ),
                    vol.Optional(CONF_COLOR, default=""): str,
                    vol.Optional(
                        CONF_NEEDS_WASHING_THRESHOLD,
                        default=DEFAULT_NEEDS_WASHING_THRESHOLD,
                    ): int,
                }
            ),
            errors=errors,
        )

    # ── Remove garment ───────────────────────────────────────────────────

    async def async_step_remove_garment(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle removing a garment."""
        coordinator = self.hass.data[DOMAIN]["coordinator"]

        if not coordinator.garments:
            return self.async_abort(reason="no_garments")

        if user_input is not None:
            tag_id = user_input[CONF_TAG_ID]
            await coordinator.async_remove_garment(tag_id)

            from .device_registry import async_remove_garment_device

            async_remove_garment_device(self.hass, tag_id)
            return self.async_create_entry(data=self.options)

        garment_options = {
            tag_id: f"{g.name} ({g.category})"
            for tag_id, g in coordinator.garments.items()
        }

        return self.async_show_form(
            step_id="remove_garment",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TAG_ID): vol.In(garment_options),
                }
            ),
        )
