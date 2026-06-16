"""Tests for the gateway (hjemmesentral) model parsing.

Grounded in the real /home -> gateway block captured in homely_sniffs.json.
"""

from custom_components.homely.models import Gateway, HomeResponse

# Trimmed real gateway block from /home (api.homely.no).
GATEWAY_DATA = {
    "id": "eafa2c31-3eb4-41a3-90cf-19f498e7a2b7",
    "modelId": "744d57fe-6f71-4d6c-ad09-51dbc1b3feac",
    "locationId": "f32bf453-23f9-4986-9a0c-195a06c99961",
    "online": True,
    "serialNumber": "020000014000F13D",
    "features": {
        "connection": {
            "states": {"source": {"value": "ethernet", "lastUpdated": "2026-06-15T17:32:23.826Z"}}
        },
        "power": {
            "states": {
                "batteryPercent": {"value": 100, "lastUpdated": "2026-06-16T00:07:48.804Z"},
                "batteryVoltage": {"value": 4.1, "lastUpdated": "2026-06-16T00:07:48.804Z"},
                "powerSourceVoltage": {"value": 9.1, "lastUpdated": "2026-06-16T00:07:48.804Z"},
                "batteryLow": {"value": False, "lastUpdated": "2026-06-16T00:07:48.804Z"},
                "acPower": {"value": True},
            }
        },
        "status": {
            "states": {
                "firmwareVersion": {"value": "4.12.10"},
                "firmwareTargetVersion": {"value": "4.12.10"},
            }
        },
    },
}


class TestGatewayModel:
    def test_parses_identity(self):
        gw = Gateway.model_validate(GATEWAY_DATA)
        assert str(gw.id) == "eafa2c31-3eb4-41a3-90cf-19f498e7a2b7"
        assert gw.serial_number == "020000014000F13D"
        assert gw.online is True

    def test_parses_power_states(self):
        gw = Gateway.model_validate(GATEWAY_DATA)
        power = gw.features.power.states
        assert power.ac_power.value is True
        assert power.battery_percent.value == 100
        assert power.battery_low.value is False
        assert power.battery_voltage.value == 4.1
        assert power.power_source_voltage.value == 9.1

    def test_parses_connection_source(self):
        gw = Gateway.model_validate(GATEWAY_DATA)
        assert gw.features.connection.states.source.value == "ethernet"

    def test_parses_firmware_version(self):
        gw = Gateway.model_validate(GATEWAY_DATA)
        assert gw.features.status.states.firmware_version.value == "4.12.10"

    def test_missing_features_is_tolerated(self):
        gw = Gateway.model_validate({"id": GATEWAY_DATA["id"], "online": True})
        assert gw.features is None


class TestHomeResponseGateway:
    def test_home_response_carries_gateway(self):
        home = HomeResponse.model_validate(
            {
                "location_id": "f32bf453-23f9-4986-9a0c-195a06c99961",
                "devices": [],
                "gateway": GATEWAY_DATA,
            }
        )
        assert home.gateway is not None
        assert home.gateway.features.power.states.ac_power.value is True
        assert home.gateway.features.status.states.firmware_version.value == "4.12.10"

    def test_home_response_without_gateway(self):
        home = HomeResponse.model_validate(
            {"location_id": "f32bf453-23f9-4986-9a0c-195a06c99961", "devices": []}
        )
        assert home.gateway is None


LOCATION_ID = "f32bf453-23f9-4986-9a0c-195a06c99961"


def _coordinator_with_gateway(gateway):
    from unittest.mock import MagicMock

    coordinator = MagicMock()
    home = MagicMock()
    home.gateway = gateway
    home.name = "Hjem"
    coordinator.get_home_state = MagicMock(return_value=home)
    return coordinator


