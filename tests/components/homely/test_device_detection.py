"""Tests for structured motion/entry detection via isAlarmDevice + sensor type.

Replaces the fragile English modelName regex. From homely_sniffs.json:
  motion: isAlarmDevice=True, sensorsConnectedDeviceType=None
  entry:  isAlarmDevice=True, sensorsConnectedDeviceType=DOOR/ENTRY_EXIT_DOOR
"""

from custom_components.homely.binary_sensor import (
    HomelyEntrySensor,
    HomelyMotionSensor,
    pick_alarm_classes,
)
from custom_components.homely.models import Device


def _alarm_device(is_alarm_device=True, sct=None, model_name=""):
    return Device.model_validate(
        {
            "id": "60f2e6e8-e850-4881-be53-1a9dfadf2e70",
            "name": "Sensor",
            "online": True,
            "modelId": "9b765375-e3f4-4627-b73c-b4143ce86c2c",
            "modelName": model_name,
            "isAlarmDevice": is_alarm_device,
            "sensorsConnectedDeviceType": sct,
            "features": {"alarm": {"states": {"alarm": {"value": False}}}},
        }
    )


class TestDeviceModelFields:
    def test_parses_is_alarm_device_and_sensor_type(self):
        dev = _alarm_device(is_alarm_device=True, sct="DOOR")
        assert dev.is_alarm_device is True
        assert dev.sensors_connected_device_type == "DOOR"


class TestStructuredDetection:
    def test_motion_when_alarm_device_without_sensor_type(self):
        # No modelName hint — must still detect motion structurally.
        dev = _alarm_device(is_alarm_device=True, sct=None, model_name="")
        assert pick_alarm_classes(dev) == [HomelyMotionSensor]

    def test_entry_when_sensor_type_set(self):
        dev = _alarm_device(is_alarm_device=True, sct="ENTRY_EXIT_DOOR", model_name="")
        assert pick_alarm_classes(dev) == [HomelyEntrySensor]

    def test_non_alarm_device_falls_back_to_model_name_regex(self):
        # isAlarmDevice False/None -> regex fallback (backwards compatible).
        dev = _alarm_device(is_alarm_device=None, sct=None, model_name="PIR Motion")
        assert pick_alarm_classes(dev) == [HomelyMotionSensor]
