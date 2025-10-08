from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
from uuid import uuid4

import pytest
import socketio
import socketio.exceptions

from custom_components.homely.const import HomelyUrls
from custom_components.homely.exceptions import (
    HomelyAuthError,
    HomelyAuthExpiredError,
    HomelyAuthInvalidError,
    HomelyAuthRequestError,
    HomelyRequestError,
    HomelyStateUpdateLocationMismatchError,
    HomelyStateUpdateError,
    HomelyStateUpdateMissingTargetError,
    HomelyStateUpdateOutOfOrderError,
    HomelyValidationError,
    HomelyValueError,
    HomelyWebSocketError,
)
from custom_components.homely.homely_api import (
    HomelyApi,
    HomelyHomeState,
    HomelyWebSocketClient,
    Location,
)
from custom_components.homely.models import (
    Device,
    HomeResponse,
    WsAlarmChangeEvent,
    WsDeviceChangeEvent,
    WsEventType,
    WsEventUnknown,
)
from tests.components.homely.conftest import create_mock_response
from tests.components.homely.const import (
    FAKE_LOCATIONS_RESPONSE,
    FAKE_TOKEN_RESPONSE,
    FAKE_WS_EVENT,
    TEST_LOCATION_ID,
    TEST_PASSWORD,
    TEST_USER_ID,
)


