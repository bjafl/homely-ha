"""Tests for siren and keypad-panel feature parsing and binary sensors.

Grounded in homely_sniffs.json device features:
  siren.{battery,acmains,tamper,conflevel}  (Alarm Siren)
  panel.{tamper,battery}                    (Alarm Keypad)
"""

from unittest.mock import MagicMock

from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.homely.models import DeviceFeatures, PanelStates, SirenStates

LOCATION_ID = "f32bf453-23f9-4986-9a0c-195a06c99961"


class TestSirenModel:
    def test_siren_states_parse(self):
        s = SirenStates.model_validate(
            {
                "battery": {"value": False},
                "acmains": {"value": False},
                "tamper": {"value": False},
                "conflevel": {"value": 3},
            }
        )
        assert s.battery.value is False
        assert s.acmains.value is False
        assert s.tamper.value is False


class TestPanelModel:
    def test_panel_feature_parses(self):
        feats = DeviceFeatures.model_validate(
            {"panel": {"states": {"tamper": {"value": False}, "battery": {"value": False}}}}
        )
        assert feats.panel is not None
        assert feats.panel.states.tamper.value is False

    def test_panel_states_standalone(self):
        ps = PanelStates.model_validate({"tamper": {"value": True}})
        assert ps.tamper.value is True


def _coordinator(device):
    c = MagicMock()
    c.get_device_state = MagicMock(return_value=device)
    return c


def _siren_device(acmains=False, tamper=False, battery=False):
    from custom_components.homely.models import Device

    return Device.model_validate(
        {
            "id": "6555f7b8-16d0-4657-8be2-4b74806038be",
            "name": "Sirene",
            "online": True,
            "modelId": "9b765375-e3f4-4627-b73c-b4143ce86c2c",
            "modelName": "Alarm Siren",
            "serialNumber": "0015BC004100EB3A",
            "features": {
                "siren": {
                    "states": {
                        "acmains": {"value": acmains},
                        "tamper": {"value": tamper},
                        "battery": {"value": battery},
                    }
                }
            },
        }
    )


class TestSirenSensors:
    def test_acmains_is_power(self):
        from custom_components.homely.binary_sensor import HomelySirenAcMainsSensor

        dev = _siren_device(acmains=True)
        ent = HomelySirenAcMainsSensor(_coordinator(dev), LOCATION_ID, dev)
        assert ent.is_on is True
        assert ent.device_class == BinarySensorDeviceClass.POWER

    def test_tamper(self):
        from custom_components.homely.binary_sensor import HomelySirenTamperSensor

        dev = _siren_device(tamper=True)
        ent = HomelySirenTamperSensor(_coordinator(dev), LOCATION_ID, dev)
        assert ent.is_on is True
        assert ent.device_class == BinarySensorDeviceClass.TAMPER

    def test_battery(self):
        from custom_components.homely.binary_sensor import HomelySirenBatterySensor

        dev = _siren_device(battery=True)
        ent = HomelySirenBatterySensor(_coordinator(dev), LOCATION_ID, dev)
        assert ent.is_on is True
        assert ent.device_class == BinarySensorDeviceClass.BATTERY

    def test_registered_when_siren_feature_present(self):
        from custom_components.homely.binary_sensor import (
            HomelySirenAcMainsSensor,
            create_binary_entities_from_device,
        )

        dev = _siren_device()
        entities = create_binary_entities_from_device(MagicMock(), LOCATION_ID, dev)
        assert any(isinstance(e, HomelySirenAcMainsSensor) for e in entities)


class TestPanelSensors:
    def test_panel_tamper(self):
        from custom_components.homely.binary_sensor import HomelyPanelTamperSensor
        from custom_components.homely.models import Device

        dev = Device.model_validate(
            {
                "id": "4384e3e7-27b5-4646-9400-958a863a0a4a",
                "name": "Keypad",
                "online": True,
                "modelId": "9b765375-e3f4-4627-b73c-b4143ce86c2c",
                "modelName": "Alarm Keypad",
                "serialNumber": "0015BC004300926C",
                "features": {"panel": {"states": {"tamper": {"value": True}}}},
            }
        )
        ent = HomelyPanelTamperSensor(_coordinator(dev), LOCATION_ID, dev)
        assert ent.is_on is True
        assert ent.device_class == BinarySensorDeviceClass.TAMPER