class TestGatewayBinarySensors:
    def test_ac_power_is_on_with_device_class_power(self):
        from homeassistant.components.binary_sensor import BinarySensorDeviceClass

        from custom_components.homely.binary_sensor import HomelyGatewayAcPowerSensor

        gw = Gateway.model_validate(GATEWAY_DATA)
        ent = HomelyGatewayAcPowerSensor(_coordinator_with_gateway(gw), LOCATION_ID, gw)
        assert ent.is_on is True
        assert ent.device_class == BinarySensorDeviceClass.POWER

    def test_battery_low_reflects_state(self):
        from homeassistant.components.binary_sensor import BinarySensorDeviceClass

        from custom_components.homely.binary_sensor import HomelyGatewayBatteryLowSensor

        gw = Gateway.model_validate(GATEWAY_DATA)
        ent = HomelyGatewayBatteryLowSensor(
            _coordinator_with_gateway(gw), LOCATION_ID, gw
        )
        assert ent.is_on is False  # batteryLow == False
        assert ent.device_class == BinarySensorDeviceClass.BATTERY

    def test_online_is_connectivity(self):
        from homeassistant.components.binary_sensor import BinarySensorDeviceClass

        from custom_components.homely.binary_sensor import HomelyGatewayOnlineSensor

        gw = Gateway.model_validate(GATEWAY_DATA)
        ent = HomelyGatewayOnlineSensor(_coordinator_with_gateway(gw), LOCATION_ID, gw)
        assert ent.is_on is True  # gateway.online
        assert ent.device_class == BinarySensorDeviceClass.CONNECTIVITY

    def test_device_info_attaches_to_gateway_with_firmware(self):
        from custom_components.homely.binary_sensor import HomelyGatewayAcPowerSensor
        from custom_components.homely.const import DOMAIN

        gw = Gateway.model_validate(GATEWAY_DATA)
        ent = HomelyGatewayAcPowerSensor(_coordinator_with_gateway(gw), LOCATION_ID, gw)
        info = ent.device_info
        assert (DOMAIN, LOCATION_ID) in info["identifiers"]
        assert info["sw_version"] == "4.12.10"


class TestGatewaySensors:
    def test_battery_percent(self):
        from homeassistant.components.sensor import SensorDeviceClass

        from custom_components.homely.sensor import HomelyGatewayBatterySensor

        gw = Gateway.model_validate(GATEWAY_DATA)
        ent = HomelyGatewayBatterySensor(_coordinator_with_gateway(gw), LOCATION_ID, gw)
        assert ent.native_value == 100
        assert ent.device_class == SensorDeviceClass.BATTERY
        assert ent.native_unit_of_measurement == "%"

    def test_battery_voltage(self):
        from homeassistant.components.sensor import SensorDeviceClass

        from custom_components.homely.sensor import HomelyGatewayBatteryVoltageSensor

        gw = Gateway.model_validate(GATEWAY_DATA)
        ent = HomelyGatewayBatteryVoltageSensor(
            _coordinator_with_gateway(gw), LOCATION_ID, gw
        )
        assert ent.native_value == 4.1
        assert ent.device_class == SensorDeviceClass.VOLTAGE

    def test_power_source_voltage(self):
        from custom_components.homely.sensor import (
            HomelyGatewayPowerSourceVoltageSensor,
        )

        gw = Gateway.model_validate(GATEWAY_DATA)
        ent = HomelyGatewayPowerSourceVoltageSensor(
            _coordinator_with_gateway(gw), LOCATION_ID, gw
        )
        assert ent.native_value == 9.1

    def test_connection_source(self):
        from homeassistant.components.sensor import SensorDeviceClass

        from custom_components.homely.sensor import HomelyGatewayConnectionSensor

        gw = Gateway.model_validate(GATEWAY_DATA)
        ent = HomelyGatewayConnectionSensor(
            _coordinator_with_gateway(gw), LOCATION_ID, gw
        )
        assert ent.native_value == "ethernet"
        assert ent.device_class == SensorDeviceClass.ENUM
