"""Test the Homely binary sensor entities."""

from collections.abc import Callable
from datetime import UTC, datetime
from unittest.mock import MagicMock, PropertyMock, patch

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
)
from homeassistant.const import EntityCategory

from custom_components.homely.binary_sensor import (
    HomelyBatteryDefectSensor,
    HomelyBatteryLowSensor,
    HomelyBinarySensorBase,
    HomelyEnergyCheckSensor,
    HomelyEntrySensor,
    HomelyFloodSensor,
    HomelyMotionSensor,
    HomelySmokeSensor,
    HomelyTamperSensor,
    async_setup_entry,
    create_binary_entities_from_device,
    pick_alarm_classes,
)
from custom_components.homely.const import (
    DOMAIN,
    HomelyEntityIcons,
    HomelyEntityIdSuffix,
)

from .conftest import (
    TEST_LOCATION_ID,
    create_mock_device,
    create_mock_entry_sensor_device,
    create_mock_flood_sensor_device,
    create_mock_motion_device,
    create_mock_sensor_state,
    create_mock_smoke_sensor_device,
    create_mock_tamper_sensor_device,
)


class TestHomelyBinarySensorSetup:
    """Test setup of Homely binary sensors."""

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

        # Create mock device with alarm feature
        mock_device = create_mock_motion_device()
        mock_device.features.battery = None
        mock_device.features.metering = None

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
        # Should have at least one binary sensor
        assert len(entities) >= 1


class TestPickAlarmClasses:
    """Test pick_alarm_classes function."""

    def test_pick_motion_sensor(self):
        """Test picking motion sensor class."""
        mock_device = create_mock_motion_device()
        classes = pick_alarm_classes(mock_device)
        assert classes is not None
        assert HomelyMotionSensor in classes

    def test_pick_entry_sensor(self):
        """Test picking entry sensor class."""
        mock_device = create_mock_entry_sensor_device()
        classes = pick_alarm_classes(mock_device)
        assert classes is not None
        assert HomelyEntrySensor in classes

    def test_pick_smoke_sensor(self):
        """Test picking smoke sensor class."""
        mock_device = create_mock_smoke_sensor_device()
        classes = pick_alarm_classes(mock_device)
        assert classes is not None
        assert HomelySmokeSensor in classes

    def test_pick_flood_sensor(self):
        """Test picking flood sensor class."""
        mock_device = create_mock_flood_sensor_device()
        classes = pick_alarm_classes(mock_device)
        assert classes is not None
        assert HomelyFloodSensor in classes

    def test_pick_tamper_sensor(self):
        """Test picking tamper sensor class."""
        mock_device = create_mock_tamper_sensor_device()
        classes = pick_alarm_classes(mock_device)
        assert classes is not None
        assert HomelyTamperSensor in classes

    def test_pick_no_alarm_feature(self):
        """Test picking with no alarm feature."""
        mock_device = create_mock_device()
        mock_device.features.alarm = None
        classes = pick_alarm_classes(mock_device)
        assert classes is None

    def test_pick_multiple_alarm_types(self):
        """Test picking multiple alarm sensor types."""
        mock_device = create_mock_device()
        mock_device.model_name = "Motion Sensor Model"
        mock_device.features.alarm = MagicMock()
        mock_device.features.alarm.states.alarm = MagicMock()
        mock_device.features.alarm.states.fire = MagicMock()
        mock_device.features.alarm.states.flood = MagicMock()
        mock_device.features.alarm.states.tamper = MagicMock()

        classes = pick_alarm_classes(mock_device)
        assert classes is not None
        assert len(classes) == 4
        assert HomelyMotionSensor in classes
        assert HomelySmokeSensor in classes
        assert HomelyFloodSensor in classes
        assert HomelyTamperSensor in classes


