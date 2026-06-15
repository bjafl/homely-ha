import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
from uuid import uuid4

import aiohttp
import pytest
from aiohttp import ClientWebSocketResponse, WSMsgType

from custom_components.homely.const import (
    APP_API_CLIENT_ID,
    APP_API_CLIENT_SECRET,
    HomelyUrls,
)
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
            json={
                "client_id": APP_API_CLIENT_ID,
                "client_secret": APP_API_CLIENT_SECRET,
                "grant_type": "password",
                "username": TEST_USER_ID,
                "password": TEST_PASSWORD,
            },
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
            json={
                "client_id": APP_API_CLIENT_ID,
                "client_secret": APP_API_CLIENT_SECRET,
                "grant_type": "password",
                "username": "invalid_user",
                "password": "wrong_password",
            },
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
            json={
                "client_id": APP_API_CLIENT_ID,
                "client_secret": APP_API_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
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
        self,
        api_logged_in_with_locations: HomelyApi,
        mock_home_response: MagicMock,
        mock_alarm_state_response: MagicMock,
    ):
        """Test get_home method of HomelyApi."""
        api = api_logged_in_with_locations
        # get_home makes two GET calls: /home/{id} then /alarm/state/{id}
        api._client_session.get = AsyncMock(
            side_effect=[mock_home_response, mock_alarm_state_response]
        )
        headers = await api._get_auth_header()
        home = await api.get_home(TEST_LOCATION_ID)
        assert api._client_session.get.call_count == 2
        api._client_session.get.assert_any_call(
            f"{HomelyUrls.HOME}/{TEST_LOCATION_ID}", headers=headers
        )
        api._client_session.get.assert_any_call(
            f"{HomelyUrls.ALARM_STATE}/{TEST_LOCATION_ID}", headers=headers
        )
        assert home is not None
        assert str(home.location_id) == TEST_LOCATION_ID
        assert isinstance(home.devices, list)

    async def test_get_home_invalid_request(
        self, api_logged_in_with_locations: HomelyApi
    ):
        """Test get_home method of HomelyApi with invalid request."""
        api = api_logged_in_with_locations
        # 404 on the first call (/home/) raises immediately — alarm state never fetched
        api._client_session.get = AsyncMock(return_value=create_mock_response(404))
        with pytest.raises(HomelyRequestError):
            await api.get_home(TEST_LOCATION_ID)
        api._client_session.get.assert_called_once()

    async def test_get_home_invalid_response(
        self, api_logged_in_with_locations: HomelyApi
    ):
        """Test get_home method of HomelyApi with invalid response."""
        api = api_logged_in_with_locations
        # Both requests return 200 but missing nested structure → KeyError → HomelyValidationError
        invalid_response = create_mock_response(200, {"invalid": "data"})
        api._client_session.get = AsyncMock(return_value=invalid_response)
        with pytest.raises(HomelyValidationError):
            await api.get_home(TEST_LOCATION_ID)
        # Both home and alarm endpoints are called before the parse error is raised
        assert api._client_session.get.call_count == 2


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
    """Test Homely WebSocket client (EIO=3 / aiohttp)."""

    def _make_client(self, api: HomelyApi) -> HomelyWebSocketClient:
        return HomelyWebSocketClient(api, TEST_LOCATION_ID, name="TestClient")

    def _build_mock_ws(
        self, auth_data: str = '42["authenticated",true]'
    ) -> MagicMock:
        """Build a mock WS with a valid EIO=3 handshake sequence."""
        mock_ws = MagicMock(spec=ClientWebSocketResponse)
        mock_ws.closed = False
        mock_ws.send_str = AsyncMock()
        mock_ws.receive = AsyncMock(
            side_effect=[
                MagicMock(
                    type=WSMsgType.TEXT,
                    data='0{"pingInterval":25000,"pingTimeout":5000}',
                ),
                MagicMock(type=WSMsgType.TEXT, data="40"),
                MagicMock(type=WSMsgType.TEXT, data=auth_data),
            ]
        )
        return mock_ws

    def test_init(self, api_logged_in_with_locations: HomelyApi):
        """Test initialization of HomelyWebSocketClient."""
        ws_client = self._make_client(api_logged_in_with_locations)
        assert ws_client._api == api_logged_in_with_locations
        assert ws_client.location_id == TEST_LOCATION_ID
        assert ws_client.name == "TestClient"
        assert ws_client.connected is False
        assert ws_client._ws is None

    async def test_connect_success(self, api_logged_in_with_locations: HomelyApi):
        """Test successful EIO=3 WebSocket connection and authentication."""
        ws_client = self._make_client(api_logged_in_with_locations)
        mock_ws = self._build_mock_ws()
        api_logged_in_with_locations._client_session.ws_connect = AsyncMock(
            return_value=mock_ws
        )
        connect_cb = MagicMock()
        ws_client.register_event_callback(connect_cb, "connect")

        await ws_client.connect()

        assert ws_client.connected is True
        connect_cb.assert_called_once()
        # Verify auth payload sent with token and locationId
        mock_ws.send_str.assert_called_once()
        sent = mock_ws.send_str.call_args[0][0]
        assert '"authentication"' in sent
        assert TEST_LOCATION_ID in sent
        # Verify WS URL contains required query params
        ws_connect_url: str = api_logged_in_with_locations._client_session.ws_connect.call_args[0][0]
        assert f"locationId={TEST_LOCATION_ID}" in ws_connect_url
        assert "EIO=3" in ws_connect_url

    async def test_connect_with_ack_id_in_auth_response(
        self, api_logged_in_with_locations: HomelyApi
    ):
        """Auth response with numeric ack ID (421[...]) must succeed."""
        ws_client = self._make_client(api_logged_in_with_locations)
        mock_ws = self._build_mock_ws(auth_data='421["authenticated",true]')
        api_logged_in_with_locations._client_session.ws_connect = AsyncMock(
            return_value=mock_ws
        )
        await ws_client.connect()  # must not raise

    async def test_connect_api_auth_error(self, api_logged_in_with_locations: HomelyApi):
        """HomelyAuthError during token fetch is wrapped as HomelyWebSocketError."""
        ws_client = self._make_client(api_logged_in_with_locations)
        api_logged_in_with_locations._get_auth_header = AsyncMock(
            side_effect=HomelyAuthError("Auth failed")
        )
        with pytest.raises(HomelyWebSocketError):
            await ws_client.connect()

    async def test_connect_no_access_token(
        self, api_logged_in_with_locations: HomelyApi
    ):
        """None access_token after auth header fetch raises HomelyWebSocketError."""
        ws_client = self._make_client(api_logged_in_with_locations)
        api_logged_in_with_locations._get_auth_header = AsyncMock(return_value={})
        with patch.object(
            type(api_logged_in_with_locations), "access_token", new_callable=PropertyMock
        ) as mock_tok:
            mock_tok.return_value = None
            with pytest.raises(HomelyWebSocketError):
                await ws_client.connect()

    async def test_connect_network_error(self, api_logged_in_with_locations: HomelyApi):
        """aiohttp.ClientError during ws_connect is wrapped as HomelyWebSocketError."""
        ws_client = self._make_client(api_logged_in_with_locations)
        api_logged_in_with_locations._client_session.ws_connect = AsyncMock(
            side_effect=aiohttp.ClientError("Connection refused")
        )
        with pytest.raises(HomelyWebSocketError):
            await ws_client.connect()

    async def test_connect_bad_eio_open(self, api_logged_in_with_locations: HomelyApi):
        """Non-'0' first frame raises HomelyWebSocketError."""
        ws_client = self._make_client(api_logged_in_with_locations)
        mock_ws = MagicMock(spec=ClientWebSocketResponse)
        mock_ws.closed = False
        mock_ws.receive = AsyncMock(
            return_value=MagicMock(type=WSMsgType.TEXT, data="garbage")
        )
        api_logged_in_with_locations._client_session.ws_connect = AsyncMock(
            return_value=mock_ws
        )
        with pytest.raises(HomelyWebSocketError):
            await ws_client.connect()

    async def test_connect_auth_rejected(self, api_logged_in_with_locations: HomelyApi):
        """Server responding authenticated=false raises HomelyWebSocketError."""
        ws_client = self._make_client(api_logged_in_with_locations)
        mock_ws = self._build_mock_ws(auth_data='42["authenticated",false]')
        api_logged_in_with_locations._client_session.ws_connect = AsyncMock(
            return_value=mock_ws
        )
        with pytest.raises(HomelyWebSocketError):
            await ws_client.connect()

    def test_register_and_unregister_callback(
        self, api_logged_in_with_locations: HomelyApi
    ):
        """Register and unregister event callbacks."""
        ws_client = self._make_client(api_logged_in_with_locations)
        cb = MagicMock()

        ws_client.register_event_callback(cb, "event")
        assert cb in ws_client._websocket_event_callbacks["event"]

        ws_client.unregister_event_callback(cb, "event")
        assert cb not in ws_client._websocket_event_callbacks["event"]

        # Unregister from all event types at once
        ws_client.register_event_callback(cb, "event")
        ws_client.register_event_callback(cb, "connect")
        ws_client.unregister_event_callback(cb)
        assert cb not in ws_client._websocket_event_callbacks["event"]
        assert cb not in ws_client._websocket_event_callbacks["connect"]

    def test_parse_sio_packet_with_and_without_ack(
        self, api_logged_in_with_locations: HomelyApi
    ):
        """_parse_sio_packet strips numeric ack IDs and returns parsed events."""
        ws_client = self._make_client(api_logged_in_with_locations)
        payload = ["message", {"type": "device-state-changed", "eventData": FAKE_WS_EVENT["data"]}]

        # No ack ID
        raw_no_ack = "42" + json.dumps(payload)
        ack_id, event = ws_client._parse_sio_packet(raw_no_ack)
        assert ack_id is None
        assert event is not None

        # Numeric ack ID
        raw_with_ack = "4212" + json.dumps(payload)
        ack_id, event = ws_client._parse_sio_packet(raw_with_ack)
        assert ack_id == "12"
        assert event is not None

    async def test_disconnect(self, api_logged_in_with_locations: HomelyApi):
        """disconnect() sets flag and closes the underlying WS."""
        ws_client = self._make_client(api_logged_in_with_locations)
        mock_ws = MagicMock(spec=ClientWebSocketResponse)
        mock_ws.closed = False
        mock_ws.close = AsyncMock()
        ws_client._ws = mock_ws

        await ws_client.disconnect()

        assert ws_client._should_disconnect is True
        mock_ws.close.assert_called_once()
