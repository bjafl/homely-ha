"""Tests for the per-device online/connectivity binary sensor.

Each Homely device reports `online`; expose it as a diagnostic connectivity
sensor so device drop-offs are visible in HA.
"""

from unittest.mock import MagicMock

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory

from .conftest import create_mock_device

LOCATION_ID = "f32bf453-23f9-4986-9a0c-195a06c99961"


def _coordinator(device):
    coordinator = MagicMock()
    coordinator.get_device_state = MagicMock(return_value=device)
    return coordinator


class TestDeviceOnlineSensor:
    def test_is_on_when_online(self):
        from custom_components.homely.binary_sensor import HomelyDeviceOnlineSensor

        device = create_mock_device(online=True)
        ent = HomelyDeviceOnlineSensor(_coordinator(device), LOCATION_ID, device)
        assert ent.is_on is True
        assert ent.device_class == BinarySensorDeviceClass.CONNECTIVITY
        assert ent.entity_category == EntityCategory.DIAGNOSTIC

    def test_is_off_when_offline(self):
        from custom_components.homely.binary_sensor import HomelyDeviceOnlineSensor

        device = create_mock_device(online=False)
        ent = HomelyDeviceOnlineSensor(_coordinator(device), LOCATION_ID, device)
        assert ent.is_on is False

    def test_registered_for_every_device(self):
        from custom_components.homely.binary_sensor import (
            HomelyDeviceOnlineSensor,
            create_binary_entities_from_device,
        )

        device = create_mock_device()
        device.features.alarm = None
        device.features.battery = None
        device.features.metering = None
        entities = create_binary_entities_from_device(
            MagicMock(), LOCATION_ID, device
        )
        assert any(isinstance(e, HomelyDeviceOnlineSensor) for e in entities)
