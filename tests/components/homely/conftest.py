"""Test configuration for Homely integration."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
import socketio
from aiohttp import ClientResponse, ClientSession
from homeassistant.const import CONF_LOCATION, CONF_PASSWORD, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homely.binary_sensor import (
    HomelyBatteryDefectSensor,
    HomelyBatteryLowSensor,
    HomelyEnergyCheckSensor,
    HomelyEntrySensor,
    HomelyFloodSensor,
    HomelyMotionSensor,
    HomelySmokeSensor,
    HomelyTamperSensor,
)
from custom_components.homely.const import CONF_AVAILABLE_LOCATIONS, DOMAIN
from custom_components.homely.coordinator import HomelyDataUpdateCoordinator
from custom_components.homely.homely_api import (
    HomelyApi,
    HomelyHomeState,
    HomelyWebSocketClient,
)
from custom_components.homely.models import (
    AlarmFeature,
    AlarmStates,
    APITokens,
    BatteryFeature,
    BatteryStates,
    Device,
    DeviceFeatures,
    DiagnosticFeature,
    DiagnosticStates,
    HomeResponse,
    Location,
    StateValue,
    TemperatureFeature,
    TemperatureStates,
    WsAlarmChangeEvent,
    WsDeviceChangeEvent,
    WsEvent,
    WsEventType,
    WsEventUnknown,
)
from tests.components.homely.const import (
    FAKE_HOME,
    FAKE_LOCATIONS_RESPONSE,
    FAKE_WS_EVENT,
    TEST_LOCATION_ID,
    TEST_LOCATION_NAME,
    TEST_PASSWORD,
    TEST_USERNAME,
)


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    return MockConfigEntry(
        # version=1,
        # minor_version=1,
        domain=DOMAIN,
        title="Homely Test",
        data={
            CONF_USERNAME: TEST_USERNAME,
            CONF_PASSWORD: TEST_PASSWORD,
            CONF_LOCATION: [TEST_LOCATION_ID],
            CONF_AVAILABLE_LOCATIONS: {
                TEST_LOCATION_ID: TEST_LOCATION_NAME,
                "loc1": "Test Home",
                "loc2": "Test Cabin",
            },
        },
        # source="user",
        # entry_id="test-entry-id",
        # discovery_keys={},  # type: ignore
        # options={},
        # subentries_data={},
        # unique_id=None,
    )


@pytest.fixture
def mock_config_entry_no_locations():
    """Create a mock config entry with no locations."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Homely Test No Locations",
        data={
            CONF_USERNAME: TEST_USERNAME,
            CONF_PASSWORD: TEST_PASSWORD,
            CONF_LOCATION: [],
            CONF_AVAILABLE_LOCATIONS: {},
        },
    )


def create_mock_device_features() -> MagicMock:
    """Create a mock device features."""
    features = MagicMock(spec=DeviceFeatures)
    return features


def create_mock_device(
    id: UUID | None = None,
    model_id: UUID | None = None,
    name: str = "Test Device",
    model_name: str = "Test Model",
    location: str = "Test Room",
    serial_number: str = "SN123456",
    online: bool = True,
    **kwargs,
) -> MagicMock:
    """Create a test device."""
    device = MagicMock(spec=Device)
    device.id = id or uuid4()
    device.model_id = model_id or uuid4()
    device.name = name
    device.model_name = model_name
    device.location = location
    device.serial_number = serial_number
    device.online = online
    device.features = create_mock_device_features()
    for key, value in kwargs.items():
        setattr(device, key, value)
    return device


def create_mock_sensor_state(
    value: StateValue, last_updated: datetime | None = None
) -> MagicMock:
    """Create a mock sensor state."""
    state = MagicMock()
    state.value = value
    state.last_updated = last_updated or datetime.now(tz=UTC)
    return state


def create_alarm_states(
    default_state_value=True, default_updated=None, **kwargs
) -> MagicMock:
    """Create mock alarm states."""
    states = MagicMock(spec=AlarmStates)
    states.alarm = create_mock_sensor_state(
        value=default_state_value, last_updated=default_updated
    )
    states.tamper = create_mock_sensor_state(
        value=default_state_value, last_updated=default_updated
    )
    states.flood = create_mock_sensor_state(
        value=default_state_value, last_updated=default_updated
    )
    states.fire = create_mock_sensor_state(
        value=default_state_value, last_updated=default_updated
    )

    for key, value in kwargs.items():
        setattr(states, key, value)

    return states