class TestHomelyApi:
    """Test Homely API."""

    def test_init(self, api_with_mock_session):
        """Test initialization of HomelyApi."""
        api = api_with_mock_session
        assert isinstance(api._request_timeout, int)
        assert isinstance(api._locations, dict)
        assert len(api._locations) == 0
        assert isinstance(api._cached_credentials, dict)
        assert len(api._cached_credentials) == 0
        assert api._auth is None
        assert api._client_session is not None
        assert isinstance(api._client_session, MagicMock)
        assert api.locations is None
        assert api.access_token is None
        assert api.is_authenticated is False
        assert api.is_reauth_token_valid is False

    async def test_valid_login(self, api_with_mock_session: HomelyApi):
        """Test login method of HomelyApi."""
        api = api_with_mock_session
        mock_response = create_mock_response(200, FAKE_TOKEN_RESPONSE)
        mock_post = AsyncMock(return_value=mock_response)
        api._client_session.post = mock_post
        await api.login(TEST_USER_ID, TEST_PASSWORD)
        mock_post.assert_called_once_with(
            HomelyUrls.AUTH_LOGIN,
            json={"username": TEST_USER_ID, "password": TEST_PASSWORD},
        )
        assert api._auth is not None
        assert api._auth.access_token == FAKE_TOKEN_RESPONSE["access_token"]
        assert api._auth.refresh_token == FAKE_TOKEN_RESPONSE["refresh_token"]
        assert api.is_authenticated is True
        assert api.is_reauth_token_valid is True
        assert api.access_token == FAKE_TOKEN_RESPONSE["access_token"]
        assert await api._get_auth_header() == {
            "Authorization": f"Bearer {FAKE_TOKEN_RESPONSE['access_token']}"
        }
        assert await api.get_access_token() == FAKE_TOKEN_RESPONSE["access_token"]

    async def test_invalid_login(self, api_with_mock_session: HomelyApi):
        """Test login method of HomelyApi with invalid credentials."""
        api = api_with_mock_session
        with pytest.raises(HomelyAuthInvalidError):
            await api._login()
        mock_response = create_mock_response(
            401, {"message": "Invalid user credentials"}
        )
        mock_post = AsyncMock(return_value=mock_response)
        api._client_session.post = mock_post
        with pytest.raises(HomelyAuthRequestError):
            await api.login("invalid_user", "wrong_password")
        mock_post.assert_called_once_with(
            HomelyUrls.AUTH_LOGIN,
            json={"username": "invalid_user", "password": "wrong_password"},
        )
        assert api.is_authenticated is False

    async def test_refresh_token(self, api_logged_in: HomelyApi):
        """Test refresh_token method of HomelyApi."""
        api = api_logged_in
        assert api._auth is not None
        api._auth.expires_at = datetime.now(UTC) - timedelta(seconds=10)
        assert api.is_authenticated is False
        assert api.is_reauth_token_valid is True
        mock_response = create_mock_response(200, FAKE_TOKEN_RESPONSE)
        mock_post = AsyncMock(return_value=mock_response)
        api._client_session.post = mock_post
        refresh_token = api._auth.refresh_token
        await api._ensure_token_valid()
        mock_post.assert_called_once_with(
            HomelyUrls.AUTH_REFRESH,
            json={"refresh_token": refresh_token},
        )
        assert api.is_authenticated is True

        api._auth.expires_at = datetime.now(UTC) - timedelta(seconds=10)
        mock_response_invalid = create_mock_response(
            401, {"message": "Invalid refresh token"}
        )
        mock_post_invalid = AsyncMock(return_value=mock_response_invalid)
        api._client_session.post = mock_post_invalid
        with pytest.raises(HomelyAuthRequestError):
            await api.refresh_token()

        api._auth.refresh_expires_at = datetime.now(UTC) - timedelta(seconds=10)
        assert api.is_reauth_token_valid is False
        with pytest.raises(HomelyAuthExpiredError):
            await api.refresh_token()

        api._auth = None
        with pytest.raises(HomelyAuthInvalidError):
            await api.refresh_token()

    async def test_get_locations(self, api_logged_in: HomelyApi):
        """Test get_locations method of HomelyApi."""
        api = api_logged_in
        mock_response = create_mock_response(200, FAKE_LOCATIONS_RESPONSE)
        mock_get = AsyncMock(return_value=mock_response)
        api._client_session.get = mock_get
        headers = await api._get_auth_header()
        locations = await api.get_locations()
        mock_get.assert_called_once_with(HomelyUrls.LOCATIONS, headers=headers)
        assert isinstance(locations, list)
        assert len(locations) == 2
        first_loc = locations[0]
        assert isinstance(first_loc, Location)
        assert str(first_loc.location_id) == TEST_LOCATION_ID

        loc_id_names = {str(loc.location_id): loc.name for loc in locations}
        for loc_id, loc_name in (await api.get_location_id_names()).items():
            assert loc_id in loc_id_names
            assert loc_id_names[loc_id] == loc_name

    async def test_get_locations_failure(self, api_logged_in: HomelyApi):
        """Test get_locations method of HomelyApi with failure."""
        api = api_logged_in
        mock_response = create_mock_response(500, {"message": "Server error"})
        mock_get = AsyncMock(return_value=mock_response)
        api._client_session.get = mock_get
        headers = await api._get_auth_header()
        with pytest.raises(HomelyRequestError):
            await api.get_locations()
        mock_get.assert_called_once_with(HomelyUrls.LOCATIONS, headers=headers)

    async def test_get_locations_invalid_response(self, api_logged_in: HomelyApi):
        """Test get_locations method of HomelyApi with invalid response."""
        api = api_logged_in
        mock_response = create_mock_response(200, [{"invalid": "data"}])
        mock_get = AsyncMock(return_value=mock_response)
        api._client_session.get = mock_get
        headers = await api._get_auth_header()
        with pytest.raises(HomelyValidationError):
            await api.get_locations()
        mock_get.assert_called_once_with(HomelyUrls.LOCATIONS, headers=headers)

    async def test_get_home(
        self, api_logged_in_with_locations: HomelyApi, mock_home_response: MagicMock
    ):
        """Test get_home method of HomelyApi."""
        api = api_logged_in_with_locations
        api._client_session.get = AsyncMock(return_value=mock_home_response)
        headers = await api._get_auth_header()
        home = await api.get_home(TEST_LOCATION_ID)
        api._client_session.get.assert_called_once_with(
            f"{HomelyUrls.HOME}/{TEST_LOCATION_ID}", headers=headers
        )
        assert home is not None
        assert str(home.location_id) == TEST_LOCATION_ID
        assert isinstance(home.devices, list)

    async def test_get_home_invalid_request(
        self, api_logged_in_with_locations: HomelyApi
    ):
        """Test get_home method of HomelyApi with invalid request."""
        api = api_logged_in_with_locations
        api._client_session.get = AsyncMock(return_value=create_mock_response(404))
        with pytest.raises(HomelyRequestError):
            await api.get_home(TEST_LOCATION_ID)
        api._client_session.get.assert_called_once()

    async def test_get_home_invalid_response(
        self, api_logged_in_with_locations: HomelyApi
    ):
        """Test get_home method of HomelyApi with invalid response."""
        api = api_logged_in_with_locations
        invalid_response = create_mock_response(200, {"invalid": "data"})
        api._client_session.get = AsyncMock(return_value=invalid_response)
        with pytest.raises(HomelyValidationError):
            await api.get_home(TEST_LOCATION_ID)
        api._client_session.get.assert_called_once()


