"""Test the Homely base sensor functionality."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from custom_components.homely.base_sensor import HomelySensorBase
from custom_components.homely.const import DOMAIN

from .conftest import TEST_LOCATION_ID, create_mock_device


class TestHomelySensorBase:
    """Test the HomelySensorBase class."""

    def test_sensor_initialization(self, mock_device, mock_coordinator_basic):
        """Test sensor initialization."""

        sensor = HomelySensorBase(mock_coordinator_basic, TEST_LOCATION_ID, mock_device)

        assert sensor.coordinator == mock_coordinator_basic
        assert sensor.location_id == TEST_LOCATION_ID
        assert sensor.device_id == str(mock_device.id)
        assert sensor.device_name == mock_device.name
        assert sensor.last_updated is None
        assert sensor.device_location == mock_device.location
        assert sensor.device_model == mock_device.model_name
        assert sensor.device_model_id == str(mock_device.model_id)
        assert sensor.device_serial == mock_device.serial_number
        assert sensor.device_manufacturer == "Unknown"

    def test_extra_state_attributes(self, mock_device, mock_coordinator_basic):
        """Test extra state attributes."""
        sensor = HomelySensorBase(mock_coordinator_basic, TEST_LOCATION_ID, mock_device)
        extra_attrs = sensor.extra_state_attributes
        assert extra_attrs is not None
        assert extra_attrs.get("last_updated") is None
        dt_now = datetime.now(tz=UTC)
        sensor.last_updated = dt_now
        extra_attrs = sensor.extra_state_attributes
        assert extra_attrs is not None
        last_updated = extra_attrs.get("last_updated")
        assert last_updated is not None
        assert last_updated.isoformat() == dt_now.isoformat()

    def test_get_current_device_state(self, mock_device, mock_coordinator_basic):
        """Test getting current device state."""
        sensor = HomelySensorBase(mock_coordinator_basic, TEST_LOCATION_ID, mock_device)
        assert sensor._get_current_sensor_state() is None
        sensor.coordinator.get_device_state = MagicMock(return_value="test_state")
        assert sensor._get_current_device_state() == "test_state"
        sensor.coordinator.get_device_state.assert_called_once_with(
            sensor.device_id, sensor.location_id
        )

    def test_device_info_generation(self, mock_device, mock_coordinator_basic):
        """Test device info generation."""
        sensor = HomelySensorBase(mock_coordinator_basic, TEST_LOCATION_ID, mock_device)
        device_info = sensor.device_info

        assert device_info is not None
        assert device_info.get("identifiers") == {(DOMAIN, str(mock_device.id))}
        assert device_info.get("name") == mock_device.name
        assert device_info.get("manufacturer") == "Unknown"
        assert device_info.get("model") == mock_device.model_name
        assert device_info.get("serial_number") == mock_device.serial_number
        assert device_info.get("suggested_area") == mock_device.location
        assert device_info.get("via_device") == (DOMAIN, TEST_LOCATION_ID)
        assert device_info.get("model_id") == str(mock_device.model_id)

    def test_get_manufacturer(self, mock_coordinator_basic, mock_device):
        """Test manufacturer retrieval."""
        # Test serial match
        device = create_mock_device(serial_number="0015BC123456")  # frient pattern
        sensor = HomelySensorBase(mock_coordinator_basic, TEST_LOCATION_ID, device)
        assert sensor.device_manufacturer == "frient"

        # Test model name match
        device = create_mock_device(model_name="ELKO thermostat")
        sensor = HomelySensorBase(mock_coordinator_basic, TEST_LOCATION_ID, device)
        assert sensor.device_manufacturer == "ELKO"

        # Test unknown manufacturer
        sensor = HomelySensorBase(mock_coordinator_basic, TEST_LOCATION_ID, mock_device)
        assert sensor.device_manufacturer == "Unknown"

        # Test no serial or model name
        device = create_mock_device()
        device.serial_number = None
        device.model_name = None
        sensor = HomelySensorBase(mock_coordinator_basic, TEST_LOCATION_ID, device)
        assert sensor.device_manufacturer == "Unknown"
