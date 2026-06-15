"""Homely integration."""

from __future__ import annotations

import asyncio
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
    HomelyRateLimitError,
)
from .homely_api import HomelyApi

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]

# Module-level rate limit tracker — persists across setup retries within the same HA run.
# This prevents rapid setup retries from repeatedly hitting the API and resetting the
# rate-limit sliding window, which would otherwise create a deadlock.
_rate_limited_until: float = 0


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Homely from a config entry."""
    global _rate_limited_until
    _LOGGER.debug("Setting up Homely integration for entry %s", entry.entry_id)

    now = asyncio.get_event_loop().time()
    if now < _rate_limited_until:
        remaining = _rate_limited_until - now
        _LOGGER.warning(
            "Skipping setup attempt — Homely API rate limited for %.0fs more", remaining
        )
        raise ConfigEntryNotReady(f"Homely API rate limited, retry in {remaining:.0f}s")

    session = async_get_clientsession(hass)
    api = HomelyApi(session, logger=_LOGGER)

    # Authenticate
    try:
        await api.login(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    except (HomelyAuthError, HomelyAuthExpiredError, HomelyAuthInvalidError) as err:
        _LOGGER.error("Authentication failed: %s", err)
        raise ConfigEntryAuthFailed from err
    except HomelyRateLimitError as err:
        _rate_limited_until = asyncio.get_event_loop().time() + max(120, err.retry_after * 10)
        _LOGGER.warning("Rate limited during login: %s", err)
        raise ConfigEntryNotReady(f"Homely API rate limited, retry after {err.retry_after}s") from err
    except HomelyNetworkError as err:
        _LOGGER.error("Network error during setup: %s", err)
        raise ConfigEntryNotReady from err

    # Get locations to ensure API is working and update available_locations
    try:
        locations = await api.get_locations()
        if not locations:
            _LOGGER.error("No locations found for this account")
            raise ConfigEntryNotReady("No locations available")

        # Reuse the already-fetched locations to avoid extra API calls
        location_id_names = {str(loc.location_id): loc.name for loc in locations}
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                "available_locations": location_id_names,
            },
        )

    except HomelyRateLimitError as err:
        _rate_limited_until = asyncio.get_event_loop().time() + max(120, err.retry_after * 10)
        _LOGGER.warning("Rate limited during location fetch: %s", err)
        raise ConfigEntryNotReady(f"Homely API rate limited, retry after {err.retry_after}s") from err
    except HomelyNetworkError as err:
        _LOGGER.error("Failed to fetch locations: %s", err)
        raise ConfigEntryNotReady from err

    selected_locations = entry.data.get(CONF_LOCATION, [])
    _LOGGER.debug("Selected locations: %s", selected_locations)
    # Create coordinator
    coordinator = HomelyDataUpdateCoordinator(hass, entry, api, selected_locations)

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        if coordinator.rate_limited_until > asyncio.get_event_loop().time():
            _rate_limited_until = coordinator.rate_limited_until
            _LOGGER.warning(
                "Rate limited during first refresh, blocking setup retries for %.0fs",
                _rate_limited_until - asyncio.get_event_loop().time(),
            )
        raise

    # Reuse cached locations to avoid an extra API call
    valid_selected = [
        loc_id for loc_id in selected_locations if str(loc_id) in location_id_names
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
