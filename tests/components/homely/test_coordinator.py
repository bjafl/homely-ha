"""Test the Homely coordinator."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.homely.const import FALLBACK_SCAN_INTERVAL
from custom_components.homely.coordinator import HomelyDataUpdateCoordinator
from custom_components.homely.exceptions import HomelyError, HomelyWebSocketError
from custom_components.homely.homely_api import HomelyHomeState, WsEvent
from custom_components.homely.models import HomeResponse

from .conftest import TEST_LOCATION_ID


class TestHomelyDataUpdateCoordinator:
    """Test Homely data update coordinator."""

    def test_init(self, hass, mock_config_entry, api_logged_in_with_locations):
        """Test coordinator initialization."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in_with_locations,
            selected_location_ids=[TEST_LOCATION_ID],
        )

        assert coordinator.user == mock_config_entry.data["username"]
        assert coordinator.pwd == mock_config_entry.data["password"]
        assert coordinator.selected_location_ids == [TEST_LOCATION_ID]
        assert coordinator.api == api_logged_in_with_locations

    def test_init_without_api(
        self, hass, mock_config_entry, patch_async_create_client_session: AsyncMock
    ):
        """Test coordinator initialization without API."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            selected_location_ids=[TEST_LOCATION_ID],
        )

        assert coordinator.api is not None
        assert coordinator.user == mock_config_entry.data["username"]
        assert coordinator.selected_location_ids == [TEST_LOCATION_ID]
        assert (
            coordinator.api._client_session
            == patch_async_create_client_session.return_value
        )

    def test_available_locations(
        self, hass, mock_config_entry, api_logged_in_with_locations
    ):
        """Test available locations property."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in_with_locations,
        )

        locations = coordinator.available_locations
        assert locations is not None
        assert len(locations) > 0

    def test_update_interval_no_websockets(
        self, hass, mock_config_entry, api_logged_in
    ):
        """Test update interval with no active websockets."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in,
            selected_location_ids=[TEST_LOCATION_ID],
        )

        interval = coordinator.update_interval
        assert interval == timedelta(seconds=FALLBACK_SCAN_INTERVAL)

    def test_update_interval_all_websockets_active(
        self, hass, mock_config_entry, api_logged_in
    ):
        """Test update interval with all websockets active."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in,
            selected_location_ids=[TEST_LOCATION_ID],
        )
        coordinator._ws_active[TEST_LOCATION_ID] = True

        interval = coordinator.update_interval
        assert interval == timedelta(minutes=30)

    def test_update_interval_partial_websockets(
        self, hass, mock_config_entry, api_logged_in
    ):
        """Test update interval with some websockets active."""
        location_2 = "location_2"
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in,
            selected_location_ids=[TEST_LOCATION_ID, location_2],
        )
        coordinator._ws_active[TEST_LOCATION_ID] = True
        coordinator._ws_active[location_2] = False

        interval = coordinator.update_interval
        assert interval == timedelta(seconds=60)  # FALLBACK_SCAN_INTERVAL * 2

    def test_get_device_state_no_data(self, hass, mock_config_entry, api_logged_in):
        """Test get_device_state with no data."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in,
        )

        device = coordinator.get_device_state("device_123")
        assert device is None

    def test_get_device_state_device_not_found(
        self, hass, mock_config_entry, api_logged_in
    ):
        """Test get_device_state with device not found."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in,
        )
        mock_home_state = MagicMock(spec=HomelyHomeState)
        mock_home_state.devices = []
        coordinator.data = {TEST_LOCATION_ID: mock_home_state}

        device = coordinator.get_device_state("device_123", TEST_LOCATION_ID)
        assert device is None

    def test_get_device_state_found(self, hass, mock_config_entry, api_logged_in):
        """Test get_device_state with device found."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in,
        )
        mock_device = MagicMock()
        mock_device.id = "device_123"
        mock_home_state = MagicMock(spec=HomelyHomeState)
        mock_home_state.devices = [mock_device]
        coordinator.data = {TEST_LOCATION_ID: mock_home_state}

        device = coordinator.get_device_state("device_123", TEST_LOCATION_ID)
        assert device is not None
        assert device.id == "device_123"

    def test_get_home_state_no_data(self, hass, mock_config_entry, api_logged_in):
        """Test get_home_state with no data."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in,
        )

        home_state = coordinator.get_home_state(TEST_LOCATION_ID)
        assert home_state is None

    def test_get_home_state_found(self, hass, mock_config_entry, api_logged_in):
        """Test get_home_state with location found."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in,
        )
        mock_home_state = MagicMock(spec=HomelyHomeState)
        coordinator.data = {TEST_LOCATION_ID: mock_home_state}

        home_state = coordinator.get_home_state(TEST_LOCATION_ID)
        assert home_state is not None

    async def test_ensure_api_initialized_already_initialized(
        self, hass, mock_config_entry, api_logged_in_with_locations
    ):
        """Test ensure_api_initialized when already initialized."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in_with_locations,
        )

        await coordinator.ensure_api_initialized()
        # Should not raise any errors

    async def test_ensure_api_initialized_not_authenticated(
        self, hass, mock_config_entry, api_with_mock_session
    ):
        """Test ensure_api_initialized when not authenticated."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_with_mock_session,
        )
        coordinator.api.login = AsyncMock()
        coordinator.api.get_locations = AsyncMock()

        await coordinator.ensure_api_initialized()

        coordinator.api.login.assert_called_once()
        coordinator.api.get_locations.assert_called_once()

    async def test_async_update_data_success(
        self,
        hass,
        mock_config_entry,
        api_logged_in_with_locations,
        mock_simple_home_response_object: HomeResponse,
    ):
        """Test successful data update."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in_with_locations,
            selected_location_ids=[TEST_LOCATION_ID],
        )

        mock_response = mock_simple_home_response_object
        mock_response.name = "NEW_NAME_TEST"
        coordinator.api.get_home = AsyncMock(return_value=mock_response)
        coordinator.api.get_locations = AsyncMock(
            return_value=coordinator.api.locations
        )  # Skip fetching new locations from api

        data = await coordinator._async_update_data()

        assert TEST_LOCATION_ID in data
        assert data[TEST_LOCATION_ID].name == "NEW_NAME_TEST"

    async def test_async_update_data_api_error(
        self, hass, mock_config_entry, api_logged_in_with_locations
    ):
        """Test data update with API error."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in_with_locations,
            selected_location_ids=[TEST_LOCATION_ID],
        )

        coordinator.api.get_home = AsyncMock(side_effect=HomelyError("API Error"))

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    async def test_async_update_data_unexpected_error(
        self, hass, mock_config_entry, api_logged_in_with_locations
    ):
        """Test data update with unexpected error."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in_with_locations,
            selected_location_ids=[TEST_LOCATION_ID],
        )

        coordinator.api.get_home = AsyncMock(side_effect=Exception("Unexpected"))

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    async def test_async_reload_selected_locations(
        self, hass, mock_config_entry, api_logged_in
    ):
        """Test reloading selected locations."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in,
            selected_location_ids=[TEST_LOCATION_ID],
        )
        coordinator.async_shutdown = AsyncMock()
        coordinator.async_refresh = AsyncMock()
        coordinator.start_websocket = AsyncMock()

        new_location = "new_location"
        await coordinator.async_reload_selected_locations([new_location])

        assert coordinator.selected_location_ids == [new_location]
        coordinator.async_shutdown.assert_called_once()
        coordinator.async_refresh.assert_called_once()
        coordinator.start_websocket.assert_called_once_with(new_location)

    async def test_start_websocket_success(
        self, hass, mock_config_entry, api_logged_in_with_locations
    ):
        """Test starting websocket successfully."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in_with_locations,
            selected_location_ids=[TEST_LOCATION_ID],
        )

        mock_ws = MagicMock()
        mock_ws.connected = False
        mock_ws.connect = AsyncMock()
        mock_ws.register_event_callback = MagicMock()

        with patch(
            "custom_components.homely.coordinator.HomelyWebSocketClient",
            return_value=mock_ws,
        ):
            await coordinator.start_websocket(TEST_LOCATION_ID)

            assert TEST_LOCATION_ID in coordinator._ws_clients
            assert coordinator._ws_active[TEST_LOCATION_ID] is True
            mock_ws.connect.assert_called_once()

    async def test_start_websocket_already_connected(
        self, hass, mock_config_entry, api_logged_in_with_locations
    ):
        """Test starting websocket when already connected."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in_with_locations,
            selected_location_ids=[TEST_LOCATION_ID],
        )

        mock_ws = MagicMock()
        mock_ws.connected = True
        mock_ws.connect = AsyncMock()
        coordinator._ws_clients[TEST_LOCATION_ID] = mock_ws

        await coordinator.start_websocket(TEST_LOCATION_ID, reconnect_if_exists=False)

        # Should not connect again
        mock_ws.connect.assert_not_called()

    async def test_start_websocket_connection_error(
        self, hass, mock_config_entry, api_logged_in_with_locations
    ):
        """Test starting websocket with connection error."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in_with_locations,
            selected_location_ids=[TEST_LOCATION_ID],
        )

        mock_ws = MagicMock()
        mock_ws.connected = False
        mock_ws.connect = AsyncMock(
            side_effect=HomelyWebSocketError("Connection failed")
        )
        mock_ws.register_event_callback = MagicMock()

        with patch(
            "custom_components.homely.coordinator.HomelyWebSocketClient",
            return_value=mock_ws,
        ):
            with pytest.raises(HomelyWebSocketError):
                await coordinator.start_websocket(TEST_LOCATION_ID)

            assert coordinator._ws_active.get(TEST_LOCATION_ID) is False

    def test_handle_ws_disconnect(self, hass, mock_config_entry, api_logged_in):
        """Test handling websocket disconnect."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in,
            selected_location_ids=[TEST_LOCATION_ID],
        )

        mock_ws = MagicMock()
        coordinator._ws_clients[TEST_LOCATION_ID] = mock_ws
        coordinator._ws_active[TEST_LOCATION_ID] = True

        with patch.object(hass, "async_create_task") as mock_create_task:
            coordinator._handle_ws_disconnect(TEST_LOCATION_ID)

            assert TEST_LOCATION_ID not in coordinator._ws_clients
            assert coordinator._ws_active[TEST_LOCATION_ID] is False
            mock_create_task.assert_called_once()

    def test_handle_ws_update_no_event(self, hass, mock_config_entry, api_logged_in):
        """Test handling websocket update with no event."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in,
            selected_location_ids=[TEST_LOCATION_ID],
        )

        coordinator._handle_ws_update(TEST_LOCATION_ID, None)
        # Should not raise any errors

    def test_handle_ws_update_no_existing_data(
        self, hass, mock_config_entry, api_logged_in
    ):
        """Test handling websocket update with no existing data."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in,
            selected_location_ids=[TEST_LOCATION_ID],
        )

        mock_event = MagicMock(spec=WsEvent)
        coordinator.async_request_refresh = MagicMock()

        coordinator._handle_ws_update(TEST_LOCATION_ID, mock_event)

        # Should trigger refresh when no existing data
        coordinator.async_request_refresh.assert_called_once()

    def test_handle_ws_update_success(self, hass, mock_config_entry, api_logged_in):
        """Test handling successful websocket update."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in,
            selected_location_ids=[TEST_LOCATION_ID],
        )

        mock_prev_state = MagicMock(spec=HomelyHomeState)
        mock_new_state = MagicMock(spec=HomelyHomeState)
        coordinator.data = {TEST_LOCATION_ID: mock_prev_state}

        mock_event = MagicMock(spec=WsEvent)

        with patch.object(
            HomelyHomeState, "from_ws_event", return_value=mock_new_state
        ) as mock_from_ws:
            coordinator.async_set_updated_data = MagicMock()
            coordinator._handle_ws_update(TEST_LOCATION_ID, mock_event)

            mock_from_ws.assert_called_once_with(mock_prev_state, mock_event)
            coordinator.async_set_updated_data.assert_called_once()
            assert coordinator._ws_active[TEST_LOCATION_ID] is True

    def test_handle_ws_update_error(self, hass, mock_config_entry, api_logged_in):
        """Test handling websocket update with error."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in,
            selected_location_ids=[TEST_LOCATION_ID],
        )

        mock_prev_state = MagicMock(spec=HomelyHomeState)
        coordinator.data = {TEST_LOCATION_ID: mock_prev_state}

        mock_event = MagicMock(spec=WsEvent)

        with patch.object(
            HomelyHomeState, "from_ws_event", side_effect=HomelyError("Parse error")
        ):
            coordinator.async_request_refresh = MagicMock()

            # Mock event loop time
            with patch.object(asyncio, "get_event_loop") as mock_loop:
                mock_loop.return_value.time.return_value = 100
                coordinator._handle_ws_update(TEST_LOCATION_ID, mock_event)

                # Should trigger refresh on error
                coordinator.async_request_refresh.assert_called_once()

    async def test_schedule_reconnect(self, hass, mock_config_entry, api_logged_in):
        """Test scheduling websocket reconnection."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in,
            selected_location_ids=[TEST_LOCATION_ID],
        )

        coordinator.start_websocket = AsyncMock()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await coordinator._schedule_reconnect(TEST_LOCATION_ID, attempt=1)

            coordinator.start_websocket.assert_called_once_with(
                TEST_LOCATION_ID, reconnect_if_exists=False
            )

    async def test_schedule_reconnect_max_attempts(
        self, hass, mock_config_entry, api_logged_in
    ):
        """Test scheduling websocket reconnection with max attempts."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in,
            selected_location_ids=[TEST_LOCATION_ID],
        )

        coordinator.start_websocket = AsyncMock(
            side_effect=HomelyWebSocketError("Connection failed")
        )

        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch.object(hass, "async_create_task") as mock_create_task,
        ):
            await coordinator._schedule_reconnect(TEST_LOCATION_ID, attempt=6)

            # Should not schedule another retry after max attempts
            mock_create_task.assert_not_called()

    async def test_async_shutdown(self, hass, mock_config_entry, api_logged_in):
        """Test async shutdown."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in,
            selected_location_ids=[TEST_LOCATION_ID],
        )

        mock_ws = MagicMock()
        mock_ws.disconnect = AsyncMock()
        coordinator._ws_clients[TEST_LOCATION_ID] = mock_ws
        coordinator._ws_active[TEST_LOCATION_ID] = True

        await coordinator.async_shutdown()

        mock_ws.disconnect.assert_called_once()
        assert len(coordinator._ws_clients) == 0
        assert len(coordinator._ws_active) == 0

    async def test_async_shutdown_with_error(
        self, hass, mock_config_entry, api_logged_in
    ):
        """Test async shutdown with disconnect error."""
        coordinator = HomelyDataUpdateCoordinator(
            hass,
            mock_config_entry,
            api=api_logged_in,
            selected_location_ids=[TEST_LOCATION_ID],
        )

        mock_ws = MagicMock()
        mock_ws.disconnect = AsyncMock(side_effect=Exception("Disconnect error"))
        coordinator._ws_clients[TEST_LOCATION_ID] = mock_ws

        # Should not raise exception
        await coordinator.async_shutdown()

        assert len(coordinator._ws_clients) == 0
