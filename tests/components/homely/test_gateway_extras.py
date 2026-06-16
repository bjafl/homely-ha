"""Tests for gateway networks + history-log models and slow-poll coordinator.

From homely_sniffs.json:
  GET /gateways/{id}/networks   -> {connectionSource, wifiNetwork{name,connected},
                                    gsm{state,signalStrength,networkOperatorName}}
  GET /gateways/{id}/history-log -> [{id,status,type,...}, ...]  (status read/acknowledged/unread)
  PATCH /gateways/{id}/history-log  {"acknowledgeAll": true}     -> mark all read
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.homely.coordinator import GatewayExtrasCoordinator
from custom_components.homely.models import (
    GatewayLogEntry,
    GatewayNetworks,
    count_unread_log_entries,
)
from custom_components.homely.sensor import (
    HomelyGatewayGsmSignalSensor,
    HomelyGatewayUnreadLogSensor,
)
from custom_components.homely.button import (
    GatewayExtrasRefreshButton,
    GatewayMarkLogReadButton,
)

from .conftest import TEST_LOCATION_ID

TEST_GATEWAY_ID = "GW_SERIAL_001"


# ---------------------------------------------------------------------------
# Model tests (pure pydantic, no HA needed)
# ---------------------------------------------------------------------------


class TestGatewayNetworksModel:
    def test_parses_ethernet_with_gsm(self):
        net = GatewayNetworks.model_validate(
            {
                "connectionSource": "ethernet",
                "wifiNetwork": {"name": "", "connected": False},
                "gsm": {
                    "state": "CONNECTED",
                    "signalStrength": "NO_CONNECTION",
                    "networkOperatorName": "Telia N",
                },
            }
        )
        assert net.connection_source == "ethernet"
        assert net.gsm.state == "CONNECTED"
        assert net.gsm.signal_strength == "NO_CONNECTION"
        assert net.gsm.network_operator_name == "Telia N"
        assert net.wifi_network.connected is False


class TestGatewayLogModel:
    def test_parses_entry(self):
        entry = GatewayLogEntry.model_validate(
            {"id": 1940, "status": "read", "type": "armedstay"}
        )
        assert entry.id == 1940
        assert entry.status == "read"
        assert entry.type == "armedstay"

    def test_count_unread(self):
        entries = [
            GatewayLogEntry.model_validate({"id": 1, "status": "read", "type": "x"}),
            GatewayLogEntry.model_validate(
                {"id": 2, "status": "acknowledged", "type": "x"}
            ),
            GatewayLogEntry.model_validate({"id": 3, "status": "unread", "type": "x"}),
            GatewayLogEntry.model_validate({"id": 4, "status": "new", "type": "x"}),
        ]
        # read/acknowledged are seen; anything else counts as unread
        assert count_unread_log_entries(entries) == 2


# ---------------------------------------------------------------------------
# GatewayExtrasCoordinator
# ---------------------------------------------------------------------------


def _make_mock_api(networks_data=None, log_data=None):
    api = AsyncMock()
    api.get_gateway_networks.return_value = (
        GatewayNetworks.model_validate(networks_data) if networks_data else None
    )
    api.get_gateway_log.return_value = [
        GatewayLogEntry.model_validate(e) for e in (log_data or [])
    ]
    api.mark_gateway_log_read = AsyncMock()
    return api


class TestGatewayExtrasCoordinator:
    async def test_fetches_networks_and_log(self, hass):
        api = _make_mock_api(
            networks_data={
                "connectionSource": "ethernet",
                "wifiNetwork": {"name": "", "connected": False},
                "gsm": {
                    "state": "CONNECTED",
                    "signalStrength": "HIGH",
                    "networkOperatorName": "Telia",
                },
            },
            log_data=[
                {"id": 1, "status": "unread", "type": "armedaway"},
                {"id": 2, "status": "read", "type": "disarmed"},
            ],
        )
        coord = GatewayExtrasCoordinator(hass, api, TEST_GATEWAY_ID, TEST_LOCATION_ID)
        await coord.async_refresh()

        assert coord.data is not None
        assert coord.data["networks"].connection_source == "ethernet"
        assert coord.data["networks"].gsm.signal_strength == "HIGH"
        assert coord.data["unread_count"] == 1

    async def test_handles_failed_networks_fetch(self, hass):
        api = _make_mock_api(networks_data=None, log_data=[])
        coord = GatewayExtrasCoordinator(hass, api, TEST_GATEWAY_ID, TEST_LOCATION_ID)
        await coord.async_refresh()

        assert coord.data["networks"] is None
        assert coord.data["unread_count"] == 0

    async def test_update_interval_is_one_hour(self, hass):
        from datetime import timedelta

        api = _make_mock_api()
        coord = GatewayExtrasCoordinator(hass, api, TEST_GATEWAY_ID, TEST_LOCATION_ID)
        assert coord.update_interval == timedelta(hours=1)


# ---------------------------------------------------------------------------
# Sensor: GSM signal
# ---------------------------------------------------------------------------


def _make_extras_coordinator(signal_strength="HIGH", unread_count=0, networks=True):
    coord = MagicMock()
    if networks:
        net = MagicMock()
        net.gsm = MagicMock()
        net.gsm.signal_strength = signal_strength
        net.gsm.network_operator_name = "Telia"
        coord.data = {"networks": net, "unread_count": unread_count}
    else:
        coord.data = {"networks": None, "unread_count": unread_count}
    return coord


def _make_gateway_mock():
    gw = MagicMock()
    gw.serial_number = TEST_GATEWAY_ID
    gw.features = None
    return gw


class TestHomelyGatewayGsmSignalSensor:
    def test_native_value_from_coordinator(self, mock_coordinator_basic):
        extras = _make_extras_coordinator(signal_strength="HIGH")
        gw = _make_gateway_mock()
        sensor = HomelyGatewayGsmSignalSensor(
            extras, mock_coordinator_basic, TEST_LOCATION_ID, gw
        )
        assert sensor.native_value == "HIGH"

    def test_native_value_none_when_no_networks(self, mock_coordinator_basic):
        extras = _make_extras_coordinator(networks=False)
        gw = _make_gateway_mock()
        sensor = HomelyGatewayGsmSignalSensor(
            extras, mock_coordinator_basic, TEST_LOCATION_ID, gw
        )
        assert sensor.native_value is None

    def test_extra_state_attributes_include_operator(self, mock_coordinator_basic):
        extras = _make_extras_coordinator(signal_strength="HIGH")
        gw = _make_gateway_mock()
        sensor = HomelyGatewayGsmSignalSensor(
            extras, mock_coordinator_basic, TEST_LOCATION_ID, gw
        )
        attrs = sensor.extra_state_attributes or {}
        assert attrs.get("network_operator") == "Telia"


# ---------------------------------------------------------------------------
# Sensor: Unread log count
# ---------------------------------------------------------------------------


class TestHomelyGatewayUnreadLogSensor:
    def test_native_value_from_coordinator(self, mock_coordinator_basic):
        extras = _make_extras_coordinator(unread_count=3)
        gw = _make_gateway_mock()
        sensor = HomelyGatewayUnreadLogSensor(
            extras, mock_coordinator_basic, TEST_LOCATION_ID, gw
        )
        assert sensor.native_value == 3

    def test_native_value_zero(self, mock_coordinator_basic):
        extras = _make_extras_coordinator(unread_count=0)
        gw = _make_gateway_mock()
        sensor = HomelyGatewayUnreadLogSensor(
            extras, mock_coordinator_basic, TEST_LOCATION_ID, gw
        )
        assert sensor.native_value == 0


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------


class TestGatewayExtrasRefreshButton:
    async def test_press_triggers_coordinator_refresh(self, mock_coordinator_basic):
        extras = MagicMock()
        extras.async_request_refresh = AsyncMock()
        gw = _make_gateway_mock()
        button = GatewayExtrasRefreshButton(
            extras, mock_coordinator_basic, TEST_LOCATION_ID, gw
        )
        await button.async_press()
        extras.async_request_refresh.assert_called_once()


class TestGatewayMarkLogReadButton:
    async def test_press_calls_api_then_refreshes(self, mock_coordinator_basic):
        mock_api = AsyncMock()
        mock_api.mark_gateway_log_read = AsyncMock()
        extras = MagicMock()
        extras.async_request_refresh = AsyncMock()
        gw = _make_gateway_mock()
        button = GatewayMarkLogReadButton(
            extras, mock_coordinator_basic, TEST_LOCATION_ID, gw, mock_api
        )
        await button.async_press()
        mock_api.mark_gateway_log_read.assert_called_once_with(TEST_GATEWAY_ID)
        extras.async_request_refresh.assert_called_once()
