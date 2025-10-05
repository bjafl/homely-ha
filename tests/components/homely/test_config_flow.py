"""Test the Homely config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_LOCATION, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from custom_components.homely.const import (
    CONF_AVAILABLE_LOCATIONS,
    DOMAIN,
    STEP_PICK_LOCATIONS,
)
from custom_components.homely.exceptions import (
    HomelyAuthInvalidError,
    HomelyNetworkError,
)

from .conftest import (
    TEST_LOCATION_ID,
    TEST_PASSWORD,
    TEST_USERNAME,
)


@pytest.fixture(name="homely_setup", autouse=True)
def homely_setup_fixture():
    """Mock homely entry setup."""
    with patch("custom_components.homely.async_setup_entry", return_value=True):
        yield


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    yield


class TestHomelyConfigFlow:
    """Test Homely config flow."""

    async def test_form_user(self, hass):
        """Test we get the user form."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["errors"] == {}
        assert result["step_id"] == "user"

    async def test_form_user_invalid_auth(self, hass, mock_session):
        """Test invalid authentication."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        with (
            patch(
                "custom_components.homely.config_flow.async_get_clientsession",
                return_value=mock_session,
            ),
            patch("custom_components.homely.config_flow.HomelyApi") as mock_api_class,
        ):
            mock_api = MagicMock()
            mock_api.login = AsyncMock(side_effect=HomelyAuthInvalidError("Invalid"))
            mock_api_class.return_value = mock_api

            result2 = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_USERNAME: TEST_USERNAME,
                    CONF_PASSWORD: TEST_PASSWORD,
                },
            )

            assert result2["type"] == data_entry_flow.FlowResultType.FORM
            assert result2["errors"] == {"base": "invalid_auth"}

    async def test_form_user_network_error(self, hass, mock_session):
        """Test network error during authentication."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        with (
            patch(
                "custom_components.homely.config_flow.async_get_clientsession",
                return_value=mock_session,
            ),
            patch("custom_components.homely.config_flow.HomelyApi") as mock_api_class,
        ):
            mock_api = MagicMock()
            mock_api.login = AsyncMock(side_effect=HomelyNetworkError("Network error"))
            mock_api_class.return_value = mock_api

            result2 = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_USERNAME: TEST_USERNAME,
                    CONF_PASSWORD: TEST_PASSWORD,
                },
            )

            assert result2["type"] == data_entry_flow.FlowResultType.FORM
            assert result2["errors"] == {"base": "cannot_connect"}

    async def test_form_user_unexpected_error(self, hass, mock_session):
        """Test unexpected error during authentication."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        with (
            patch(
                "custom_components.homely.config_flow.async_get_clientsession",
                return_value=mock_session,
            ),
            patch("custom_components.homely.config_flow.HomelyApi") as mock_api_class,
        ):
            mock_api = MagicMock()
            mock_api.login = AsyncMock(side_effect=Exception("Unexpected"))
            mock_api_class.return_value = mock_api

            result2 = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_USERNAME: TEST_USERNAME,
                    CONF_PASSWORD: TEST_PASSWORD,
                },
            )

            assert result2["type"] == data_entry_flow.FlowResultType.FORM
            assert result2["errors"] == {"base": "unknown"}

    async def test_form_user_no_locations(self, hass, mock_session):
        """Test no locations available."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        with (
            patch(
                "custom_components.homely.config_flow.async_get_clientsession",
                return_value=mock_session,
            ),
            patch("custom_components.homely.config_flow.HomelyApi") as mock_api_class,
        ):
            mock_api = MagicMock()
            mock_api.login = AsyncMock()
            mock_api.get_location_id_names = AsyncMock(return_value={})
            mock_api_class.return_value = mock_api

            result2 = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_USERNAME: TEST_USERNAME,
                    CONF_PASSWORD: TEST_PASSWORD,
                },
            )

            assert result2["type"] == data_entry_flow.FlowResultType.FORM
            assert result2["errors"] == {"base": "no_locations"}

    async def test_form_locations(self, hass, mock_session):
        """Test location selection form."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        test_locations = {TEST_LOCATION_ID: "Test Home"}

        with (
            patch(
                "custom_components.homely.config_flow.async_get_clientsession",
                return_value=mock_session,
            ),
            patch("custom_components.homely.config_flow.HomelyApi") as mock_api_class,
        ):
            mock_api = MagicMock()
            mock_api.login = AsyncMock()
            mock_api.get_location_id_names = AsyncMock(return_value=test_locations)
            mock_api_class.return_value = mock_api

            result2 = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_USERNAME: TEST_USERNAME,
                    CONF_PASSWORD: TEST_PASSWORD,
                },
            )

            assert result2["type"] == data_entry_flow.FlowResultType.FORM
            assert result2["step_id"] == "locations"

    async def test_form_locations_no_selection(self, hass, mock_session):
        """Test location selection with no locations selected."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        test_locations = {TEST_LOCATION_ID: "Test Home"}

        with (
            patch(
                "custom_components.homely.config_flow.async_get_clientsession",
                return_value=mock_session,
            ),
            patch("custom_components.homely.config_flow.HomelyApi") as mock_api_class,
        ):
            mock_api = MagicMock()
            mock_api.login = AsyncMock()
            mock_api.get_location_id_names = AsyncMock(return_value=test_locations)
            mock_api_class.return_value = mock_api

            result2 = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_USERNAME: TEST_USERNAME,
                    CONF_PASSWORD: TEST_PASSWORD,
                },
            )

            # Try to configure with no locations selected
            result3 = await hass.config_entries.flow.async_configure(
                result2["flow_id"],
                {
                    CONF_LOCATION: [],
                },
            )

            assert result3["type"] == data_entry_flow.FlowResultType.FORM
            assert result3["errors"] == {CONF_LOCATION: "at_least_one_location"}

    async def test_complete_flow(self, hass, mock_session):
        """Test complete config flow."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        test_locations = {TEST_LOCATION_ID: "Test Home"}

        with (
            patch(
                "custom_components.homely.config_flow.async_get_clientsession",
                return_value=mock_session,
            ),
            patch("custom_components.homely.config_flow.HomelyApi") as mock_api_class,
        ):
            mock_api = MagicMock()
            mock_api.login = AsyncMock()
            mock_api.get_location_id_names = AsyncMock(return_value=test_locations)
            mock_api_class.return_value = mock_api

            result2 = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_USERNAME: TEST_USERNAME,
                    CONF_PASSWORD: TEST_PASSWORD,
                },
            )

            result3 = await hass.config_entries.flow.async_configure(
                result2["flow_id"],
                {
                    CONF_LOCATION: [TEST_LOCATION_ID],
                },
            )

            assert result3["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
            assert result3["title"] == f"Homely ({TEST_USERNAME})"
            assert result3["data"][CONF_USERNAME] == TEST_USERNAME
            assert result3["data"][CONF_PASSWORD] == TEST_PASSWORD
            assert result3["data"][CONF_LOCATION] == [TEST_LOCATION_ID]
            assert result3["data"][CONF_AVAILABLE_LOCATIONS] == test_locations

    async def test_already_configured(
        self, hass: HomeAssistant, mock_session, mock_config_entry
    ):
        """Test flow when already configured."""
        mock_config_entry.add_to_hass(hass)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        test_locations = {TEST_LOCATION_ID: "Test Home"}

        with (
            patch(
                "custom_components.homely.config_flow.async_get_clientsession",
                return_value=mock_session,
            ),
            patch("custom_components.homely.config_flow.HomelyApi") as mock_api_class,
        ):
            mock_api = MagicMock()
            mock_api.login = AsyncMock()
            mock_api.get_location_id_names = AsyncMock(return_value=test_locations)
            mock_api_class.return_value = mock_api

            result2 = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_USERNAME: TEST_USERNAME,
                    CONF_PASSWORD: TEST_PASSWORD,
                },
            )

            result3 = await hass.config_entries.flow.async_configure(
                result2["flow_id"],
                {
                    CONF_LOCATION: [TEST_LOCATION_ID],
                },
            )

            assert result3.get("type") == data_entry_flow.FlowResultType.ABORT
            assert result3.get("reason") == "already_configured"


class TestHomelyOptionsFlow:
    """Test Homely options flow."""

    async def test_options_flow_init(
        self, hass: HomeAssistant, mock_session, mock_config_entry, api_logged_in
    ):
        """Test options flow initialization."""
        mock_config_entry.add_to_hass(hass)
        result = await hass.config_entries.options.async_init(
            mock_config_entry.entry_id
        )

        assert result.get("type") == data_entry_flow.FlowResultType.FORM
        assert result.get("step_id") == "pick_locations"

    async def test_options_flow_update_locations(self, hass, mock_config_entry):
        """Test updating locations through options flow."""
        mock_config_entry.add_to_hass(hass)

        # Init the options flow
        result = await hass.config_entries.options.async_init(
            mock_config_entry.entry_id
        )

        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == STEP_PICK_LOCATIONS

        # Verify current selections are shown as default
        # (The form should show loc1 as selected by default)

        # Update to select different locations
        with patch.object(hass.config_entries, "async_reload") as mock_reload:
            result2 = await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={CONF_LOCATION: ["loc2"]},  # Change from loc1 to loc2
            )

        assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
        mock_reload.assert_called_once_with(mock_config_entry.entry_id)

    async def test_options_flow_no_change(self, hass, mock_config_entry):
        """Test options flow with no location changes."""
        mock_config_entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(
            mock_config_entry.entry_id
        )

        # Use same location as configured
        with patch.object(hass.config_entries, "async_reload") as mock_reload:
            result2 = await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={CONF_LOCATION: [TEST_LOCATION_ID]},
            )

            assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
            # Should not trigger reload since locations didn't change
            mock_reload.assert_not_called()

    async def test_options_flow_fetch_fresh_locations(
        self, hass, mock_config_entry_no_locations, mock_session
    ):
        """Test fetching fresh locations when not available."""
        # Create config entry without available locations
        mock_config_entry_no_locations.add_to_hass(hass)

        fresh_locations = {
            TEST_LOCATION_ID: "Test Home",
            "new_location": "New Home",
        }

        with (
            patch(
                "custom_components.homely.config_flow.async_get_clientsession",
                return_value=mock_session,
            ),
            patch("custom_components.homely.config_flow.HomelyApi") as mock_api_class,
        ):
            mock_api = MagicMock()
            mock_api.login = AsyncMock()
            mock_api.get_location_id_names = AsyncMock(return_value=fresh_locations)
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.options.async_init(
                mock_config_entry_no_locations.entry_id
            )

            assert result["type"] == data_entry_flow.FlowResultType.FORM
            # Should have fetched fresh locations
            mock_api.login.assert_called_once()
            mock_api.get_location_id_names.assert_called_once()

    async def test_options_flow_fetch_locations_error(
        self, hass, mock_config_entry_no_locations, mock_session
    ):
        """Test error when fetching fresh locations."""
        # Create config entry without available locations
        # mock_config_entry.data = {
        #     CONF_USERNAME: TEST_USERNAME,
        #     CONF_PASSWORD: TEST_PASSWORD,
        #     CONF_LOCATION: [TEST_LOCATION_ID],
        # }
        mock_config_entry_no_locations.add_to_hass(hass)

        with (
            patch(
                "custom_components.homely.config_flow.async_get_clientsession",
                return_value=mock_session,
            ),
            patch("custom_components.homely.config_flow.HomelyApi") as mock_api_class,
        ):
            mock_api = MagicMock()
            mock_api.login = AsyncMock(
                side_effect=HomelyNetworkError("Mock network error")
            )
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.options.async_init(
                mock_config_entry_no_locations.entry_id
            )

            # Should still show form even if fetching fails
            assert result["type"] == data_entry_flow.FlowResultType.FORM
