"""Tests for the arm/disarm event entity (who/when from the WS stream)."""

from unittest.mock import MagicMock

from custom_components.homely.homely_api import HomelyHomeState
from custom_components.homely.models import AlarmState, WsAlarmChangeData

LOCATION_ID = "f32bf453-23f9-4986-9a0c-195a06c99961"


def _home_state(last_event=None):
    home = HomelyHomeState.model_validate(
        {"location_id": LOCATION_ID, "devices": []}
    )
    if last_event is not None:
        home.last_alarm_event = last_event
    return home


def _alarm_event(state, user_name="Bjarte Flø Lode", event_id=2417):
    return WsAlarmChangeData.model_validate(
        {
            "locationId": LOCATION_ID,
            "state": state,
            "userName": user_name,
            "userId": "5fcb044d-2f2b-43fb-9ca3-8b3869342be7",
            "timestamp": "2026-06-16T04:17:45.729Z",
            "eventId": event_id,
        }
    )


def _coordinator(home):
    c = MagicMock()
    c.get_home_state = MagicMock(return_value=home)
    return c


class TestHomeStateStoresAlarmEvent:
    def test_process_alarm_update_stores_event(self):
        home = _home_state()
        ev = _alarm_event("DISARMED")
        home._process_ws_alarm_state_update(ev)
        assert home.alarm_state == AlarmState.DISARMED
        assert home.last_alarm_event is ev
        assert home.last_alarm_event.user_name == "Bjarte Flø Lode"


class TestAlarmEventEntity:
    def _entity(self, home):
        """Create the entity against an (initially event-less) home state."""
        from custom_components.homely.event import HomelyAlarmEventEntity

        ent = HomelyAlarmEventEntity(_coordinator(home), LOCATION_ID, home)
        ent._trigger_event = MagicMock()
        ent.async_write_ha_state = MagicMock()
        return ent

    def test_fires_disarmed_event_with_user(self):
        home = _home_state()
        ent = self._entity(home)
        home.last_alarm_event = _alarm_event("DISARMED", "Bjarte Flø Lode")
        ent._handle_coordinator_update()
        ent._trigger_event.assert_called_once()
        event_type, attrs = ent._trigger_event.call_args[0]
        assert event_type == "disarmed"
        assert attrs["user_name"] == "Bjarte Flø Lode"

    def test_does_not_refire_same_event(self):
        home = _home_state()
        ent = self._entity(home)
        home.last_alarm_event = _alarm_event("DISARMED")
        ent._handle_coordinator_update()
        ent._handle_coordinator_update()
        ent._trigger_event.assert_called_once()

    def test_pending_state_does_not_fire(self):
        home = _home_state()
        ent = self._entity(home)
        home.last_alarm_event = _alarm_event("ARM_STAY_PENDING", user_name=None)
        ent._handle_coordinator_update()
        ent._trigger_event.assert_not_called()

    def test_armed_stay_maps_to_armed_home(self):
        home = _home_state()
        ent = self._entity(home)
        home.last_alarm_event = _alarm_event("ARMED_STAY")
        ent._handle_coordinator_update()
        assert ent._trigger_event.call_args[0][0] == "armed_home"

    def test_does_not_replay_event_present_at_startup(self):
        # An event already present when the entity is created must not replay.
        home = _home_state(_alarm_event("DISARMED"))
        ent = self._entity(home)
        ent._handle_coordinator_update()
        ent._trigger_event.assert_not_called()
