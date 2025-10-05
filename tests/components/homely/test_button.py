"""Test the Homely button entities."""

from unittest.mock import AsyncMock, MagicMock

from custom_components.homely.button import RefreshButton, async_setup_entry
from custom_components.homely.const import DOMAIN

from .conftest import TEST_LOCATION_ID


class TestHomelyButtonSetup:
    """Test setup of Homely buttons."""

    async def test_async_setup_entry_no_locations(
        self, hass, mock_config_entry, mock_coordinator_basic
    ):
        """Test setup entry with no locations selected."""
        mock_coordinator_basic.selected_location_ids = []
        hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator_basic}}

        mock_add_entities = MagicMock()
        await async_setup_entry(hass, mock_config_entry, mock_add_entities)
        mock_add_entities.assert_called_once_with([])

    async def test_async_setup_entry_no_home_state(
        self, hass, mock_config_entry, mock_coordinator_basic
    ):
        """Test setup entry with no home state for selected location."""
        mock_coordinator_basic.selected_location_ids = [TEST_LOCATION_ID]
        mock_coordinator_basic.get_home_state = MagicMock(return_value=None)
        hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator_basic}}

        mock_add_entities = MagicMock()
        await async_setup_entry(hass, mock_config_entry, mock_add_entities)
        mock_add_entities.assert_called_once_with([])

    async def test_async_setup_entry_with_location(
        self, hass, mock_config_entry, mock_coordinator_basic
    ):
        """Test setup entry with valid location."""
        mock_home_state = MagicMock()
        mock_home_state.gateway_serial = "TEST_SERIAL"
        mock_home_state.name = "Test Home"

        mock_coordinator_basic.selected_location_ids = [TEST_LOCATION_ID]
        mock_coordinator_basic.get_home_state = MagicMock(return_value=mock_home_state)
        hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator_basic}}

        mock_add_entities = MagicMock()
        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should have called add_entities once
        mock_add_entities.assert_called_once()
        # Get the entities that were added
        entities = mock_add_entities.call_args[0][0]
        # Should have one refresh button
        assert len(entities) == 1
        assert isinstance(entities[0], RefreshButton)

    async def test_async_setup_entry_with_multiple_locations(
        self, hass, mock_config_entry, mock_coordinator_basic
    ):
        """Test setup entry with multiple locations."""
        mock_home_state_1 = MagicMock()
        mock_home_state_2 = MagicMock()

        location_id_2 = "location_2"

        def get_home_state_side_effect(location_id):
            if location_id == TEST_LOCATION_ID:
                return mock_home_state_1
            elif location_id == location_id_2:
                return mock_home_state_2
            return None

        mock_coordinator_basic.selected_location_ids = [TEST_LOCATION_ID, location_id_2]
        mock_coordinator_basic.get_home_state = MagicMock(
            side_effect=get_home_state_side_effect
        )
        hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator_basic}}

        mock_add_entities = MagicMock()
        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should have called add_entities once
        mock_add_entities.assert_called_once()
        # Get the entities that were added
        entities = mock_add_entities.call_args[0][0]
        # Should have two refresh buttons
        assert len(entities) == 2
        assert all(isinstance(e, RefreshButton) for e in entities)


class TestRefreshButton:
    """Test Homely refresh button."""

    def test_init(self, mock_coordinator_basic):
        """Test refresh button initialization."""
        mock_home_state = MagicMock()
        mock_home_state.gateway_serial = "TEST_SERIAL"
        mock_home_state.name = "Test Home"

        button = RefreshButton(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_home_state
        )

        assert button._attr_name == "Trigger Refresh"
        assert button._attr_unique_id == f"{TEST_LOCATION_ID}_refresh"
        assert button._attr_icon == "mdi:refresh"
        assert button.location_id == TEST_LOCATION_ID

    def test_device_info(self, mock_coordinator_basic):
        """Test device info property."""
        mock_home_state = MagicMock()
        button = RefreshButton(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_home_state
        )

        device_info = button.device_info
        assert device_info is not None
        assert (DOMAIN, TEST_LOCATION_ID) in device_info["identifiers"]

    async def test_async_press(self, mock_coordinator_basic):
        """Test button press action."""
        mock_home_state = MagicMock()
        mock_coordinator_basic.async_request_refresh = AsyncMock()

        button = RefreshButton(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_home_state
        )

        await button.async_press()

        # Should have called async_request_refresh
        mock_coordinator_basic.async_request_refresh.assert_called_once()

    async def test_async_press_multiple_times(self, mock_coordinator_basic):
        """Test button press action multiple times."""
        mock_home_state = MagicMock()
        mock_coordinator_basic.async_request_refresh = AsyncMock()

        button = RefreshButton(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_home_state
        )

        await button.async_press()
        await button.async_press()
        await button.async_press()

        # Should have called async_request_refresh three times
        assert mock_coordinator_basic.async_request_refresh.call_count == 3
