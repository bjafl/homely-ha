"""DataUpdateCoordinator for our integration."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import (
    async_create_clientsession,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, FALLBACK_SCAN_INTERVAL
from .exceptions import HomelyError, HomelyWebSocketError
from .homely_api import (
    HomelyApi,
    HomelyHomeState,
    HomelyWebSocketClient,
    Location,
    WsEvent,
)
from .models import Device

_LOGGER = logging.getLogger(__name__)


class HomelyDataUpdateCoordinator(DataUpdateCoordinator[dict[str, HomelyHomeState]]):
    """Class to manage fetching data from the Homely API."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: HomelyApi | None = None,
        selected_location_ids: list[str] | None = None,
    ) -> None:
        """Initialize coordinator."""
        self.user: str = entry.data[CONF_USERNAME]
        self.pwd: str = entry.data[CONF_PASSWORD]
        self.selected_location_ids: list[str] = (
            selected_location_ids or []  # or entry.data[CONF_LOCATION] or []
        )
        self._config_entry = entry  # Store reference to config entry

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({entry.unique_id})",
        )

        # API and WebSocket clients
        if api:
            self.api = api
        else:
            session = async_create_clientsession(hass)
            self.api = HomelyApi(session)
        self._ws_clients: dict[str, HomelyWebSocketClient] = {}
        self._ws_active: dict[str, bool] = {}
        self._last_error_refresh: float = 0

    @property
    def available_locations(self) -> list[Location] | None:
        """Return list of available locations."""
        return self.api.locations

    @property
    def update_interval(self) -> timedelta:
        """Dynamic update interval based on WebSocket status."""
        active_websockets = sum(1 for active in self._ws_active.values() if active)
        total_locations = len(self.selected_location_ids)

        if active_websockets == total_locations:
            # All locations have active WebSockets, poll very infrequently
            return timedelta(minutes=30)
        elif active_websockets > 0:
            # Some WebSockets active, reduce polling frequency
            return timedelta(seconds=FALLBACK_SCAN_INTERVAL * 2)
        else:
            # No WebSockets, use normal interval
            return timedelta(seconds=FALLBACK_SCAN_INTERVAL)

    @update_interval.setter
    def update_interval(self, interval: timedelta) -> None:
        """To avoid error when fw sets update_interval."""
        self._update_interval = interval

    @callback
    def get_device_state(
        self, device_id: str, location_id: str | None = None
    ) -> Device | None:
        """Get the state of a device by its ID."""
        if not self.data:
            return None
        if location_id and location_id not in self.data:
            return None
        locations_to_check = [location_id] if location_id else self.data.keys()
        for loc_id in locations_to_check:
            home_state = self.data.get(loc_id)
            if home_state:
                for device in home_state.devices:
                    if str(device.id) == device_id:
                        return device
        return None

    @callback
    def get_home_state(self, location_id: str) -> HomelyHomeState | None:
        """Get the home state for a location."""
        if not self.data:
            return None
        if location_id and location_id not in self.data:
            return None
        return self.data.get(location_id)

    # @callback
    # def get_feature_state(self, device_id: str, feature: str, location_id: str | None = None) -> any | None:

    async def ensure_api_initialized(self):
        """Check if API is initialized, if not, do so."""
        if not self.api.is_authenticated:
            await self.api.login(self.user, self.pwd)
        if not self.api.locations:
            await self.api.get_locations()

            # Update config entry with latest available locations
            # if self.api.locations:
            #     location_id_names = await self.api.get_location_id_names()
            #     self.available_locations = location_id_names

    async def _async_update_data(self) -> dict[str, HomelyHomeState]:
        """Update home state via HTTP REST API.

        This fetches the full state for all selected locations, and needs to be
        called before attempting to apply websocket updates.

        It may also need to be called
        when new devices are added or removed, and can be used as a fallback if websockets
        are not working. For now, we call it occasionally to ensure state is valid.
        """
        new_data: dict[str, HomelyHomeState] = {}
        try:
            await self.ensure_api_initialized()

            # Validate that selected locations still exist
            if self.api.locations:
                all_location_ids = await self.api.get_location_id_names()
                valid_selected_ids = [
                    loc_id
                    for loc_id in self.selected_location_ids
                    if loc_id in all_location_ids
                ]

                if len(valid_selected_ids) != len(self.selected_location_ids):
                    _LOGGER.warning(
                        "Some selected locations no longer exist. "
                        "Valid: %s, Selected: %s",
                        valid_selected_ids,
                        self.selected_location_ids,
                    )
                    self.selected_location_ids = valid_selected_ids

            for loc_id in self.selected_location_ids:
                _LOGGER.debug("Fetching state for location %s", loc_id)
                response = await self.api.get_home(loc_id)
                new_data[loc_id] = HomelyHomeState.from_response(response)
        except HomelyError as err:
            _LOGGER.error("API error: %s", err)
            raise UpdateFailed(err) from err
        except Exception as err:
            _LOGGER.error("Unexpected error: %s", err, exc_info=True)
            raise UpdateFailed(f"Error communicating with API: {err}") from err

        return new_data

    async def async_reload_selected_locations(
        self, new_location_ids: list[str] | None = None
    ) -> None:
        """Reload the selected locations."""
        _LOGGER.info(
            "Reloading locations from %s to %s",
            self.selected_location_ids,
            new_location_ids,
        )
        if new_location_ids:
            self.selected_location_ids = new_location_ids
        await self.async_shutdown()
        await self.async_refresh()

        # Start websockets for new locations
        for loc_id in self.selected_location_ids:
            try:
                await self.start_websocket(loc_id)
            except HomelyWebSocketError as err:
                _LOGGER.warning("Failed to start websocket for %s: %s", loc_id, err)

    async def start_websocket(
        self, location_id: str, reconnect_if_exists: bool = True
    ) -> None:
        """Start websocket connection."""
        await self.ensure_api_initialized()
        old_ws = self._ws_clients.get(location_id)
        if old_ws and old_ws.connected and not reconnect_if_exists:
            _LOGGER.debug("WebSocket for location %s already connected", location_id)
            return

        # Create new WebSocket client
        ws = HomelyWebSocketClient(
            api=self.api,
            location_id=location_id,
            name=f"Homely WS {location_id}",
            max_reconnection_attempts=5,
        )

        try:
            # Register event handlers
            ws.register_event_callback(
                callback=lambda ws_event: self._handle_ws_update(location_id, ws_event),
                event_type="event",
            )
            ws.register_event_callback(
                callback=lambda _: self._handle_ws_disconnect(location_id),
                event_type="disconnect",
            )

            await ws.connect()

            # Store the connected client
            self._ws_clients[location_id] = ws
            self._ws_active[location_id] = True

            _LOGGER.info("WebSocket connected for location %s", location_id)

        except HomelyWebSocketError as err:
            self._ws_active[location_id] = False
            _LOGGER.error("WebSocket connection failed: %s", err)
            raise

    @callback
    def _handle_ws_disconnect(self, location_id: str) -> None:
        """Handle websocket disconnection."""
        _LOGGER.warning("WebSocket disconnected for location %s", location_id)

        self._ws_clients.pop(location_id, None)
        self._ws_active[location_id] = False

        # Schedule reconnection
        self.hass.async_create_task(self._schedule_reconnect(location_id))

    @callback
    def _handle_ws_update(self, location_id: str, ws_event: WsEvent | None) -> None:
        """Handle updates from the websocket."""
        _LOGGER.debug("WebSocket update for location %s", location_id)

        if not ws_event:
            _LOGGER.warning("WebSocket update for %s but no event data", location_id)
            return

        if not self.data or location_id not in self.data:
            _LOGGER.warning(
                "WebSocket update for %s but no existing data, triggering refresh",
                location_id,
            )
            self.async_request_refresh()  # pyright: ignore[reportUnusedCoroutine]
            return
        try:
            prev_state = self.data[location_id]
            new_state = HomelyHomeState.from_ws_event(prev_state, ws_event)
            updated_data = self.data.copy()
            updated_data[location_id] = new_state
            self._ws_active[location_id] = True
            self.async_set_updated_data(updated_data)
        except HomelyError as err:
            _LOGGER.error("Failed to process WebSocket update: %s", err)

            # Rate limit refresh requests - only refresh if last refresh was more than 60 seconds ago
            now = asyncio.get_event_loop().time()
            if (
                not hasattr(self, "_last_error_refresh")
                or (now - self._last_error_refresh) > 60
            ):
                self._last_error_refresh = now
                _LOGGER.info("Triggering data refresh due to WebSocket error")
                self.async_request_refresh()  # pyright: ignore[reportUnusedCoroutine]
            else:
                _LOGGER.debug("Skipping refresh request - too recent (rate limited)")

    async def _schedule_reconnect(self, location_id: str, attempt: int = 1) -> None:
        """Schedule WebSocket reconnection with exponential backoff."""
        # Exponential backoff: 30s, 60s, 120s, 240s, max 300s (5 minutes)
        delay = min(30 * (2 ** (attempt - 1)), 300)
        _LOGGER.info(
            "Scheduling WebSocket reconnection for %s in %d seconds (attempt %d)",
            location_id,
            delay,
            attempt,
        )
        await asyncio.sleep(delay)

        try:
            await self.start_websocket(location_id, reconnect_if_exists=False)
            _LOGGER.info("WebSocket reconnection successful for %s", location_id)
        except HomelyWebSocketError as err:
            _LOGGER.error("WebSocket reconnection failed for %s: %s", location_id, err)
            # Schedule next retry with increased attempt count (max 6 attempts)
            if attempt < 6:
                self.hass.async_create_task(
                    self._schedule_reconnect(location_id, attempt + 1)
                )
            else:
                _LOGGER.error(
                    "Max WebSocket reconnection attempts reached for %s", location_id
                )

    async def async_shutdown(self) -> None:
        """Clean up resources when coordinator shuts down."""
        for location_id, ws_client in self._ws_clients.items():
            try:
                await ws_client.disconnect()
            except Exception as err:
                _LOGGER.warning(
                    "Error disconnecting WebSocket for %s: %s", location_id, err
                )
        self._ws_clients.clear()
        self._ws_active.clear()
