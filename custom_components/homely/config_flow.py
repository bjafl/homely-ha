"""Config flow for Homely integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_LOCATION,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_AVAILABLE_LOCATIONS,
    DOMAIN,
    STEP_LOCATIONS,
    STEP_PICK_LOCATIONS,
    STEP_USER,
)
from .exceptions import HomelyAuthInvalidError, HomelyNetworkError
from .homely_api import HomelyApi

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class HomelyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Homely."""

    VERSION = 1

    def __init__(self):
        """Initialize flow."""
        self._api: HomelyApi | None = None
        self._locations: dict[str, str] = {}
        self._username: str | None = None
        self._password: str | None = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]

            session = async_get_clientsession(self.hass)
            api = HomelyApi(session)

            try:
                if not self._username or not self._password:
                    raise HomelyAuthInvalidError("Username and password are required")

                await api.login(self._username, self._password)
                location_id_names = await api.get_location_id_names()

                if not location_id_names:
                    errors["base"] = "no_locations"
                else:
                    self._locations = location_id_names
                    self._api = api
                    return await self.async_step_locations()

            except HomelyAuthInvalidError:
                errors["base"] = "invalid_auth"
            except HomelyNetworkError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during authentication")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id=STEP_USER,
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_locations(self, user_input=None):
        """Handle location selection."""
        if user_input is not None:
            selected_locations = user_input[CONF_LOCATION]

            if not selected_locations:
                return self.async_show_form(
                    step_id=STEP_LOCATIONS,
                    data_schema=self._get_locations_schema(),
                    errors={CONF_LOCATION: "at_least_one_location"},
                )

            # Check for existing entries with same username
            existing_entry = None
            for entry in self._async_current_entries():
                if entry.data.get(CONF_USERNAME) == self._username:
                    existing_entry = entry
                    break

            if existing_entry:
                # Update existing entry instead of creating new one
                self.hass.config_entries.async_update_entry(
                    existing_entry,
                    data={
                        **existing_entry.data,
                        CONF_LOCATION: selected_locations,
                        CONF_AVAILABLE_LOCATIONS: self._locations,
                    },
                )
                return self.async_abort(reason="already_configured")

            return self.async_create_entry(
                title=f"Homely ({self._username})",
                data={
                    CONF_USERNAME: self._username,
                    CONF_PASSWORD: self._password,
                    CONF_LOCATION: selected_locations,
                    CONF_AVAILABLE_LOCATIONS: self._locations,
                },
            )

        if not self._locations:
            return self.async_abort(reason="no_locations")
        if not self._username:
            return self.async_abort(reason="no_username")

        return self.async_show_form(
            step_id=STEP_LOCATIONS,
            data_schema=self._get_locations_schema(),
            description_placeholders={
                "location_count": str(len(self._locations)),
                "username": self._username,
            },
        )

    def _get_locations_schema(self):
        """Get the locations selection schema."""
        return vol.Schema(
            {
                vol.Required(CONF_LOCATION): cv.multi_select(self._locations),
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return HomelyOptionsFlowHandler(config_entry)


class HomelyOptionsFlowHandler(OptionsFlow):
    """Handle options flow for Homely config.

    Allows user to change selected locations.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__()
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options - this is the entry point."""
        return await self.async_step_pick_locations(user_input)

    async def async_step_pick_locations(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle location selection."""
        if user_input is not None:
            new_locations = user_input[CONF_LOCATION]
            current_locations = self._config_entry.data.get(CONF_LOCATION, [])

            # Only reload if locations actually changed
            if set(new_locations) != set(current_locations):
                # Update the config entry data with new selections
                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    data={
                        **self._config_entry.data,
                        CONF_LOCATION: new_locations,
                    },
                )

                # Trigger full integration reload to update entities
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self._config_entry.entry_id)
                )

            return self.async_create_entry(title="", data=user_input)

        # Get available locations from config entry data
        available_locations: dict[str, str] = self._config_entry.data.get(
            CONF_AVAILABLE_LOCATIONS, {}
        )

        # Fallback: Try to get fresh locations if none stored
        if not available_locations:
            available_locations = await self._fetch_fresh_locations()

        current_locations = self._config_entry.data.get(
            CONF_LOCATION, available_locations
        )  # Select all by default

        return self.async_show_form(
            step_id=STEP_PICK_LOCATIONS,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_LOCATION, default=current_locations
                    ): cv.multi_select(available_locations),
                }
            ),
        )

    async def _fetch_fresh_locations(self) -> dict[str, str]:
        """Fetch fresh locations from API if not available in config."""
        try:
            session = async_get_clientsession(self.hass)
            api = HomelyApi(session)

            await api.login(
                self._config_entry.data[CONF_USERNAME],
                self._config_entry.data[CONF_PASSWORD],
            )

            location_id_names = await api.get_location_id_names()

            # Update config entry with fresh location data
            self.hass.config_entries.async_update_entry(
                self._config_entry,
                data={
                    **self._config_entry.data,
                    CONF_AVAILABLE_LOCATIONS: location_id_names,
                },
            )

            return location_id_names

        except Exception as err:
            _LOGGER.error("Failed to fetch fresh locations: %s", err)
            return {}