class TestHomelyHomeState:
    """Test Homely HomeState."""

    def test_init(self, mock_simple_home_response_object: HomeResponse):
        """Test initialization of HomeState."""
        home_state = HomelyHomeState.from_response(mock_simple_home_response_object)
        assert str(home_state.location_id) == TEST_LOCATION_ID

    def test_get_device_by_id(
        self, mock_device: Device, mock_simple_home_state: HomelyHomeState
    ):
        """Test get_device_by_id method of HomeState."""
        home_state = mock_simple_home_state
        device = home_state.get_device(str(mock_device.id))
        assert device is not None
        assert device.id == mock_device.id
        assert device.name == mock_device.name

        device_none = home_state.get_device("non-existent-device")
        assert device_none is None

    def test_get_device_feature_state(
        self, mock_device_with_features: Device, mock_simple_home_state: HomelyHomeState
    ):
        """Test get_device_feature_state method of HomeState."""
        home_state = mock_simple_home_state
        home_state.devices.append(mock_device_with_features)
        assert mock_device_with_features.features.temperature is not None
        assert (
            mock_device_with_features.features.temperature.states.temperature
            is not None
        )
        temperature = (
            mock_device_with_features.features.temperature.states.temperature.value
        )
        state = home_state.get_device_feature_state(
            str(mock_device_with_features.id), "temperature", "temperature"
        )
        assert state is not None
        assert state.value == temperature
        state_none = home_state.get_device_feature_state(
            str(mock_device_with_features.id), "temperature", "non-existent-state"
        )
        assert state_none is None

    def test_process_ws_device_update(
        self,
        mock_device_with_features: Device,
        mock_simple_home_state: HomelyHomeState,
        generate_ws_update_event,
    ):
        """Test process_ws_device_update method of HomeState."""
        # Prepare home state and target device
        home_state = mock_simple_home_state
        mock_device = mock_device_with_features
        home_state.devices.append(mock_device)
        mock_device_id = str(mock_device.id)
        assert home_state.get_device(mock_device_id) is not None

        # Test successful update
        assert mock_device.features.temperature is not None
        assert mock_device.features.temperature.states.temperature is not None
        old_temperature = mock_device.features.temperature.states.temperature.value
        assert old_temperature is not None
        new_temperature = old_temperature + 5
        dt_updated = datetime.now(UTC)
        ws_event: WsDeviceChangeEvent = generate_ws_update_event(
            event_type=WsEventType.DEVICE_STATE_CHANGED,
            location_id=TEST_LOCATION_ID,
            device_id=mock_device_id,
            feature="temperature",
            state_name="temperature",
            value=new_temperature,
            updated=dt_updated,
        )
        assert str(ws_event.data.device_id) == mock_device_id

        home_state._process_ws_device_state_update(ws_event.data)
        new_temperature_state = home_state.get_device_feature_state(
            str(mock_device_with_features.id), "temperature", "temperature"
        )
        assert new_temperature_state is not None
        assert new_temperature_state.value == new_temperature
        assert new_temperature_state.last_updated == dt_updated

        # Test update outdated
        dt_outdated = dt_updated - timedelta(hours=10)
        old_temperature = new_temperature
        new_temperature = old_temperature + 5
        ws_event_outdated: WsDeviceChangeEvent = generate_ws_update_event(
            event_type=WsEventType.DEVICE_STATE_CHANGED,
            location_id=TEST_LOCATION_ID,
            device_id=mock_device_id,
            feature="temperature",
            state_name="temperature",
            value=new_temperature,
            updated=dt_outdated,
        )
        home_state._process_ws_device_state_update(
            ws_event_outdated.data, ignore_outdated_values=True
        )
        temperature_state = home_state.get_device_feature_state(
            str(mock_device_with_features.id), "temperature", "temperature"
        )
        assert temperature_state is not None
        assert temperature_state.value == old_temperature
        assert temperature_state.last_updated == dt_updated
        with pytest.raises(HomelyStateUpdateOutOfOrderError):
            home_state._process_ws_device_state_update(
                ws_event_outdated.data, ignore_outdated_values=False
            )

        # Test update missing device state
        mock_device.features.temperature.states.temperature = None
        assert (
            home_state.get_device_feature_state(
                str(mock_device_with_features.id), "temperature", "temperature"
            )
        ) is None
        home_state._process_ws_device_state_update(
            ws_event.data, ignore_missing_states=True
        )
        assert (
            home_state.get_device_feature_state(
                str(mock_device_with_features.id), "temperature", "temperature"
            )
        ) is None
        with pytest.raises(HomelyStateUpdateMissingTargetError):
            home_state._process_ws_device_state_update(ws_event.data)

        # Test update for non-existent device
        home_state.devices = []
        with pytest.raises(HomelyValueError):
            home_state._process_ws_device_state_update(ws_event.data)

        # Test wrong location ID
        ws_event.data.root_location_id = uuid4()
        with pytest.raises(HomelyStateUpdateLocationMismatchError):
            home_state._process_ws_device_state_update(ws_event.data)

    def test_update_state(self, mock_simple_home_state: HomelyHomeState):
        """Test update_state method of HomeState."""
        home_state = mock_simple_home_state
        event_device = MagicMock(spec=WsDeviceChangeEvent)
        event_device.type = WsEventType.DEVICE_STATE_CHANGED
        event_device.data = MagicMock()
        mock_process_device_update = MagicMock()
        home_state._process_ws_device_state_update = mock_process_device_update
        home_state.update_state(event_device)
        mock_process_device_update.assert_called_once()

        event_alarm = MagicMock(spec=WsAlarmChangeEvent)
        event_alarm.type = WsEventType.ALARM_STATE_CHANGED
        event_alarm.data = MagicMock()
        mock_process_alarm_update = MagicMock()
        home_state._process_ws_alarm_state_update = mock_process_alarm_update
        home_state.update_state(event_alarm)
        mock_process_alarm_update.assert_called_once()

        event_unknown = MagicMock(spec=WsEventUnknown)
        event_unknown.type = "unknown-event-type"
        event_unknown.data = MagicMock()
        with pytest.raises(HomelyStateUpdateError):
            home_state.update_state(event_unknown)