class TestCreateBinaryEntitiesFromDevice:
    """Test create_binary_entities_from_device function."""

    def test_create_motion_sensor(self, mock_coordinator_basic):
        """Test creating motion sensor."""
        mock_device = create_mock_motion_device()
        mock_device.features.battery = None
        mock_device.features.metering = None

        entities = create_binary_entities_from_device(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )

        assert len(entities) >= 1
        assert any(isinstance(e, HomelyMotionSensor) for e in entities)

    def test_create_battery_sensors(self, mock_coordinator_basic):
        """Test creating battery sensors."""
        mock_device = create_mock_device()
        mock_device.features.alarm = None
        mock_device.features.battery = MagicMock()
        mock_device.features.battery.states.low = MagicMock()
        mock_device.features.battery.states.defect = MagicMock()
        mock_device.features.metering = None

        entities = create_binary_entities_from_device(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )

        assert len(entities) == 2
        assert any(isinstance(e, HomelyBatteryLowSensor) for e in entities)
        assert any(isinstance(e, HomelyBatteryDefectSensor) for e in entities)

    def test_create_energy_check_sensor(self, mock_coordinator_basic):
        """Test creating energy check sensor."""
        mock_device = create_mock_device()
        mock_device.features.alarm = None
        mock_device.features.battery = None
        mock_device.features.metering = MagicMock()
        mock_device.features.metering.states.check = MagicMock()

        entities = create_binary_entities_from_device(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )

        assert len(entities) == 1
        assert isinstance(entities[0], HomelyEnergyCheckSensor)

    def test_create_multiple_sensors(self, mock_coordinator_basic):
        """Test creating multiple sensors from one device."""
        mock_device = create_mock_motion_device()
        mock_device.features.battery = MagicMock()
        mock_device.features.battery.states.low = MagicMock()
        mock_device.features.battery.states.defect = None
        mock_device.features.metering = None

        entities = create_binary_entities_from_device(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )

        # Should have motion + battery sensors + tamper + fire + flood
        assert len(entities) >= 2
        assert any(isinstance(e, HomelyMotionSensor) for e in entities)
        assert any(isinstance(e, HomelyBatteryLowSensor) for e in entities)

    def test_create_no_sensors(self, mock_coordinator_basic):
        """Test creating no sensors when device has no features."""
        mock_device = create_mock_device()
        mock_device.features.alarm = None
        mock_device.features.battery = None
        mock_device.features.metering = None

        entities = create_binary_entities_from_device(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )

        assert len(entities) == 0