def create_mock_alarm_sensor_device(
    state_value=True,
    last_updated=None,
    device_name="Alarm Sensor",
    model_name="Alarm Sensor Model",
) -> MagicMock:
    """Create a mock alarm sensor device."""
    alarm_feature = MagicMock(spec=AlarmFeature)
    alarm_feature.states = create_alarm_states(
        default_state_value=state_value, default_updated=last_updated
    )
    mock_features = MagicMock(spec=DeviceFeatures)
    mock_features.alarm = alarm_feature
    return create_mock_device(
        name=device_name,
        model_name=model_name,
        features=mock_features,
    )


def create_mock_motion_device(state_value=True, last_updated=None) -> MagicMock:
    """Create a mock motion sensor device."""
    return create_mock_alarm_sensor_device(
        state_value=state_value,
        last_updated=last_updated,
        device_name="Motion Sensor",
        model_name="Motion Sensor Model",
    )


def create_mock_entry_sensor_device(state_value=True, last_updated=None) -> MagicMock:
    """Create a mock entry sensor device."""
    return create_mock_alarm_sensor_device(
        state_value=state_value,
        last_updated=last_updated,
        device_name="Entry Sensor",
        model_name="Entry Sensor Model",
    )


def create_mock_smoke_sensor_device(state_value=True, last_updated=None) -> MagicMock:
    """Create a mock smoke sensor device."""
    return create_mock_alarm_sensor_device(
        state_value=state_value,
        last_updated=last_updated,
        device_name="Smoke Sensor",
        model_name="Smoke Sensor Model",
    )


def create_mock_tamper_sensor_device(state_value=True, last_updated=None) -> MagicMock:
    """Create a mock tamper sensor device."""
    return create_mock_alarm_sensor_device(
        state_value=state_value,
        last_updated=last_updated,
        device_name="Tamper Sensor",
        model_name="Tamper Sensor Model",
    )


def create_mock_flood_sensor_device(state_value=True, last_updated=None) -> MagicMock:
    """Create a mock flood sensor device."""
    return create_mock_alarm_sensor_device(
        state_value=state_value,
        last_updated=last_updated,
        device_name="Flood Sensor",
        model_name="Flood Sensor Model",
    )


def create_mock_response(
    status: int = 200,
    json_data: dict | list | None = None,
    # raise_for_status: Literal[True, False, Exception] = False,
) -> MagicMock:
    """Create a mock ClientResponse."""
    mock_response = MagicMock(spec=ClientResponse)
    mock_response.status = status
    mock_response.json = AsyncMock(return_value=json_data or {})
    if status >= 400:
        mock_response.raise_for_status = MagicMock(
            side_effect=Exception(f"HTTP {status} Error")
        )
        mock_response.ok = False
    else:
        mock_response.raise_for_status = MagicMock()
        mock_response.ok = True
    return mock_response


@pytest.fixture
def mock_home_response_data() -> dict:
    """Fixture for mock home response data."""
    path = Path(__file__).parent / "fixtures" / "home_response.json"
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


@pytest.fixture
def mock_home_response(mock_home_response_data) -> MagicMock:
    """Fixture for a mock Home Assistant response."""
    return create_mock_response(status=200, json_data=mock_home_response_data)


@pytest.fixture
def mock_simple_home_response_object(mock_device) -> HomeResponse:
    """Fixture for a simple home response object."""
    home = HomeResponse(**FAKE_HOME)
    home.devices = [mock_device]
    return home


@pytest.fixture
def mock_simple_home_state(mock_simple_home_response_object) -> HomelyHomeState:
    """Fixture for a simple home state."""
    return HomelyHomeState.from_response(mock_simple_home_response_object)


@pytest.fixture
def mock_session() -> MagicMock:
    """Fixture for a mock ClientSession."""
    return MagicMock(spec=ClientSession)


@pytest.fixture
def api_with_mock_session(mock_session) -> HomelyApi:
    """Fixture for a mock HomelyApi."""
    return HomelyApi(mock_session)


