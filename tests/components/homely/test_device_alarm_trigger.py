"""Tests for per-device alarm trigger/restore WS events.

Grounded in real captured traffic (2026-07-05, BURGLARY on an entry sensor):
see ~/source/sniffs/homely_alarm_roles_redacted.json.
"""

from unittest.mock import MagicMock

import pytest

from custom_components.homely.exceptions import HomelyStateUpdateLocationMismatchError
from custom_components.homely.homely_api import HomelyHomeState
from custom_components.homely.models import WsDeviceAlarmData

LOCATION_ID = "f32bf453-23f9-4986-9a0c-195a06c99961"
DEVICE_ID = "8a70e463-5f3d-445f-9ab3-5fbd25318c0b"


def _home_state() -> HomelyHomeState:
    return HomelyHomeState.model_validate({"location_id": LOCATION_ID, "devices": []})


def _triggered(alarm_type="BURGLARY", device_id=DEVICE_ID, location_id=LOCATION_ID):
    return WsDeviceAlarmData.model_validate(
        {
            "type": alarm_type,
            "deviceId": device_id,
            "locationId": location_id,
            "eventTime": "2026-07-05T16:54:56.733Z",
        }
    )


def _restored(alarm_type="BURGLARY", device_id=DEVICE_ID, location_id=LOCATION_ID):
    # Real payload carries no eventTime on restore.
    return WsDeviceAlarmData.model_validate(
        {"type": alarm_type, "deviceId": device_id, "locationId": location_id}
    )


class TestHomeStateStoresDeviceAlarmEvents:
    def test_triggered_stores_event_and_bumps_seq(self):
        home = _home_state()
        home._process_ws_device_alarm_triggered(_triggered())
        assert home.last_device_alarm_triggered.alarm_type == "BURGLARY"
        assert str(home.last_device_alarm_triggered.device_id) == DEVICE_ID
        assert home.last_device_alarm_triggered_seq == 1

    def test_restored_stores_event_and_bumps_seq(self):
        home = _home_state()
        home._process_ws_device_alarm_restore(_restored())
        assert home.last_device_alarm_restored.alarm_type == "BURGLARY"
        assert home.last_device_alarm_restored_seq == 1

    def test_second_trigger_bumps_seq_again(self):
        home = _home_state()
        home._process_ws_device_alarm_triggered(_triggered())
        home._process_ws_device_alarm_triggered(_triggered())
        assert home.last_device_alarm_triggered_seq == 2

    def test_location_mismatch_raises(self):
        home = _home_state()
        wrong = _triggered(location_id="00000000-0000-0000-0000-000000000000")
        with pytest.raises(HomelyStateUpdateLocationMismatchError):
            home._process_ws_device_alarm_triggered(wrong)


def _coordinator(home):
    c = MagicMock()
    c.get_home_state = MagicMock(return_value=home)
    return c


class TestDeviceAlarmEventEntity:
    def _entity(self, home):
        from custom_components.homely.event import HomelyDeviceAlarmEventEntity

        device = MagicMock()
        device.id = DEVICE_ID
        ent = HomelyDeviceAlarmEventEntity(
            _coordinator(home), LOCATION_ID, device, home
        )
        ent._trigger_event = MagicMock()
        ent.async_write_ha_state = MagicMock()
        return ent

    def test_fires_triggered_for_matching_device(self):
        home = _home_state()
        ent = self._entity(home)
        home._process_ws_device_alarm_triggered(_triggered())
        ent._handle_coordinator_update()
        ent._trigger_event.assert_called_once()
        event_type, attrs = ent._trigger_event.call_args[0]
        assert event_type == "triggered"
        assert attrs["alarm_type"] == "BURGLARY"

    def test_ignores_trigger_for_other_device(self):
        home = _home_state()
        ent = self._entity(home)
        home._process_ws_device_alarm_triggered(
            _triggered(device_id="00000000-0000-0000-0000-000000000001")
        )
        ent._handle_coordinator_update()
        ent._trigger_event.assert_not_called()

    def test_fires_restored_after_triggered(self):
        home = _home_state()
        ent = self._entity(home)
        home._process_ws_device_alarm_triggered(_triggered())
        ent._handle_coordinator_update()
        home._process_ws_device_alarm_restore(_restored())
        ent._handle_coordinator_update()
        assert ent._trigger_event.call_args[0][0] == "restored"

    def test_does_not_replay_event_present_at_startup(self):
        home = _home_state()
        home._process_ws_device_alarm_triggered(_triggered())
        ent = self._entity(home)  # created AFTER the event already happened
        ent._handle_coordinator_update()
        ent._trigger_event.assert_not_called()
