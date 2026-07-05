"""Regression test: replay the exact raw WS frames from a real arm→trigger→breach→
disarm cycle (STAY profile, 2026-07-05) and assert each step maps to the correct HA
alarm state and fires the correct event-entity event.

Frames are copied verbatim (with tokens redacted at capture time, not here — these
frames carry no secrets) from ~/source/sniffs/homely_alarm_roles_redacted.json.
"""

from unittest.mock import MagicMock

from homeassistant.components.alarm_control_panel.const import AlarmControlPanelState

from custom_components.homely.alarm_control_panel import _ALARM_STATE_MAP
from custom_components.homely.event import HomelyAlarmEventEntity
from custom_components.homely.homely_api import HomelyHomeState, HomelyWebSocketClient

LOCATION_ID = "f32bf453-23f9-4986-9a0c-195a06c99961"

# Raw Socket.IO event frames, byte-for-byte as captured (ack-id digits included).
FRAME_ARM_STAY_PENDING = (
    '422197096["message",{"type":"alarm-state-changed","eventData":'
    '{"locationId":"f32bf453-23f9-4986-9a0c-195a06c99961","state":"ARM_STAY_PENDING",'
    '"timestamp":"2026-07-05T16:53:52.021Z","partnerCode":1275}}]'
)
FRAME_ARMED_STAY = (
    '422197122["message",{"type":"alarm-state-changed","eventData":'
    '{"locationId":"f32bf453-23f9-4986-9a0c-195a06c99961","state":"ARMED_STAY",'
    '"timestamp":"2026-07-05T16:54:12.039Z","userId":"5fcb044d-2f2b-43fb-9ca3-8b3869342be7",'
    '"userName":"Bjarte Test Lode","eventId":2701,"partnerCode":1275}}]'
)
FRAME_BREACHED = (
    '422197257["message",{"type":"alarm-state-changed","eventData":'
    '{"locationId":"f32bf453-23f9-4986-9a0c-195a06c99961","state":"BREACHED",'
    '"timestamp":"2026-07-05T16:55:16.766Z","userName":"","eventId":2705,'
    '"partnerCode":1275}}]'
)
FRAME_DISARMED = (
    '422197272["message",{"type":"alarm-state-changed","eventData":'
    '{"locationId":"f32bf453-23f9-4986-9a0c-195a06c99961","state":"DISARMED",'
    '"timestamp":"2026-07-05T16:55:21.480Z","userId":"e8ef1246-b8e5-4cae-ac01-6d49e84effc8",'
    '"userName":"Bjarte Fl\\u00f8 Lode","eventId":2708,'
    '"deviceId":"adee071e-3428-4808-bafd-9b9bd7353869","partnerCode":1275}}]'
)


def _client() -> HomelyWebSocketClient:
    return HomelyWebSocketClient(api=MagicMock(), location_id=LOCATION_ID)


def _initial_state() -> HomelyHomeState:
    return HomelyHomeState.model_validate({"location_id": LOCATION_ID, "devices": []})


class TestRealBreachSequenceReplay:
    def test_full_sequence_maps_to_expected_ha_states(self):
        client = _client()
        state = _initial_state()

        _, ev = client._parse_sio_packet(FRAME_ARM_STAY_PENDING)
        state = HomelyHomeState.from_ws_event(state, ev, ignore_unhandled_event_types=True)
        assert _ALARM_STATE_MAP[state.alarm_state] == AlarmControlPanelState.ARMING

        _, ev = client._parse_sio_packet(FRAME_ARMED_STAY)
        state = HomelyHomeState.from_ws_event(state, ev, ignore_unhandled_event_types=True)
        assert _ALARM_STATE_MAP[state.alarm_state] == AlarmControlPanelState.ARMED_HOME

        _, ev = client._parse_sio_packet(FRAME_BREACHED)
        state = HomelyHomeState.from_ws_event(state, ev, ignore_unhandled_event_types=True)
        assert _ALARM_STATE_MAP[state.alarm_state] == AlarmControlPanelState.TRIGGERED
        assert state.last_alarm_event.event_id == 2705

        _, ev = client._parse_sio_packet(FRAME_DISARMED)
        state = HomelyHomeState.from_ws_event(state, ev, ignore_unhandled_event_types=True)
        assert _ALARM_STATE_MAP[state.alarm_state] == AlarmControlPanelState.DISARMED
        assert state.last_alarm_event.user_name == "Bjarte Flø Lode"

    def test_breach_and_disarm_fire_expected_action_events(self):
        client = _client()
        state = _initial_state()
        for frame in (FRAME_ARM_STAY_PENDING, FRAME_ARMED_STAY):
            _, ev = client._parse_sio_packet(frame)
            state = HomelyHomeState.from_ws_event(state, ev, ignore_unhandled_event_types=True)

        coordinator = MagicMock()
        coordinator.get_home_state = MagicMock(return_value=state)
        entity = HomelyAlarmEventEntity(coordinator, LOCATION_ID, state)
        entity._trigger_event = MagicMock()
        entity.async_write_ha_state = MagicMock()

        _, ev = client._parse_sio_packet(FRAME_BREACHED)
        state = HomelyHomeState.from_ws_event(state, ev, ignore_unhandled_event_types=True)
        coordinator.get_home_state.return_value = state
        entity._handle_coordinator_update()
        assert entity._trigger_event.call_args[0][0] == "triggered"

        _, ev = client._parse_sio_packet(FRAME_DISARMED)
        state = HomelyHomeState.from_ws_event(state, ev, ignore_unhandled_event_types=True)
        coordinator.get_home_state.return_value = state
        entity._handle_coordinator_update()
        assert entity._trigger_event.call_args[0][0] == "disarmed"