class TestHomelyBinarySensorBase:
    """Test Homely binary sensor base class."""

    def test_init(self, mock_device, mock_coordinator_basic):
        """Test sensor initialization."""
        HomelyBinarySensorBase(mock_coordinator_basic, TEST_LOCATION_ID, mock_device)

    def test_is_on_property(self, mock_device, mock_coordinator_basic):
        """Test is_on property."""
        sensor = HomelyBinarySensorBase(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        assert sensor.is_on is None
        state = create_mock_sensor_state(value=True)
        sensor._get_current_sensor_state = MagicMock(return_value=state)
        assert sensor.is_on is True
        sensor._get_current_sensor_state.assert_called_once()


class CommonAlarmEntitySensorTests:
    """Common tests for homely alarm entity based binary sensors."""

    def test_get_current_sensor_state_device_none(self, sensor):
        """Test getting current sensor state."""
        mock_get_none = MagicMock(return_value=None)
        sensor._get_current_device_state = mock_get_none
        assert sensor._get_current_sensor_state() is None
        mock_get_none.assert_called_once()

    def test_get_current_sensor_no_alarm_feature(self, sensor):
        """Test getting current sensor state with no alarm feature."""
        mock_device_no_alarm = MagicMock()  # spec=Device)
        mock_device_no_alarm.features.alarm = None
        mock_get_no_alarm = MagicMock(return_value=mock_device_no_alarm)
        sensor._get_current_device_state = mock_get_no_alarm
        assert sensor._get_current_sensor_state() is None
        mock_get_no_alarm.assert_called_once()

    def test_get_current_sensor_state_no_sensor_state(self, sensor, state_name: str):
        """Test getting current sensor state with no alarm states."""
        mock_device_no_alarm_state = MagicMock()  # spec=Device)
        setattr(mock_device_no_alarm_state.features.alarm.states, state_name, None)
        mock_get_device_no_alarm_state = MagicMock(
            return_value=mock_device_no_alarm_state
        )
        sensor._get_current_device_state = mock_get_device_no_alarm_state
        assert sensor._get_current_sensor_state() is None
        mock_get_device_no_alarm_state.assert_called_once()

    def test_get_current_sensor_state_valid(
        self, sensor, create_mock_device: Callable[[bool, datetime], MagicMock]
    ):
        """Test getting current sensor state with valid state."""
        last_updated = datetime.now(tz=UTC)
        state_value = True
        mock_device = create_mock_device(state_value, last_updated)
        mock_get_device_valid_state = MagicMock(return_value=mock_device)
        sensor._get_current_device_state = mock_get_device_valid_state
        state = sensor._get_current_sensor_state()
        assert state is not None
        assert state.value is state_value
        assert state.last_updated == last_updated
        mock_get_device_valid_state.assert_called_once()
        assert sensor.is_on is state_value


class TestHomelyMotionSensor(CommonAlarmEntitySensorTests):
    """Test Homely motion sensor."""

    def test_init(self, mock_device, mock_coordinator_basic):
        """Test motion sensor initialization."""
        sensor = HomelyMotionSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        assert sensor.device_class == BinarySensorDeviceClass.MOTION
        assert sensor.has_entity_name is True
        assert sensor._attr_unique_id == f"{mock_device.id}_motion"
        assert sensor._attr_translation_key == "motion"

    def test_get_current_sensor_state_device_none(self, motion_sensor_test_entity):
        """Test getting current sensor state."""
        super().test_get_current_sensor_state_device_none(motion_sensor_test_entity)

    def test_get_current_sensor_no_alarm_feature(self, motion_sensor_test_entity):
        """Test getting current sensor state with no alarm feature."""
        super().test_get_current_sensor_no_alarm_feature(motion_sensor_test_entity)

    def test_get_current_sensor_state_no_sensor_state(self, motion_sensor_test_entity):
        """Test getting current sensor state with no alarm states."""
        super().test_get_current_sensor_state_no_sensor_state(
            motion_sensor_test_entity, "alarm"
        )

    def test_get_current_sensor_state_valid(self, motion_sensor_test_entity):
        """Test getting current sensor state with valid state."""
        super().test_get_current_sensor_state_valid(
            motion_sensor_test_entity, create_mock_motion_device
        )


class TestHomelyEntrySensor(CommonAlarmEntitySensorTests):
    """Test Homely entry sensor."""

    def test_init(self, mock_device, mock_coordinator_basic):
        """Test motion sensor initialization."""
        sensor = HomelyEntrySensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        assert sensor.device_class == BinarySensorDeviceClass.OPENING
        assert sensor.has_entity_name is True
        assert sensor._attr_unique_id == f"{mock_device.id}_opening"
        assert sensor._attr_translation_key == "opening"

    def test_get_current_sensor_state_device_none(self, entry_sensor_test_entity):
        """Test getting current sensor state."""
        super().test_get_current_sensor_state_device_none(entry_sensor_test_entity)

    def test_get_current_sensor_no_alarm_feature(self, entry_sensor_test_entity):
        """Test getting current sensor state with no alarm feature."""
        super().test_get_current_sensor_no_alarm_feature(entry_sensor_test_entity)

    def test_get_current_sensor_state_no_sensor_state(self, entry_sensor_test_entity):
        """Test getting current sensor state with no alarm states."""
        super().test_get_current_sensor_state_no_sensor_state(
            entry_sensor_test_entity, "alarm"
        )

    def test_get_current_sensor_state_valid(self, entry_sensor_test_entity):
        """Test getting current sensor state with valid state."""
        super().test_get_current_sensor_state_valid(
            entry_sensor_test_entity, create_mock_entry_sensor_device
        )


class TestHomelySmokeSensor(CommonAlarmEntitySensorTests):
    """Test Homely smoke sensor."""

    def test_init(self, mock_device, mock_coordinator_basic):
        """Test smoke sensor initialization."""
        sensor = HomelySmokeSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        assert sensor.device_class == BinarySensorDeviceClass.SMOKE
        assert sensor.has_entity_name is True
        assert sensor._attr_unique_id == f"{mock_device.id}_smoke"
        assert sensor._attr_translation_key == "smoke"

    def test_get_current_sensor_state_device_none(self, smoke_sensor_test_entity):
        """Test getting current sensor state."""
        super().test_get_current_sensor_state_device_none(smoke_sensor_test_entity)

    def test_get_current_sensor_no_alarm_feature(self, smoke_sensor_test_entity):
        """Test getting current sensor state with no alarm feature."""
        super().test_get_current_sensor_no_alarm_feature(smoke_sensor_test_entity)

    def test_get_current_sensor_state_no_sensor_state(self, smoke_sensor_test_entity):
        """Test getting current sensor state with no alarm states."""
        super().test_get_current_sensor_state_no_sensor_state(
            smoke_sensor_test_entity, "fire"
        )

    def test_get_current_sensor_state_valid(self, smoke_sensor_test_entity):
        """Test getting current sensor state with valid state."""
        super().test_get_current_sensor_state_valid(
            smoke_sensor_test_entity, create_mock_smoke_sensor_device
        )


class TestHomelyTamperSensor(CommonAlarmEntitySensorTests):
    """Test Homely tamper sensor."""

    def test_init(self, mock_device, mock_coordinator_basic):
        """Test tamper sensor initialization."""
        sensor = HomelyTamperSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        assert sensor.device_class == BinarySensorDeviceClass.TAMPER
        assert sensor.has_entity_name is True
        assert sensor._attr_unique_id == f"{mock_device.id}_tamper"
        assert sensor._attr_translation_key == "tamper"

    def test_get_current_sensor_state_device_none(self, tamper_sensor_test_entity):
        """Test getting current sensor state."""
        super().test_get_current_sensor_state_device_none(tamper_sensor_test_entity)

    def test_get_current_sensor_no_alarm_feature(self, tamper_sensor_test_entity):
        """Test getting current sensor state with no alarm feature."""
        super().test_get_current_sensor_no_alarm_feature(tamper_sensor_test_entity)

    def test_get_current_sensor_state_no_sensor_state(self, tamper_sensor_test_entity):
        """Test getting current sensor state with no alarm states."""
        super().test_get_current_sensor_state_no_sensor_state(
            tamper_sensor_test_entity, "tamper"
        )

    def test_get_current_sensor_state_valid(self, tamper_sensor_test_entity):
        """Test getting current sensor state with valid state."""
        super().test_get_current_sensor_state_valid(
            tamper_sensor_test_entity, create_mock_tamper_sensor_device
        )


class TestHomelyFloodSensor(CommonAlarmEntitySensorTests):
    """Test Homely flood sensor."""

    def test_init(self, mock_device, mock_coordinator_basic):
        """Test flood sensor initialization."""
        sensor = HomelyFloodSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        assert sensor.device_class == BinarySensorDeviceClass.MOISTURE
        assert sensor.has_entity_name is True
        assert sensor._attr_unique_id == f"{mock_device.id}_flood"
        assert sensor._attr_translation_key == "flood"

    def test_get_current_sensor_state_device_none(self, flood_sensor_test_entity):
        """Test getting current sensor state."""
        super().test_get_current_sensor_state_device_none(flood_sensor_test_entity)

    def test_get_current_sensor_no_alarm_feature(self, flood_sensor_test_entity):
        """Test getting current sensor state with no alarm feature."""
        super().test_get_current_sensor_no_alarm_feature(flood_sensor_test_entity)

    def test_get_current_sensor_state_no_sensor_state(self, flood_sensor_test_entity):
        """Test getting current sensor state with no alarm states."""
        super().test_get_current_sensor_state_no_sensor_state(
            flood_sensor_test_entity, "flood"
        )

    def test_get_current_sensor_state_valid(self, flood_sensor_test_entity):
        """Test getting current sensor state with valid state."""
        super().test_get_current_sensor_state_valid(
            flood_sensor_test_entity, create_mock_flood_sensor_device
        )


class TestHomelyBatteryLowSensor:
    """Test Homely battery low sensor."""

    def test_init(self, mock_device, mock_coordinator_basic):
        """Test battery low sensor initialization."""
        sensor = HomelyBatteryLowSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        assert sensor.device_class == BinarySensorDeviceClass.BATTERY
        assert sensor._attr_entity_category == EntityCategory.DIAGNOSTIC
        assert sensor.has_entity_name is True
        assert sensor._attr_unique_id == f"{mock_device.id}_battery_low_alarm"
        assert sensor._attr_translation_key == "battery_low"
        assert sensor.voltage is None

    def test_get_current_sensor_state_device_none(self, battery_low_sensor_test_entity):
        """Test getting current sensor state."""
        sensor = battery_low_sensor_test_entity
        mock_get_none = MagicMock(return_value=None)
        sensor._get_current_device_state = mock_get_none
        assert sensor._get_current_sensor_state() is None
        mock_get_none.assert_called_once()

    def test_get_current_sensor_no_battery_feature(
        self, battery_low_sensor_test_entity
    ):
        """Test getting current sensor state with no battery feature."""
        sensor = battery_low_sensor_test_entity
        mock_device_no_battery = MagicMock()
        mock_device_no_battery.features.battery = None
        mock_get_no_battery = MagicMock(return_value=mock_device_no_battery)
        sensor._get_current_device_state = mock_get_no_battery
        assert sensor._get_current_sensor_state() is None
        mock_get_no_battery.assert_called_once()

    def test_get_current_sensor_state_no_sensor_state(
        self, battery_low_sensor_test_entity
    ):
        """Test getting current sensor state with no alarm states."""
        sensor = battery_low_sensor_test_entity
        mock_device_no_low_state = MagicMock()
        mock_device_no_low_state.features.battery.states.low = None
        mock_get_device_no_low_state = MagicMock(return_value=mock_device_no_low_state)
        sensor._get_current_device_state = mock_get_device_no_low_state
        assert sensor._get_current_sensor_state() is None
        mock_get_device_no_low_state.assert_called_once()

    def test_get_current_sensor_state_valid(self, battery_low_sensor_test_entity):
        """Test getting current sensor state with valid state."""
        sensor = battery_low_sensor_test_entity
        last_updated = datetime.now(tz=UTC)
        state_value = True
        mock_state = create_mock_sensor_state(state_value, last_updated)
        mock_device = MagicMock()
        mock_device.features.battery.states.low = mock_state
        mock_device.features.battery.states.voltage = None
        mock_get_device_valid_state = MagicMock(return_value=mock_device)
        sensor._get_current_device_state = mock_get_device_valid_state
        state = sensor._get_current_sensor_state()
        assert state is not None
        assert state.value is state_value
        assert state.last_updated == last_updated
        mock_get_device_valid_state.assert_called_once()
        assert sensor.is_on is state_value
        assert sensor.voltage is None

        mock_device.features.battery.states.voltage = MagicMock()
        mock_device.features.battery.states.voltage.value = 2.5
        assert sensor.is_on is state_value
        assert sensor.voltage == 2.5

    def test_extra_attributes(self, battery_low_sensor_test_entity):
        """Test extra state attributes."""
        sensor = battery_low_sensor_test_entity
        assert sensor.extra_state_attributes is not None
        sensor.voltage = 3.0
        attrs = sensor.extra_state_attributes
        assert attrs is not None
        assert "voltage" in attrs
        assert attrs["voltage"] == 3.0

    def test_icon_property(self, battery_low_sensor_test_entity):
        """Test icon property."""
        sensor = battery_low_sensor_test_entity
        mock_is_on = PropertyMock(return_value=True)
        with patch.object(HomelyBatteryLowSensor, "is_on", new=mock_is_on):
            assert sensor.icon == HomelyEntityIcons.BATTERY_LOW
            mock_is_on.assert_called_once()
        mock_is_on = PropertyMock(return_value=False)
        with patch.object(HomelyBatteryLowSensor, "is_on", new=mock_is_on):
            assert sensor.icon == HomelyEntityIcons.BATTERY_NOT_LOW
            mock_is_on.assert_called_once()


class TestHomelyBatteryDefectSensor:
    """Test Homely battery defect sensor."""

    def test_init(self, mock_device, mock_coordinator_basic):
        """Test battery defect sensor initialization."""
        sensor = HomelyBatteryDefectSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        assert sensor.device_class == BinarySensorDeviceClass.PROBLEM
        assert sensor._attr_entity_category == EntityCategory.DIAGNOSTIC
        assert sensor.has_entity_name is True
        assert (
            sensor._attr_unique_id
            == f"{mock_device.id}_{HomelyEntityIdSuffix.BATTERY_DEFECT}"
        )
        assert sensor._attr_translation_key == HomelyEntityIdSuffix.BATTERY_DEFECT

    def test_get_current_sensor_state_device_none(
        self, battery_defect_sensor_test_entity
    ):
        """Test getting current sensor state."""
        sensor = battery_defect_sensor_test_entity
        mock_get_none = MagicMock(return_value=None)
        sensor._get_current_device_state = mock_get_none
        assert sensor._get_current_sensor_state() is None
        mock_get_none.assert_called_once()

    def test_get_current_sensor_no_battery_feature(
        self, battery_defect_sensor_test_entity
    ):
        """Test getting current sensor state with no battery feature."""
        sensor = battery_defect_sensor_test_entity
        mock_device_no_battery = MagicMock()
        mock_device_no_battery.features.battery = None
        mock_get_no_battery = MagicMock(return_value=mock_device_no_battery)
        sensor._get_current_device_state = mock_get_no_battery
        assert sensor._get_current_sensor_state() is None
        mock_get_no_battery.assert_called_once()

    def test_get_current_sensor_state_no_sensor_state(
        self, battery_defect_sensor_test_entity
    ):
        """Test getting current sensor state with no valid sensor state."""
        sensor = battery_defect_sensor_test_entity
        mock_device_no_defect_state = MagicMock()
        mock_device_no_defect_state.features.battery.states.defect = None
        mock_get_device_no_defect_state = MagicMock(
            return_value=mock_device_no_defect_state
        )
        sensor._get_current_device_state = mock_get_device_no_defect_state
        assert sensor._get_current_sensor_state() is None
        mock_get_device_no_defect_state.assert_called_once()

    def test_get_current_sensor_state_valid(self, battery_defect_sensor_test_entity):
        """Test getting current sensor state with valid state."""
        sensor = battery_defect_sensor_test_entity
        last_updated = datetime.now(tz=UTC)
        state_value = True
        mock_state = create_mock_sensor_state(state_value, last_updated)
        mock_device = MagicMock()
        mock_device.features.battery.states.defect = mock_state
        mock_get_device_valid_state = MagicMock(return_value=mock_device)
        sensor._get_current_device_state = mock_get_device_valid_state
        state = sensor._get_current_sensor_state()
        assert state is not None
        assert state.value is state_value
        assert state.last_updated == last_updated
        mock_get_device_valid_state.assert_called_once()
        assert sensor.is_on is state_value

    def test_icon_property(self, battery_defect_sensor_test_entity):
        """Test icon property."""
        sensor = battery_defect_sensor_test_entity
        mock_is_on = PropertyMock(return_value=True)
        with patch.object(HomelyBatteryDefectSensor, "is_on", new=mock_is_on):
            assert sensor.icon == HomelyEntityIcons.BATTERY_DEFECT
            mock_is_on.assert_called_once()
        mock_is_on = PropertyMock(return_value=False)
        with patch.object(HomelyBatteryDefectSensor, "is_on", new=mock_is_on):
            assert sensor.icon == HomelyEntityIcons.BATTERY_NOT_DEFECT
            mock_is_on.assert_called_once()


class TestHomelyEnergyCheckSensor:
    """Test Homely energy check sensor."""

    def test_init(self, mock_device, mock_coordinator_basic):
        """Test energy check sensor initialization."""
        sensor = HomelyEnergyCheckSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        assert sensor.device_class == BinarySensorDeviceClass.PROBLEM
        assert sensor.has_entity_name is True
        assert (
            sensor._attr_unique_id
            == f"{mock_device.id}_{HomelyEntityIdSuffix.ENERGY_CHECK}"
        )
        assert sensor._attr_translation_key == HomelyEntityIdSuffix.ENERGY_CHECK

    def test_get_current_sensor_state_device_none(
        self, energy_check_sensor_test_entity
    ):
        """Test getting current sensor state."""
        sensor = energy_check_sensor_test_entity
        mock_get_none = MagicMock(return_value=None)
        sensor._get_current_device_state = mock_get_none
        assert sensor._get_current_sensor_state() is None
        mock_get_none.assert_called_once()

    def test_get_current_sensor_no_metering_feature(
        self, energy_check_sensor_test_entity
    ):
        """Test getting current sensor state with no metering feature."""
        sensor = energy_check_sensor_test_entity
        mock_device_no_metering = MagicMock()
        mock_device_no_metering.features.metering = None
        mock_get_no_metering = MagicMock(return_value=mock_device_no_metering)
        sensor._get_current_device_state = mock_get_no_metering
        assert sensor._get_current_sensor_state() is None
        mock_get_no_metering.assert_called_once()

    def test_get_current_sensor_state_no_sensor_state(
        self, energy_check_sensor_test_entity
    ):
        """Test getting current sensor state with no valid sensor state."""
        sensor = energy_check_sensor_test_entity
        mock_device_no_metering_state = MagicMock()
        mock_device_no_metering_state.features.metering.states.check = None
        mock_get_device_no_metering_state = MagicMock(
            return_value=mock_device_no_metering_state
        )
        sensor._get_current_device_state = mock_get_device_no_metering_state
        assert sensor._get_current_sensor_state() is None
        mock_get_device_no_metering_state.assert_called_once()

    def test_get_current_sensor_state_valid(self, energy_check_sensor_test_entity):
        """Test getting current sensor state with valid state."""
        sensor = energy_check_sensor_test_entity
        last_updated = datetime.now(tz=UTC)
        state_value = True
        mock_state = create_mock_sensor_state(state_value, last_updated)
        mock_device = MagicMock()
        mock_device.features.metering.states.check = mock_state
        mock_get_device_valid_state = MagicMock(return_value=mock_device)
        sensor._get_current_device_state = mock_get_device_valid_state
        state = sensor._get_current_sensor_state()
        assert state is not None
        assert state.value is state_value
        assert state.last_updated == last_updated
        mock_get_device_valid_state.assert_called_once()
        assert sensor.is_on is state_value