@pytest.fixture
def valid_api_tokens() -> APITokens:
    """Fixture for valid API tokens."""
    return APITokens(
        access_token="valid_access_token",
        refresh_token="valid_refresh_token",
        expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
        refresh_expires_at=datetime.now(tz=UTC) + timedelta(days=1),
    )


@pytest.fixture
def api_logged_in(
    api_with_mock_session: HomelyApi, valid_api_tokens: APITokens
) -> HomelyApi:
    """Fixture for a logged-in HomelyApi."""
    api = api_with_mock_session
    api._auth = valid_api_tokens
    return api


@pytest.fixture
def api_logged_in_with_locations(
    api_logged_in: HomelyApi, mock_home_response: MagicMock
) -> HomelyApi:
    """Fixture for a logged-in HomelyApi with locations."""
    api = api_logged_in
    locations = {loc["locationId"]: Location(**loc) for loc in FAKE_LOCATIONS_RESPONSE}
    api._locations = locations
    return api


@pytest.fixture
def mock_device() -> MagicMock:
    """Fixture for a mock device."""
    return create_mock_device()


@pytest.fixture
def mock_coordinator_basic(hass) -> MagicMock:
    """Fixture for a basic mock HomelyDataUpdateCoordinator."""
    coordinator = MagicMock(spec=HomelyDataUpdateCoordinator)
    coordinator.hass = hass
    coordinator.location_id = TEST_LOCATION_ID
    # coordinator.get_device_state = MagicMock()
    return coordinator


@pytest.fixture
def mock_coordinator(
    hass, mock_config_entry, api_logged_in_with_locations
) -> HomelyDataUpdateCoordinator:
    """Fixture for a HomelyDataUpdateCoordinator with mock api and mock config entry."""
    return HomelyDataUpdateCoordinator(
        hass, mock_config_entry, api_logged_in_with_locations, [TEST_LOCATION_ID]
    )


@pytest.fixture
def mock_alarm_feature() -> MagicMock:
    """Fixture for a mock alarm feature."""
    alarm_feature = MagicMock(spec=AlarmFeature)
    alarm_feature.states = create_alarm_states()
    return alarm_feature


@pytest.fixture
def mock_device_with_features(mock_alarm_feature):
    """Fixture for a mock device with features."""
    features = MagicMock(spec=DeviceFeatures)
    features.alarm = mock_alarm_feature
    features.temperature = MagicMock(spec=TemperatureFeature)
    features.temperature.states = MagicMock(spec=TemperatureStates)
    features.temperature.states.temperature = create_mock_sensor_state(22.5)
    features.battery = MagicMock(spec=BatteryFeature)
    features.battery.states = MagicMock(spec=BatteryStates)
    features.battery.states.voltage = create_mock_sensor_state(3)
    features.battery.states.low = create_mock_sensor_state(False)
    features.diagnostic = MagicMock(spec=DiagnosticFeature)
    features.diagnostic.states = MagicMock(spec=DiagnosticStates)
    features.diagnostic.states.network_link_strength = create_mock_sensor_state(74)
    return create_mock_device(features=features)


@pytest.fixture
def mock_motion_sensor_device() -> MagicMock:
    """Fixture for a mock motion sensor device."""
    return create_mock_motion_device()


@pytest.fixture
def mock_entry_sensor_device() -> MagicMock:
    """Fixture for a mock entry sensor device."""
    return create_mock_entry_sensor_device()


@pytest.fixture
def mock_smoke_sensor_device() -> MagicMock:
    """Fixture for a mock smoke sensor device."""
    return create_mock_smoke_sensor_device()


@pytest.fixture
def mock_tamper_sensor_device() -> MagicMock:
    """Fixture for a mock tamper sensor device."""
    return create_mock_tamper_sensor_device()


@pytest.fixture
def mock_flood_sensor_device() -> MagicMock:
    """Fixture for a mock flood sensor device."""
    return create_mock_flood_sensor_device()


@pytest.fixture
def motion_sensor_test_entity(
    mock_coordinator_basic, mock_motion_sensor_device
) -> HomelyMotionSensor:
    """Fixture for a motion sensor entity with mock components."""
    return HomelyMotionSensor(
        mock_coordinator_basic, TEST_LOCATION_ID, mock_motion_sensor_device
    )


