"""Tests for gateway.exitEntrySettings — per-mode countdown/sound config.

Values match the real config captured 2026-07-05 via PATCH /gateways/{id}/exit-entry
(see ~/source/sniffs/homely_alarm_modes_redacted.json, API_GAP_ANALYSIS.md §2).
"""

from unittest.mock import MagicMock

from custom_components.homely.alarm_control_panel import HomelyAlarmControlPanel
from custom_components.homely.models import ExitEntrySettings, Gateway

EXIT_ENTRY_DATA = {
    "alarmProfileAway": {
        "entryTime": 30,
        "entrySoundTime": 25,
        "exitTime": 60,
        "exitSoundTime": 30,
        "squawkLevel": "MediumLevelSound",
    },
    "alarmProfileNight": {
        "entryTime": 40,
        "entrySoundTime": 30,
        "exitTime": 20,
        "exitSoundTime": 0,
        "squawkLevel": "LowLevelSound",
    },
    "alarmProfileStay": {
        "entryTime": 20,
        "entrySoundTime": 20,
        "exitTime": 20,
        "exitSoundTime": 5,
        "squawkLevel": "LowLevelSound",
    },
    "sirenLevelStayDelay": "LowLevelSound",
    "sirenLevelEntryExit": "HighLevelSound",
    "sirenLevelNightDelay": "LowLevelSound",
    "sirenLevelAlarm": "VeryHighLevelSound",
}

LOCATION_ID = "f32bf453-23f9-4986-9a0c-195a06c99961"


class TestExitEntrySettingsModel:
    def test_parses_all_three_profiles(self):
        settings = ExitEntrySettings.model_validate(EXIT_ENTRY_DATA)
        assert settings.alarm_profile_away.exit_time == 60
        assert settings.alarm_profile_night.entry_time == 40
        assert settings.alarm_profile_stay.entry_time == 20
        assert settings.siren_level_alarm == "VeryHighLevelSound"

    def test_gateway_carries_exit_entry_settings(self):
        gw = Gateway.model_validate(
            {
                "id": "eafa2c31-3eb4-41a3-90cf-19f498e7a2b7",
                "online": True,
                "exitEntrySettings": EXIT_ENTRY_DATA,
            }
        )
        assert gw.exit_entry_settings is not None
        assert gw.exit_entry_settings.alarm_profile_stay.exit_time == 20


class TestAlarmControlPanelExitEntryAttributes:
    def test_exposes_per_mode_countdown_attrs(self):
        gw = Gateway.model_validate(
            {
                "id": "eafa2c31-3eb4-41a3-90cf-19f498e7a2b7",
                "online": True,
                "exitEntrySettings": EXIT_ENTRY_DATA,
            }
        )
        home_state = MagicMock()
        home_state.gateway = gw
        home_state.name = "Hjem"
        home_state.gateway_serial = "020000014000F13D"
        coordinator = MagicMock()
        coordinator.get_home_state = MagicMock(return_value=home_state)

        panel = HomelyAlarmControlPanel(coordinator, LOCATION_ID, home_state)
        attrs = panel.extra_state_attributes

        assert attrs["away_exit_time"] == 60
        assert attrs["night_entry_time"] == 40
        assert attrs["stay_entry_time"] == 20
        assert attrs["siren_level_alarm"] == "VeryHighLevelSound"

    def test_no_gateway_returns_none(self):
        home_state = MagicMock()
        home_state.gateway = None
        coordinator = MagicMock()
        coordinator.get_home_state = MagicMock(return_value=home_state)
        panel = HomelyAlarmControlPanel(coordinator, LOCATION_ID, home_state)
        assert panel.extra_state_attributes is None