class TestHomelyWebSocketClient:
    """Test Homely WebSocket client."""

    def test_init(self, api_logged_in_with_locations: HomelyApi):
        """Test initialization of HomelyWebSocketClient."""

        ws_client = HomelyWebSocketClient(
            api_logged_in_with_locations, TEST_LOCATION_ID, name="TestClient"
        )
        assert ws_client._api == api_logged_in_with_locations
        assert ws_client.location_id == TEST_LOCATION_ID
        assert ws_client._sio is not None
        assert ws_client.name == "TestClient"
        assert ws_client.connected is False

    async def test_valid_connect(
        self, mock_homely_websocket_client: HomelyWebSocketClient
    ):
        """Test valid sio connection attempt for HomelyWebSocketClient."""
        ws_client = mock_homely_websocket_client
        assert ws_client._location_id == TEST_LOCATION_ID  # Expects this from fixture
        fake_token = "test_token"
        fake_auth_header = {"Authorization": f"Bearer {fake_token}"}
        mock_get_auth_header = AsyncMock(return_value=fake_auth_header)
        ws_client._api._get_auth_header = mock_get_auth_header
        ws_client._setup_sio_events = MagicMock()

        ws_client._sio.connected = True  # Simulate successful connection
        with patch.object(
            type(ws_client._api), "access_token", new_callable=PropertyMock
        ) as mock_access_token:
            mock_access_token.return_value = fake_token
            await ws_client.connect()  # mocked in fixture

        ws_client._setup_sio_events.assert_called_once()

        # Verify the URL contains properly encoded token
        sio_connect: AsyncMock = ws_client._sio.connect  # type: ignore
        call_args = sio_connect.call_args

        url: str = call_args[0][0]
        assert f"locationId={TEST_LOCATION_ID}" in url
        assert f"token=Bearer%20{fake_token}" in url
        assert url.startswith(HomelyUrls.WEBSOCKET)

        headers: dict = call_args[1]["headers"]
        assert headers.get("Authorization") == fake_auth_header["Authorization"]
        assert headers.get("locationId") == TEST_LOCATION_ID

    async def test_invalid_connect_api_err(
        self, mock_homely_websocket_client: HomelyWebSocketClient
    ):
        """Test invalid sio connection attempt for HomelyWebSocketClient."""
        ws_client = mock_homely_websocket_client
        api = ws_client._api
        api._get_auth_header = AsyncMock(
            side_effect=HomelyAuthError("Mocked auth error")
        )
        with pytest.raises(HomelyWebSocketError):
            await ws_client.connect()

        api._get_auth_header = AsyncMock(return_value="Mocked")
        with patch.object(
            type(api), "access_token", new_callable=PropertyMock
        ) as mock_access_token:
            mock_access_token.return_value = None
            with pytest.raises(HomelyWebSocketError):
                await ws_client.connect()

    async def test_invalid_connect_sio_err(
        self, mock_homely_websocket_client: HomelyWebSocketClient
    ):
        """Test invalid sio connection attempt for HomelyWebSocketClient."""
        ws_client = mock_homely_websocket_client
        ws_client._setup_sio_events = MagicMock()
        sio = ws_client._sio

        sio.connected = False  # Simulate failed connection
        with pytest.raises(HomelyWebSocketError):
            await ws_client.connect()

        sio.connect = AsyncMock(
            side_effect=socketio.exceptions.ConnectionError("Mocked sio connect error")
        )
        with pytest.raises(HomelyWebSocketError):
            await ws_client.connect()

        sio.connect = AsyncMock(side_effect=ValueError("Mocked invalid params error"))
        with pytest.raises(HomelyWebSocketError):
            await ws_client.connect()

        sio.connect = AsyncMock(side_effect=TimeoutError("Mocked timeout error"))
        with pytest.raises(HomelyWebSocketError):
            await ws_client.connect()

        sio.connect = AsyncMock(side_effect=Exception("Mocked unknown error"))
        with pytest.raises(HomelyWebSocketError):
            await ws_client.connect()

    async def test_sio_event_registration(
        self, mock_homely_websocket_client: HomelyWebSocketClient
    ):
        """Test setup of sio events for HomelyWebSocketClient."""
        ws_client = mock_homely_websocket_client
        sio = ws_client._sio
        sio.event = MagicMock(side_effect=lambda func: func)  # Decorator passthrough
        ws_client._setup_sio_events()

        """Test that event handlers are registered."""
        # The decorator should have been called for each event
        assert sio.event.call_count == 3

        # Check that handlers were registered for correct events
        calls = [str(call) for call in sio.event.call_args_list]
        assert any("connect" in str(call) for call in calls)
        assert any("disconnect" in str(call) for call in calls)
        assert any("event" in str(call) for call in calls)

        # # Get registered event handler for testing
        # event_handler: Callable | None = None
        # for name, handler in ws_client._sio.handlers.items():
        #     if name == "event":
        #         event_handler = handler
        #         break
        # assert event_handler is not None

    async def test_event_callback(
        self, mock_homely_websocket_client: HomelyWebSocketClient
    ):
        """Test sio event callback."""
        ws_client = mock_homely_websocket_client
        sio = ws_client._sio
        callback = MagicMock()
        ws_client.register_event_callback(callback, "event")

        # Capture decorated sio event handlers
        registered_sio_events = {}

        def fake_register_event(func):
            registered_sio_events[func.__name__] = func
            return func

        sio.event = fake_register_event
        ws_client._setup_sio_events()

        # Simulate handling a WebSocket event
        event_handler = registered_sio_events.get("event")
        assert event_handler is not None
        event_handler(FAKE_WS_EVENT)

        callback.assert_called_once()
        call_args = callback.call_args
        event_data: WsDeviceChangeEvent = call_args[0][0]
        assert event_data.type == FAKE_WS_EVENT["type"]
        assert str(event_data.data.root_location_id) == TEST_LOCATION_ID

        # Test unregistering the callback
        event_cbs = ws_client._websocket_event_callbacks.get("event", [])
        assert callback in event_cbs
        ws_client.unregister_event_callback(callback, "event")
        event_cbs = ws_client._websocket_event_callbacks.get("event", [])
        assert callback not in event_cbs

        # Test unregistering from all event types

        ws_client._websocket_event_callbacks["event"] = [callback]
        ws_client._websocket_event_callbacks["connect"] = [callback]

        # Add dummy to disconnect for coverage
        def dummy(x):
            return

        ws_client._websocket_event_callbacks["disconnect"] = [dummy]

        assert callback in ws_client._websocket_event_callbacks["event"]
        assert callback in ws_client._websocket_event_callbacks["connect"]
        ws_client.unregister_event_callback(callback)
        assert callback not in ws_client._websocket_event_callbacks["event"]
        assert callback not in ws_client._websocket_event_callbacks["connect"]

    def test_reconnect(self, mock_homely_websocket_client: HomelyWebSocketClient):
        """Test reconnect method of HomelyWebSocketClient."""

        # TODO
