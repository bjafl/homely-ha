"""Tests for UserRole values and tolerant parsing.

Grounded in captured app-API traffic (GET /locations/{id}/users, 2026-07-05):
OWNER, ADMIN, and USER are all real, observed roles.
"""

import logging

import pytest

from custom_components.homely.models import Location, UserRole

LOCATION_ID = "f32bf453-23f9-4986-9a0c-195a06c99961"


class TestUserRoleValues:
    """The enum must contain the values the app-API actually sends."""

    def test_owner_value_exists(self):
        assert UserRole.OWNER.value == "OWNER"

    def test_admin_value_exists(self):
        assert UserRole.ADMIN.value == "ADMIN"

    def test_user_value_exists(self):
        # Sniffed via GET /locations/{id}/users — a real, non-admin account role.
        assert UserRole.USER.value == "USER"


class TestUnknownUserRoleFallback:
    """An unrecognized role must never crash location parsing."""

    def test_unknown_role_maps_to_unknown_member(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = UserRole("GUEST")
        assert result is UserRole.UNKNOWN
        assert "GUEST" in caplog.text


class TestLocationParsesUserRole:
    """GET /locations must not raise for any real observed role."""

    @pytest.mark.parametrize("role", ["OWNER", "ADMIN", "USER"])
    def test_location_parses_role(self, role):
        loc = Location(
            **{
                "name": "Hjem",
                "locationId": LOCATION_ID,
                "role": role,
                "userId": "5fcb044d-2f2b-43fb-9ca3-8b3869342be7",
            }
        )
        assert loc.role is UserRole(role)
