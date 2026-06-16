"""Tests for alarm state values, HA mappings, and tolerant WS parsing.

Grounded in captured app-API traffic (api.homely.no):
- Arming/exit-delay states: ARM_PENDING, ARM_NIGHT_PENDING, ARM_STAY_PENDING
- Armed states: ARMED_AWAY, ARMED_NIGHT, ARMED_STAY
- Entry-delay states (carried over from SDK API): ALARM_PENDING, ALARM_STAY_PENDING
"""

import logging

import pytest
from homeassistant.components.alarm_control_panel.const import AlarmControlPanelState

from custom_components.homely.alarm_control_panel import (
    _ALARM_STATE_MAP,
    HomelyAlarmControlPanel,
)
from custom_components.homely.models import AlarmState, WsAlarmChangeData

TEST_LOCATION_ID = "f32bf453-23f9-4986-9a0c-195a06c99961"
TS = "2026-06-16T04:17:24.397Z"


class TestAlarmStateValues:
    """The enum must contain the values the app-API actually sends."""

    def test_armed_stay_value_exists(self):
        # App-API sends ARMED_STAY (sniffed); the branch regressed to ARMED_PARTLY.
        assert AlarmState.ARMED_STAY.value == "ARMED_STAY"

    def test_arm_stay_pending_value_exists(self):
        # Sniffed over WebSocket when arming in stay/home mode.
        assert AlarmState.ARM_STAY_PENDING.value == "ARM_STAY_PENDING"

    def test_unmatched_value_maps_to_unknown_member(self, caplog):
        # A value matching no pattern must never raise — map to UNKNOWN and warn.
        with caplog.at_level(logging.WARNING):
            result = AlarmState("SOMETHING_ELSE")
        assert result is AlarmState.UNKNOWN
        assert "SOMETHING_ELSE" in caplog.text


class TestUnknownStateRegexFallback:
    """Unknown values are best-effort classified by pattern (logged), so a
    future Homely state still yields a sensible HA state instead of unknown."""

    @pytest.mark.parametrize(
        "raw, expected_ha",
        [
            # ARM*PENDING / ARMED*PENDING -> arming (exit delay)
            ("ARM_FUTURE_PENDING", AlarmControlPanelState.ARMING),
            ("ARMED_VACATION_PENDING", AlarmControlPanelState.ARMING),
            # ALARM*PENDING -> pending (entry delay) — checked before ARM*
            ("ALARM_FUTURE_PENDING", AlarmControlPanelState.PENDING),
            # ARMED (no pending) -> treat as armed
            ("ARMED_VACATION", AlarmControlPanelState.ARMED_AWAY),
        ],
    )
    def test_regex_fallback_yields_ha_state(self, raw, expected_ha, caplog):
        with caplog.at_level(logging.WARNING):
            state = AlarmState(raw)
        assert _ALARM_STATE_MAP[state] == expected_ha
        assert raw in caplog.text


class TestWsAlarmTolerantParsing:
    """Unknown alarm states over WS must not crash the event parse."""

    def test_unknown_ws_state_does_not_raise(self):
        data = WsAlarmChangeData.model_validate(
            {"locationId": TEST_LOCATION_ID, "state": "FUTURE_STATE", "timestamp": TS}
        )
        assert data.state is AlarmState.UNKNOWN

    def test_arm_stay_pending_ws_state_parses(self):
        data = WsAlarmChangeData.model_validate(
            {"locationId": TEST_LOCATION_ID, "state": "ARM_STAY_PENDING", "timestamp": TS}
        )
        assert data.state is AlarmState.ARM_STAY_PENDING


class TestAlarmControlPanelStateMap:
    """Homely state -> HA AlarmControlPanelState mapping."""

    @pytest.mark.parametrize(
        "homely_state, ha_state",
        [
            (AlarmState.ARMED_STAY, AlarmControlPanelState.ARMED_HOME),
            # Exit/arming delay -> ARMING
            (AlarmState.ARM_STAY_PENDING, AlarmControlPanelState.ARMING),
            # Entry delay -> PENDING (the "disarm now" window)
            (AlarmState.ALARM_PENDING, AlarmControlPanelState.PENDING),
            (AlarmState.ALARM_STAY_PENDING, AlarmControlPanelState.PENDING),
        ],
    )
    def test_state_map(self, homely_state, ha_state):
        assert _ALARM_STATE_MAP[homely_state] == ha_state


class TestArmHomeCommand:
    """arm_home must send the profile the app-API expects."""

    async def test_arm_home_sends_armed_stay(self):
        from unittest.mock import AsyncMock, MagicMock

        coordinator = MagicMock()
        coordinator.api.arm_alarm = AsyncMock()
        home_state = MagicMock()
        home_state.name = "Hjem"
        home_state.gateway_serial = "020000014000F13D"
        panel = HomelyAlarmControlPanel(coordinator, TEST_LOCATION_ID, home_state)

        await panel.async_alarm_arm_home()

        coordinator.api.arm_alarm.assert_awaited_once_with(
            TEST_LOCATION_ID, "ARMED_STAY"
        )
