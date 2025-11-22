"""Test the Homely sensor entities."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from homeassistant.components.alarm_control_panel.const import AlarmControlPanelState
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfTemperature

from custom_components.homely.const import DOMAIN, HomelyEntityIcons
from custom_components.homely.models import AlarmState, MeteringStateName
from custom_components.homely.sensor import (
    HomelyAlarmStateSensor,
    HomelyEnergyDemandSensor,
    HomelyEnergySensor,
    HomelySignalStrengthSensor,
    HomelyTemperatureSensor,
    HomelyThermostatSensor,
    async_setup_entry,
    create_entities_from_device,
)

from .conftest import TEST_LOCATION_ID, create_mock_device, create_mock_sensor_state


class TestHomelySetup:
    """Test setup of Homely sensors."""

    async def test_async_setup_entry_no_locations(
        self, hass, mock_config_entry, mock_coordinator_basic
    ):
        """Test setup entry with no locations selected."""
        mock_coordinator_basic.selected_location_ids = []
        hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator_basic}}

        mock_add_entities = MagicMock()
        await async_setup_entry(hass, mock_config_entry, mock_add_entities)
        mock_add_entities.assert_not_called()

    async def test_async_setup_entry_no_data(
        self, hass, mock_config_entry, mock_coordinator_basic
    ):
        """Test setup entry with no data for selected locations."""
        mock_coordinator_basic.selected_location_ids = [TEST_LOCATION_ID]
        mock_coordinator_basic.data = {}
        hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator_basic}}

        mock_add_entities = MagicMock()
        await async_setup_entry(hass, mock_config_entry, mock_add_entities)
        mock_add_entities.assert_not_called()

    async def test_async_setup_entry_with_devices(
        self, hass, mock_config_entry, mock_coordinator_basic
    ):
        """Test setup entry with devices."""
        # Create mock home state with devices
        mock_home_state = MagicMock()
        mock_home_state.gateway_serial = "TEST_SERIAL"
        mock_home_state.name = "Test Home"
        mock_home_state.user_role = "owner"
        mock_home_state.alarm_state = AlarmState.DISARMED

        # Create mock device with temperature feature
        mock_device = create_mock_device()
        mock_temp_state = create_mock_sensor_state(22.5, datetime.now(tz=UTC))
        mock_features = MagicMock()
        mock_features.temperature.states.temperature = mock_temp_state
        mock_device.features = mock_features

        mock_home_state.devices = [mock_device]

        mock_coordinator_basic.selected_location_ids = [TEST_LOCATION_ID]
        mock_coordinator_basic.data = {TEST_LOCATION_ID: mock_home_state}
        hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator_basic}}

        mock_add_entities = MagicMock()
        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should have called add_entities once
        mock_add_entities.assert_called_once()
        # Get the entities that were added
        entities = mock_add_entities.call_args[0][0]
        # Should have alarm state sensor + temperature sensor
        assert len(entities) >= 2
        # First entity should be alarm state sensor
        assert isinstance(entities[0], HomelyAlarmStateSensor)


class TestCreateEntitiesFromDevice:
    """Test create_entities_from_device function."""

    def test_create_temperature_sensor(self, mock_coordinator_basic):
        """Test creating temperature sensor."""
        mock_device = create_mock_device()
        mock_device.features.temperature = MagicMock()
        mock_device.features.diagnostic = None
        mock_device.features.metering = None
        mock_device.features.thermostat = None

        entities = create_entities_from_device(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )

        assert len(entities) == 1
        assert isinstance(entities[0], HomelyTemperatureSensor)

    def test_create_signal_strength_sensor(self, mock_coordinator_basic):
        """Test creating signal strength sensor."""
        mock_device = create_mock_device()
        mock_device.features.temperature = None
        mock_device.features.diagnostic = MagicMock()
        mock_device.features.diagnostic.states.network_link_strength = MagicMock()
        mock_device.features.metering = None
        mock_device.features.thermostat = None

        entities = create_entities_from_device(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )

        assert len(entities) == 1
        assert isinstance(entities[0], HomelySignalStrengthSensor)

    def test_create_energy_sensors(self, mock_coordinator_basic):
        """Test creating energy sensors."""
        mock_device = create_mock_device()
        mock_device.features.temperature = None
        mock_device.features.diagnostic = None
        mock_device.features.metering = MagicMock()
        mock_device.features.metering.states.summation_delivered = MagicMock()
        mock_device.features.metering.states.summation_received = MagicMock()
        mock_device.features.metering.states.demand = MagicMock()
        mock_device.features.thermostat = None

        entities = create_entities_from_device(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )

        assert len(entities) == 3
        assert any(isinstance(e, HomelyEnergySensor) for e in entities)
        assert any(isinstance(e, HomelyEnergyDemandSensor) for e in entities)

    def test_create_thermostat_sensor(self, mock_coordinator_basic):
        """Test creating thermostat sensor."""
        mock_device = create_mock_device()
        mock_device.features.temperature = None
        mock_device.features.diagnostic = None
        mock_device.features.metering = None
        mock_device.features.thermostat = MagicMock()

        entities = create_entities_from_device(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )

        assert len(entities) == 1
        assert isinstance(entities[0], HomelyThermostatSensor)

    def test_create_multiple_sensors(self, mock_coordinator_basic):
        """Test creating multiple sensors from one device."""
        mock_device = create_mock_device()
        mock_device.features.temperature = MagicMock()
        mock_device.features.diagnostic = MagicMock()
        mock_device.features.diagnostic.states.network_link_strength = MagicMock()
        mock_device.features.metering = MagicMock()
        mock_device.features.metering.states.summation_delivered = MagicMock()
        mock_device.features.metering.states.summation_received = None
        mock_device.features.metering.states.demand = None
        mock_device.features.thermostat = None

        entities = create_entities_from_device(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )

        # Should have temperature + signal + energy delivered
        assert len(entities) == 3
        assert any(isinstance(e, HomelyTemperatureSensor) for e in entities)
        assert any(isinstance(e, HomelySignalStrengthSensor) for e in entities)
        assert any(isinstance(e, HomelyEnergySensor) for e in entities)

    def test_create_no_sensors(self, mock_coordinator_basic):
        """Test creating no sensors when device has no features."""
        mock_device = create_mock_device()
        mock_device.features.temperature = None
        mock_device.features.diagnostic = None
        mock_device.features.metering = None
        mock_device.features.thermostat = None

        entities = create_entities_from_device(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )

        assert len(entities) == 0


class TestHomelyTemperatureSensor:
    """Test Homely temperature sensor."""

    def test_init(self, mock_device, mock_coordinator_basic):
        """Test temperature sensor initialization."""
        sensor = HomelyTemperatureSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        assert sensor.has_entity_name is True
        assert sensor._attr_unique_id == f"{mock_device.id}_temperature"
        assert sensor._attr_translation_key == "temperature"
        assert sensor._attr_native_unit_of_measurement == UnitOfTemperature.CELSIUS
        assert sensor._attr_device_class == SensorDeviceClass.TEMPERATURE
        assert sensor._attr_state_class == SensorStateClass.MEASUREMENT

    def test_get_current_sensor_state_device_none(
        self, mock_device, mock_coordinator_basic
    ):
        """Test getting current sensor state when device is None."""
        sensor = HomelyTemperatureSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        mock_get_none = MagicMock(return_value=None)
        sensor._get_current_device_state = mock_get_none
        assert sensor._get_current_sensor_state() is None
        mock_get_none.assert_called_once()

    def test_get_current_sensor_no_temperature_feature(
        self, mock_device, mock_coordinator_basic
    ):
        """Test getting current sensor state with no temperature feature."""
        sensor = HomelyTemperatureSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        mock_device_no_temp = MagicMock()
        mock_device_no_temp.features.temperature = None
        mock_get_no_temp = MagicMock(return_value=mock_device_no_temp)
        sensor._get_current_device_state = mock_get_no_temp
        assert sensor._get_current_sensor_state() is None
        mock_get_no_temp.assert_called_once()

    def test_get_current_sensor_state_no_sensor_state(
        self, mock_device, mock_coordinator_basic
    ):
        """Test getting current sensor state with no temperature state."""
        sensor = HomelyTemperatureSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        mock_device_no_temp_state = MagicMock()
        mock_device_no_temp_state.features.temperature.states.temperature = None
        mock_get_device_no_temp_state = MagicMock(
            return_value=mock_device_no_temp_state
        )
        sensor._get_current_device_state = mock_get_device_no_temp_state
        assert sensor._get_current_sensor_state() is None
        mock_get_device_no_temp_state.assert_called_once()

    def test_get_current_sensor_state_valid(self, mock_device, mock_coordinator_basic):
        """Test getting current sensor state with valid state."""
        sensor = HomelyTemperatureSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        last_updated = datetime.now(tz=UTC)
        state_value = 22.5
        mock_state = create_mock_sensor_state(state_value, last_updated)
        mock_device_valid = MagicMock()
        mock_device_valid.features.temperature.states.temperature = mock_state
        mock_get_device_valid_state = MagicMock(return_value=mock_device_valid)
        sensor._get_current_device_state = mock_get_device_valid_state
        state = sensor._get_current_sensor_state()
        assert state is not None
        assert state.value == state_value
        assert state.last_updated == last_updated
        mock_get_device_valid_state.assert_called_once()
        assert sensor.native_value == state_value


class TestHomelyAlarmStateSensor:
    """Test Homely alarm state sensor."""

    def test_init(self, mock_coordinator_basic):
        """Test alarm state sensor initialization."""
        mock_home_state = MagicMock()
        mock_home_state.gateway_serial = "TEST_SERIAL"
        mock_home_state.name = "Test Home"
        mock_home_state.user_role = "owner"
        sensor = HomelyAlarmStateSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_home_state
        )
        assert sensor.has_entity_name is True
        assert sensor._attr_unique_id == f"{TEST_LOCATION_ID}_alarm_state"
        assert sensor._attr_translation_key == "alarm_state"
        assert sensor._attr_device_class == SensorDeviceClass.ENUM
        assert sensor._attr_options is not None
        assert AlarmControlPanelState.DISARMED in sensor._attr_options
        assert AlarmControlPanelState.ARMED_AWAY in sensor._attr_options
        assert sensor.device_serial == "TEST_SERIAL"
        assert sensor.device_name == "Test Home"

    def test_get_current_sensor_state_no_home_state(self, mock_coordinator_basic):
        """Test getting current sensor state when home state is None."""
        mock_home_state = MagicMock()
        sensor = HomelyAlarmStateSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_home_state
        )
        sensor.coordinator.get_home_state = MagicMock(return_value=None)
        assert sensor._get_current_sensor_state() is None

    def test_get_current_sensor_state_no_alarm_state(self, mock_coordinator_basic):
        """Test getting current sensor state when alarm state is None."""
        mock_home_state = MagicMock()
        sensor = HomelyAlarmStateSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_home_state
        )
        mock_state = MagicMock()
        mock_state.alarm_state = None
        sensor.coordinator.get_home_state = MagicMock(return_value=mock_state)
        assert sensor._get_current_sensor_state() is None

    def test_get_current_sensor_state_valid(self, mock_coordinator_basic):
        """Test getting current sensor state with valid state."""
        mock_home_state = MagicMock()
        sensor = HomelyAlarmStateSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_home_state
        )
        mock_state = MagicMock()
        mock_state.alarm_state = AlarmState.DISARMED
        sensor.coordinator.get_home_state = MagicMock(return_value=mock_state)
        state = sensor._get_current_sensor_state()
        assert state == AlarmState.DISARMED
        assert sensor.native_value == AlarmControlPanelState.DISARMED

    def test_alarm_state_mapping(self, mock_coordinator_basic):
        """Test alarm state mapping."""
        mock_home_state = MagicMock()
        sensor = HomelyAlarmStateSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_home_state
        )

        test_cases = [
            (AlarmState.DISARMED, AlarmControlPanelState.DISARMED),
            (AlarmState.ARMED_AWAY, AlarmControlPanelState.ARMED_AWAY),
            (AlarmState.ARMED_STAY, AlarmControlPanelState.ARMED_HOME),
            (AlarmState.ARMED_NIGHT, AlarmControlPanelState.ARMED_NIGHT),
            (AlarmState.BREACHED, AlarmControlPanelState.TRIGGERED),
            (AlarmState.ALARM_PENDING, AlarmControlPanelState.PENDING),
        ]

        for homely_state, expected_ha_state in test_cases:
            mock_state = MagicMock()
            mock_state.alarm_state = homely_state
            sensor.coordinator.get_home_state = MagicMock(return_value=mock_state)
            assert sensor.native_value == expected_ha_state

    def test_icon_property(self, mock_coordinator_basic):
        """Test icon property."""
        mock_home_state = MagicMock()
        sensor = HomelyAlarmStateSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_home_state
        )

        test_cases = [
            (AlarmState.DISARMED, HomelyEntityIcons.ALARM_DISARMED),
            (AlarmState.ARMED_STAY, HomelyEntityIcons.ALARM_ARMED_HOME),
            (AlarmState.ARMED_AWAY, HomelyEntityIcons.ALARM_ARMED_AWAY),
            (AlarmState.ARMED_NIGHT, HomelyEntityIcons.ALARM_ARMED_NIGHT),
            (AlarmState.BREACHED, HomelyEntityIcons.ALARM_TRIGGERED),
            (AlarmState.ALARM_PENDING, HomelyEntityIcons.ALARM_PENDING),
            (None, HomelyEntityIcons.ALARM_UNKNOWN),
            (AlarmState.ALARM_STAY_PENDING, HomelyEntityIcons.ALARM_ARMING),
        ]

        for alarm_state, expected_icon in test_cases:
            mock_state = MagicMock()
            mock_state.alarm_state = alarm_state
            sensor.coordinator.get_home_state = MagicMock(return_value=mock_state)
            # Access native_value to trigger state update
            _ = sensor.native_value
            assert sensor.icon == expected_icon

    def test_extra_state_attributes(self, mock_coordinator_basic):
        """Test extra state attributes."""
        mock_home_state = MagicMock()
        mock_home_state.user_role = "owner"
        sensor = HomelyAlarmStateSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_home_state
        )
        attrs = sensor.extra_state_attributes
        assert attrs is not None
        assert "user_role" in attrs
        assert attrs["user_role"] == "owner"
        assert "homely_alarm_state" in attrs


class TestHomelySignalStrengthSensor:
    """Test Homely signal strength sensor."""

    def test_init(self, mock_device, mock_coordinator_basic):
        """Test signal strength sensor initialization."""
        sensor = HomelySignalStrengthSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        assert sensor.has_entity_name is True
        assert sensor._attr_unique_id == f"{mock_device.id}_signal_strength"
        assert sensor._attr_translation_key == "signal_strength"
        assert sensor._attr_native_unit_of_measurement == "%"
        assert sensor._attr_state_class == SensorStateClass.MEASUREMENT
        assert sensor._attr_entity_category == EntityCategory.DIAGNOSTIC

    def test_get_current_sensor_state_device_none(
        self, mock_device, mock_coordinator_basic
    ):
        """Test getting current sensor state when device is None."""
        sensor = HomelySignalStrengthSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        mock_get_none = MagicMock(return_value=None)
        sensor._get_current_device_state = mock_get_none
        assert sensor._get_current_sensor_state() is None
        mock_get_none.assert_called_once()

    def test_get_current_sensor_no_diagnostic_feature(
        self, mock_device, mock_coordinator_basic
    ):
        """Test getting current sensor state with no diagnostic feature."""
        sensor = HomelySignalStrengthSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        mock_device_no_diag = MagicMock()
        mock_device_no_diag.features.diagnostic = None
        mock_get_no_diag = MagicMock(return_value=mock_device_no_diag)
        sensor._get_current_device_state = mock_get_no_diag
        assert sensor._get_current_sensor_state() is None
        mock_get_no_diag.assert_called_once()

    def test_get_current_sensor_state_valid(self, mock_device, mock_coordinator_basic):
        """Test getting current sensor state with valid state."""
        sensor = HomelySignalStrengthSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        last_updated = datetime.now(tz=UTC)
        state_value = 85
        mock_state = create_mock_sensor_state(state_value, last_updated)
        mock_device_valid = MagicMock()
        mock_device_valid.features.diagnostic.states.network_link_strength = mock_state
        mock_device_valid.features.diagnostic.states.network_link_address = None
        mock_get_device_valid_state = MagicMock(return_value=mock_device_valid)
        sensor._get_current_device_state = mock_get_device_valid_state
        state = sensor._get_current_sensor_state()
        assert state is not None
        assert state.value == state_value
        assert state.last_updated == last_updated
        assert sensor.native_value == state_value

    def test_icon_property(self, mock_device, mock_coordinator_basic):
        """Test icon property based on signal strength."""
        sensor = HomelySignalStrengthSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )

        test_cases = [
            (85, HomelyEntityIcons.SIGNAL_HIGH),
            (70, HomelyEntityIcons.SIGNAL_MEDIUM),
            (50, HomelyEntityIcons.SIGNAL_LOW),
            (30, HomelyEntityIcons.SIGNAL_VERY_LOW),
            (None, HomelyEntityIcons.SIGNAL_NONE),
        ]

        for strength_value, expected_icon in test_cases:
            if strength_value is None:
                sensor._get_current_sensor_state = MagicMock(return_value=None)
            else:
                mock_state = create_mock_sensor_state(
                    strength_value, datetime.now(tz=UTC)
                )
                mock_device_valid = MagicMock()
                mock_device_valid.features.diagnostic.states.network_link_strength = (
                    mock_state
                )
                mock_device_valid.features.diagnostic.states.network_link_address = None
                sensor._get_current_device_state = MagicMock(
                    return_value=mock_device_valid
                )
            assert sensor.icon == expected_icon

    def test_extra_state_attributes(self, mock_device, mock_coordinator_basic):
        """Test extra state attributes."""
        sensor = HomelySignalStrengthSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        mock_state = create_mock_sensor_state(75, datetime.now(tz=UTC))
        mock_address = create_mock_sensor_state(
            "00:11:22:33:44:55", datetime.now(tz=UTC)
        )
        mock_device_valid = MagicMock()
        mock_device_valid.features.diagnostic.states.network_link_strength = mock_state
        mock_device_valid.features.diagnostic.states.network_link_address = mock_address
        sensor._get_current_device_state = MagicMock(return_value=mock_device_valid)
        # Trigger state update
        _ = sensor.native_value
        attrs = sensor.extra_state_attributes
        assert attrs is not None
        assert "network_link_address" in attrs
        assert attrs["network_link_address"] == "00:11:22:33:44:55"


class TestHomelyEnergySensor:
    """Test Homely energy sensor."""

    def test_init_delivered(self, mock_device, mock_coordinator_basic):
        """Test energy sensor initialization for delivered."""
        sensor = HomelyEnergySensor(
            mock_coordinator_basic,
            TEST_LOCATION_ID,
            mock_device,
            MeteringStateName.SUMMATION_DELIVERED,
        )
        assert sensor.has_entity_name is True
        assert sensor._attr_unique_id == f"{mock_device.id}_energy_delivered"
        assert sensor._attr_translation_key == "energy_delivered"
        assert sensor._attr_device_class == SensorDeviceClass.ENERGY
        assert sensor._attr_state_class == SensorStateClass.TOTAL_INCREASING
        assert sensor._attr_native_unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR

    def test_init_received(self, mock_device, mock_coordinator_basic):
        """Test energy sensor initialization for received."""
        sensor = HomelyEnergySensor(
            mock_coordinator_basic,
            TEST_LOCATION_ID,
            mock_device,
            MeteringStateName.SUMMATION_RECEIVED,
        )
        assert sensor._attr_unique_id == f"{mock_device.id}_energy_received"
        assert sensor._attr_translation_key == "energy_received"

    def test_get_current_sensor_state_device_none(
        self, mock_device, mock_coordinator_basic
    ):
        """Test getting current sensor state when device is None."""
        sensor = HomelyEnergySensor(
            mock_coordinator_basic,
            TEST_LOCATION_ID,
            mock_device,
            MeteringStateName.SUMMATION_DELIVERED,
        )
        mock_get_none = MagicMock(return_value=None)
        sensor._get_current_device_state = mock_get_none
        assert sensor._get_current_sensor_state() is None
        mock_get_none.assert_called_once()

    def test_get_current_sensor_no_metering_feature(
        self, mock_device, mock_coordinator_basic
    ):
        """Test getting current sensor state with no metering feature."""
        sensor = HomelyEnergySensor(
            mock_coordinator_basic,
            TEST_LOCATION_ID,
            mock_device,
            MeteringStateName.SUMMATION_DELIVERED,
        )
        mock_device_no_metering = MagicMock()
        mock_device_no_metering.features.metering = None
        mock_get_no_metering = MagicMock(return_value=mock_device_no_metering)
        sensor._get_current_device_state = mock_get_no_metering
        assert sensor._get_current_sensor_state() is None
        mock_get_no_metering.assert_called_once()

    def test_get_current_sensor_state_valid_delivered(
        self, mock_device, mock_coordinator_basic
    ):
        """Test getting current sensor state with valid delivered state."""
        sensor = HomelyEnergySensor(
            mock_coordinator_basic,
            TEST_LOCATION_ID,
            mock_device,
            MeteringStateName.SUMMATION_DELIVERED,
        )
        last_updated = datetime.now(tz=UTC)
        state_value = 1234
        mock_state = create_mock_sensor_state(state_value, last_updated)
        mock_device_valid = MagicMock()
        mock_device_valid.features.metering.states.summation_delivered = mock_state
        mock_get_device_valid_state = MagicMock(return_value=mock_device_valid)
        sensor._get_current_device_state = mock_get_device_valid_state
        state = sensor._get_current_sensor_state()
        assert state is not None
        assert state.value == state_value
        assert state.last_updated == last_updated
        assert sensor.native_value == state_value

    def test_get_current_sensor_state_valid_received(
        self, mock_device, mock_coordinator_basic
    ):
        """Test getting current sensor state with valid received state."""
        sensor = HomelyEnergySensor(
            mock_coordinator_basic,
            TEST_LOCATION_ID,
            mock_device,
            MeteringStateName.SUMMATION_RECEIVED,
        )
        last_updated = datetime.now(tz=UTC)
        state_value = 5678
        mock_state = create_mock_sensor_state(state_value, last_updated)
        mock_device_valid = MagicMock()
        mock_device_valid.features.metering.states.summation_received = mock_state
        mock_get_device_valid_state = MagicMock(return_value=mock_device_valid)
        sensor._get_current_device_state = mock_get_device_valid_state
        state = sensor._get_current_sensor_state()
        assert state is not None
        assert state.value == state_value
        assert sensor.native_value == state_value


class TestHomelyEnergyDemandSensor:
    """Test Homely energy demand sensor."""

    def test_init(self, mock_device, mock_coordinator_basic):
        """Test energy demand sensor initialization."""
        sensor = HomelyEnergyDemandSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        assert sensor.has_entity_name is True
        assert sensor._attr_unique_id == f"{mock_device.id}_energy_demand"
        assert sensor._attr_name == "Energy Demand"
        assert sensor._attr_device_class == SensorDeviceClass.POWER
        assert sensor._attr_state_class == SensorStateClass.MEASUREMENT

    def test_get_current_sensor_state_device_none(
        self, mock_device, mock_coordinator_basic
    ):
        """Test getting current sensor state when device is None."""
        sensor = HomelyEnergyDemandSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        mock_get_none = MagicMock(return_value=None)
        sensor._get_current_device_state = mock_get_none
        assert sensor._get_current_sensor_state() is None
        mock_get_none.assert_called_once()

    def test_get_current_sensor_no_metering_feature(
        self, mock_device, mock_coordinator_basic
    ):
        """Test getting current sensor state with no metering feature."""
        sensor = HomelyEnergyDemandSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        mock_device_no_metering = MagicMock()
        mock_device_no_metering.features.metering = None
        mock_get_no_metering = MagicMock(return_value=mock_device_no_metering)
        sensor._get_current_device_state = mock_get_no_metering
        assert sensor._get_current_sensor_state() is None
        mock_get_no_metering.assert_called_once()

    def test_get_current_sensor_state_valid(self, mock_device, mock_coordinator_basic):
        """Test getting current sensor state with valid state."""
        sensor = HomelyEnergyDemandSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        last_updated = datetime.now(tz=UTC)
        state_value = 500
        mock_state = create_mock_sensor_state(state_value, last_updated)
        mock_device_valid = MagicMock()
        mock_device_valid.features.metering.states.demand = mock_state
        mock_get_device_valid_state = MagicMock(return_value=mock_device_valid)
        sensor._get_current_device_state = mock_get_device_valid_state
        state = sensor._get_current_sensor_state()
        assert state is not None
        assert state.value == state_value
        assert state.last_updated == last_updated
        assert sensor.native_value == state_value


class TestHomelyThermostatSensor:
    """Test Homely thermostat sensor."""

    def test_init(self, mock_device, mock_coordinator_basic):
        """Test thermostat sensor initialization."""
        sensor = HomelyThermostatSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        assert sensor.has_entity_name is True
        assert sensor._attr_unique_id == f"{mock_device.id}_thermostat"
        assert sensor._attr_translation_key == "thermostat"
        assert sensor._attr_device_class == SensorDeviceClass.TEMPERATURE
        assert sensor._attr_state_class == SensorStateClass.MEASUREMENT

    def test_get_current_sensor_state_device_none(
        self, mock_device, mock_coordinator_basic
    ):
        """Test getting current sensor state when device is None."""
        sensor = HomelyThermostatSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        mock_get_none = MagicMock(return_value=None)
        sensor._get_current_device_state = mock_get_none
        assert sensor._get_current_sensor_state() is None
        mock_get_none.assert_called_once()

    def test_get_current_sensor_no_thermostat_feature(
        self, mock_device, mock_coordinator_basic
    ):
        """Test getting current sensor state with no thermostat feature."""
        sensor = HomelyThermostatSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        mock_device_no_thermo = MagicMock()
        mock_device_no_thermo.features.thermostat = None
        mock_get_no_thermo = MagicMock(return_value=mock_device_no_thermo)
        sensor._get_current_device_state = mock_get_no_thermo
        assert sensor._get_current_sensor_state() is None
        mock_get_no_thermo.assert_called_once()

    def test_get_current_sensor_state_valid_local_temperature(
        self, mock_device, mock_coordinator_basic
    ):
        """Test getting current sensor state with valid local_temperature state."""
        sensor = HomelyThermostatSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        last_updated = datetime.now(tz=UTC)
        state_value = 21.5
        mock_state = create_mock_sensor_state(state_value, last_updated)
        mock_device_valid = MagicMock()
        mock_device_valid.features.thermostat.states.local_temperature = mock_state
        mock_get_device_valid_state = MagicMock(return_value=mock_device_valid)
        sensor._get_current_device_state = mock_get_device_valid_state
        state = sensor._get_current_sensor_state()
        assert state is not None
        assert state.value == state_value
        assert state.last_updated == last_updated
        assert sensor.native_value == state_value

    def test_get_current_sensor_state_fallback_temperature(
        self, mock_device, mock_coordinator_basic
    ):
        """Test getting current sensor state with fallback temperature state."""
        sensor = HomelyThermostatSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        last_updated = datetime.now(tz=UTC)
        state_value = 20.0
        mock_state = create_mock_sensor_state(state_value, last_updated)
        mock_device_valid = MagicMock()
        mock_device_valid.features.thermostat.states.local_temperature = None
        mock_device_valid.features.thermostat.states.temperature = mock_state
        mock_get_device_valid_state = MagicMock(return_value=mock_device_valid)
        sensor._get_current_device_state = mock_get_device_valid_state
        state = sensor._get_current_sensor_state()
        assert state is not None
        assert state.value == state_value
        assert sensor.native_value == state_value

    def test_extra_state_attributes(self, mock_device, mock_coordinator_basic):
        """Test extra state attributes."""
        sensor = HomelyThermostatSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        mock_temp_state = create_mock_sensor_state(21.0, datetime.now(tz=UTC))
        mock_setpoint_state = create_mock_sensor_state(22.0, datetime.now(tz=UTC))
        mock_device_valid = MagicMock()
        mock_device_valid.features.thermostat.states.local_temperature = mock_temp_state
        mock_device_valid.features.thermostat.states.model_dump = MagicMock(
            return_value={
                "local_temperature": mock_temp_state,
                "occupied_heating_setpoint": mock_setpoint_state,
            }
        )
        sensor._get_current_device_state = MagicMock(return_value=mock_device_valid)
        attrs = sensor.extra_state_attributes
        assert attrs is not None
        assert "occupied_heating_setpoint" in attrs
        assert attrs["occupied_heating_setpoint"] == 22.0
