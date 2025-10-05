"""Homely integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LOCATION, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceRegistry

from .const import DOMAIN

# from .exceptions import HomelyError, HomelyConfigAuthError
from .coordinator import HomelyDataUpdateCoordinator
from .exceptions import (
    HomelyAuthError,
    HomelyAuthExpiredError,
    HomelyAuthInvalidError,
    HomelyNetworkError,
)
from .homely_api import HomelyApi

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Homely from a config entry."""
    _LOGGER.debug("Setting up Homely integration for entry %s", entry.entry_id)

    session = async_get_clientsession(hass)
    api = HomelyApi(session, logger=_LOGGER)

    # Authenticate
    try:
        await api.login(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    except (HomelyAuthError, HomelyAuthExpiredError, HomelyAuthInvalidError) as err:
        _LOGGER.error("Authentication failed: %s", err)
        raise ConfigEntryAuthFailed from err
    except HomelyNetworkError as err:
        _LOGGER.error("Network error during setup: %s", err)
        raise ConfigEntryNotReady from err

    # Get locations to ensure API is working and update available_locations
    try:
        locations = await api.get_locations()
        if not locations:
            _LOGGER.error("No locations found for this account")
            raise ConfigEntryNotReady("No locations available")

        # Update config entry with latest available locations
        location_id_names = await api.get_location_id_names()
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                "available_locations": location_id_names,
            },
        )

    except HomelyNetworkError as err:
        _LOGGER.error("Failed to fetch locations: %s", err)
        raise ConfigEntryNotReady from err

    selected_locations = entry.data.get(CONF_LOCATION, [])
    _LOGGER.debug("Selected locations: %s", selected_locations)
    # Create coordinator
    coordinator = HomelyDataUpdateCoordinator(hass, entry, api, selected_locations)

    await coordinator.async_config_entry_first_refresh()

    # Validate selected locations exist
    available_locations = await api.get_location_id_names()
    _LOGGER.debug("Available locations: %s", available_locations)
    valid_selected = [
        loc_id for loc_id in selected_locations if str(loc_id) in available_locations
    ]

    if not valid_selected:
        _LOGGER.error("No valid selected locations found")
        raise ConfigEntryNotReady("No valid locations selected")

    if len(valid_selected) != len(selected_locations):
        _LOGGER.warning("Some selected locations no longer exist, updating config")
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_LOCATION: valid_selected,
            },
        )
    # Store coordinator in hass data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start WebSocket connections for all locations
    await coordinator.async_reload_selected_locations(valid_selected)

    _LOGGER.info("Homely integration setup complete")
    return True


async def async_remove_entry_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_entry: DeviceRegistry,
) -> bool:
    """Remove a device."""
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Homely integration for entry %s", entry.entry_id)

    # Stop WebSocket connections
    coordinator: HomelyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_shutdown()

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Remove from hass data
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)

    _LOGGER.info("Homely integration unloaded")
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
