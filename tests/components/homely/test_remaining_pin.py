"""Tests for the remaining-PIN-attempts sensor (location/alarm level).

`remainingPinAttempts` is a top-level field in the /home response; exposing it
makes the disarm PIN-lockout window visible (ref. the disarm 400 investigation).
"""

from unittest.mock import MagicMock

from homeassistant.const import EntityCategory

from custom_components.homely.models import HomeResponse

LOCATION_ID = "f32bf453-23f9-4986-9a0c-195a06c99961"


def _coordinator_with_home(remaining):
    coordinator = MagicMock()
    home = MagicMock()
    home.name = "Hjem"
    home.gateway_serial = "020000014000F13D"
    home.remaining_pin_attempts = remaining
    coordinator.get_home_state = MagicMock(return_value=home)
    return coordinator, home


class TestRemainingPinAttemptsModel:
    def test_home_response_parses_remaining_pin_attempts(self):
        home = HomeResponse.model_validate(
            {"location_id": LOCATION_ID, "devices": [], "remainingPinAttempts": 3}
        )
        assert home.remaining_pin_attempts == 3

    def test_absent_is_none(self):
        home = HomeResponse.model_validate(
            {"location_id": LOCATION_ID, "devices": []}
        )
        assert home.remaining_pin_attempts is None


class TestRemainingPinAttemptsSensor:
    def test_native_value(self):
        from custom_components.homely.sensor import HomelyRemainingPinAttemptsSensor

        coordinator, home = _coordinator_with_home(3)
        ent = HomelyRemainingPinAttemptsSensor(coordinator, LOCATION_ID, home)
        assert ent.native_value == 3

    def test_is_diagnostic(self):
        from custom_components.homely.sensor import HomelyRemainingPinAttemptsSensor

        coordinator, home = _coordinator_with_home(2)
        ent = HomelyRemainingPinAttemptsSensor(coordinator, LOCATION_ID, home)
        assert ent.entity_category == EntityCategory.DIAGNOSTIC

    def test_attaches_to_location_device(self):
        from custom_components.homely.const import DOMAIN
        from custom_components.homely.sensor import HomelyRemainingPinAttemptsSensor

        coordinator, home = _coordinator_with_home(2)
        ent = HomelyRemainingPinAttemptsSensor(coordinator, LOCATION_ID, home)
        assert (DOMAIN, LOCATION_ID) in ent.device_info["identifiers"]