@pytest.fixture
def entry_sensor_test_entity(
    mock_coordinator_basic, mock_entry_sensor_device
) -> HomelyEntrySensor:
    """Fixture for a mock entry sensor device."""
    return HomelyEntrySensor(
        mock_coordinator_basic, TEST_LOCATION_ID, mock_entry_sensor_device
    )


@pytest.fixture
def smoke_sensor_test_entity(
    mock_coordinator_basic, mock_smoke_sensor_device
) -> HomelySmokeSensor:
    """Fixture for a mock smoke sensor device."""
    return HomelySmokeSensor(
        mock_coordinator_basic, TEST_LOCATION_ID, mock_smoke_sensor_device
    )


@pytest.fixture
def tamper_sensor_test_entity(
    mock_coordinator_basic, mock_tamper_sensor_device
) -> HomelyTamperSensor:
    """Fixture for a mock tamper sensor device."""
    return HomelyTamperSensor(
        mock_coordinator_basic, TEST_LOCATION_ID, mock_tamper_sensor_device
    )


@pytest.fixture
def flood_sensor_test_entity(
    mock_coordinator_basic, mock_flood_sensor_device
) -> HomelyFloodSensor:
    """Fixture for a mock flood sensor device."""
    return HomelyFloodSensor(
        mock_coordinator_basic, TEST_LOCATION_ID, mock_flood_sensor_device
    )


@pytest.fixture
def battery_low_sensor_test_entity(
    mock_coordinator_basic, mock_device
) -> HomelyBatteryLowSensor:
    """Fixture for a mock battery low sensor device."""
    return HomelyBatteryLowSensor(mock_coordinator_basic, TEST_LOCATION_ID, mock_device)


@pytest.fixture
def battery_defect_sensor_test_entity(
    mock_coordinator_basic, mock_device
) -> HomelyBatteryDefectSensor:
    """Fixture for a mock battery defect sensor device."""
    return HomelyBatteryDefectSensor(
        mock_coordinator_basic, TEST_LOCATION_ID, mock_device
    )


@pytest.fixture
def energy_check_sensor_test_entity(
    mock_coordinator_basic, mock_device
) -> HomelyEnergyCheckSensor:
    """Fixture for a mock energy check sensor device."""
    return HomelyEnergyCheckSensor(
        mock_coordinator_basic, TEST_LOCATION_ID, mock_device
    )


@pytest.fixture
def patch_async_create_client_session(mock_session):
    """Mock async function."""
    with patch(
        "custom_components.homely.coordinator.async_create_clientsession",
        return_value=mock_session,
    ) as mock:
        yield mock


@pytest.fixture
def mock_sio():
    """Fixture for a mock socketio client."""
    sio = MagicMock(spec=socketio.AsyncClient)
    sio.connect = AsyncMock()
    sio.disconnect = AsyncMock()
    sio.emit = AsyncMock()
    sio.wait = AsyncMock()
    sio.connected = False
    return sio


@pytest.fixture
def mock_homely_websocket_client(mock_sio, api_logged_in_with_locations: HomelyApi):
    """Fixture for a mock HomelyWebSocketClient."""
    ws_client = HomelyWebSocketClient(
        api_logged_in_with_locations,
        TEST_LOCATION_ID,
        logger=MagicMock(),
        name="MockClient",
    )
    ws_client._sio = mock_sio
    return ws_client


@pytest.fixture
def generate_ws_update_event():
    """Generate a WebSocket update event."""

    def _generate(
        event_type: WsEventType,
        location_id: str,
        device_id: str,
        feature: str,
        state_name: str,
        value: StateValue,
        updated: datetime | None = None,
    ) -> WsEvent:
        event = FAKE_WS_EVENT.copy()
        event["data"] = event["data"].copy()

        change = {
            "feature": feature,
            "stateName": state_name,
            "value": value,
            "lastUpdated": updated or datetime.now(UTC),
        }
        event["type"] = event_type
        event["data"]["rootLocationId"] = location_id
        event["data"]["deviceId"] = device_id
        event["data"]["change"] = change
        event["data"]["changes"] = [change]
        if event_type == WsEventType.DEVICE_STATE_CHANGED:
            return WsDeviceChangeEvent(**event)
        if event_type == WsEventType.ALARM_STATE_CHANGED:
            return WsAlarmChangeEvent(**event)
        return WsEventUnknown(**event)

    return _generate
