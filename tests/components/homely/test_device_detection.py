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
from custom_components.homely.models import AlarmReaction, Device


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


class TestDeviceModelVendorAndType:
    """API-reported manufacturer/connectivity type (2026-07 sniff)."""

    def test_parses_model_vendor_and_device_type(self):
        # Real device from the sniff: "Vaskeromsdør" entry sensor.
        dev = Device.model_validate(
            {
                "id": "067721f1-f16a-41da-930b-05ae26eee802",
                "name": "Vaskeromsdør",
                "online": True,
                "modelId": "9b765375-e3f4-4627-b73c-b4143ce86c2c",
                "modelName": "Alarm Entry Sensor 2",
                "modelVendor": "frient A/S",
                "deviceType": "ZIGBEE",
                "features": {"alarm": {"states": {"alarm": {"value": False}}}},
            }
        )
        assert dev.model_vendor == "frient A/S"
        assert dev.device_type == "ZIGBEE"

    def test_missing_model_vendor_is_none(self):
        dev = Device.model_validate(
            {
                "id": "067721f1-f16a-41da-930b-05ae26eee802",
                "online": True,
                "modelId": "9b765375-e3f4-4627-b73c-b4143ce86c2c",
                "features": {"alarm": {"states": {"alarm": {"value": False}}}},
            }
        )
        assert dev.model_vendor is None
        assert dev.device_type is None


class TestAlarmProfileAndReactionFields:
    """Per-mode alarm-profile membership + reaction type (2026-07 sniff).

    FOLLOWER is a real reaction value confirmed live via
    PATCH /devices/{id}/alarm-reaction {"alarmReactionStay": "FOLLOWER"}.
    """

    def test_parses_profile_and_reaction_fields(self):
        dev = Device.model_validate(
            {
                "id": "067721f1-f16a-41da-930b-05ae26eee802",
                "name": "Vaskeromsdør",
                "online": True,
                "modelId": "9b765375-e3f4-4627-b73c-b4143ce86c2c",
                "alarmProfileAway": True,
                "alarmProfileNight": True,
                "alarmProfileStay": True,
                "alarmReactionAway": "ENTRY_EXIT",
                "alarmReactionNight": "NORMAL",
                "alarmReactionStay": "ENTRY_EXIT",
                "features": {"alarm": {"states": {"alarm": {"value": False}}}},
            }
        )
        assert dev.alarm_profile_away is True
        assert dev.alarm_profile_night is True
        assert dev.alarm_profile_stay is True
        assert dev.alarm_reaction_away is AlarmReaction.ENTRY_EXIT
        assert dev.alarm_reaction_night is AlarmReaction.NORMAL
        assert dev.alarm_reaction_stay is AlarmReaction.ENTRY_EXIT

    def test_follower_reaction_value_parses(self):
        dev = Device.model_validate(
            {
                "id": "067721f1-f16a-41da-930b-05ae26eee802",
                "online": True,
                "modelId": "9b765375-e3f4-4627-b73c-b4143ce86c2c",
                "alarmReactionStay": "FOLLOWER",
                "features": {"alarm": {"states": {"alarm": {"value": False}}}},
            }
        )
        assert dev.alarm_reaction_stay is AlarmReaction.FOLLOWER

    def test_unknown_reaction_value_does_not_raise(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            dev = Device.model_validate(
                {
                    "id": "067721f1-f16a-41da-930b-05ae26eee802",
                    "online": True,
                    "modelId": "9b765375-e3f4-4627-b73c-b4143ce86c2c",
                    "alarmReactionAway": "SOMETHING_NEW",
                    "features": {"alarm": {"states": {"alarm": {"value": False}}}},
                }
            )
        assert dev.alarm_reaction_away is AlarmReaction.UNKNOWN
        assert "SOMETHING_NEW" in caplog.text
