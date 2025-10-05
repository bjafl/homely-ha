"""Entity base class and helpers for Homely integration."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import HomelyDataUpdateCoordinator
from .const import DOMAIN
from .models import (
    Device,
    SensorState,
)

_LOGGER = logging.getLogger(__name__)


# def create_device_info(device: Device) -> dict[str, Any]:
#     """Create device info for the device registry."""
#     device_info = {
#         "identifiers": {(DOMAIN, device.id)},
#         "name": device.name,
#         "manufacturer": get_manufacturer(device),
#         "model": device.model_name,
#         "suggested_area": device.location,
#         "serial_number": device.serial_number,
#     }
#     # Filter out None values to avoid mutating dict during iteration
#     return {key: value for key, value in device_info.items() if value is not None}


# def get_model_name(device: Device) -> str:
#     """Get the model name for a Homely device."""
#     MODEL_ID_MAP = {
#         "15e64f49-fdbc-4cd6-9912-e2a6e838d44f": "Intelligent Smoke Alarm",
#         "17ddbcb4-8c00-4bc3-b06f-d20f51c0fe52": "Alarm Motion Sensor 2",
#         "ad923ba3-2b72-45e0-a9d7-91808a76f2ed": "Intelligent Heat Alarm",
#         "57038a68-3a39-43c8-be8d-11f58521eecc": "Motion Sensor Mini",
#         "9b765375-e3f4-4627-b73c-b4143ce86c2c": "Alarm Entry Sensor 2",
#         # TODO: Add entries (+ move to consts?)
#     }
#     return MODEL_ID_MAP.get(str(device.model_id), "Unknown")


def get_manufacturer(device: Device) -> str:
    """Get the manufacturer for a Homely device."""
    SERIAL_MATCH = {
        "frient": re.compile(r"^0015BC"),  # Develco Products AS (frient)
        "FireAngel": re.compile(
            r"^00155F"
        ),  # GreenPeak (Qorvo) - used in FireAngel products
        "Yale": re.compile(r"^b0449c"),  # Untested, from dnschecker.org
        "ID Lock": re.compile(r"^70b3d5"),  # Untested, from dnschecker.org
        "ELKO": re.compile(
            r"^000D6F"
        ),  # Ember Corporation (Silicon Labs) - used in ELKO products
        "IKEA": re.compile(
            r"^68ec8a"
        ),  # IKEA uses several prefixes, (often Silicon Labs owned ?)
        # Namron seems to use several prefixes, often Silicon Labs owned
        "Climax Technology": re.compile(r"^001d94"),  # Untested, from dnschecker.org
        # TODO: Add entries (+ move to consts?)
    }
    MODEL_NAME_MATCH = {
        "ELKO": re.compile(r".*ELKO.*", re.IGNORECASE),
        "IKEA": re.compile(r".*IKEA.*", re.IGNORECASE),
        "frient": re.compile(r".*frient.*", re.IGNORECASE),
        "Yale": re.compile(r".*Yale.*", re.IGNORECASE),
        "Climax Technology": re.compile(r".*Climax.*", re.IGNORECASE),
        "Danalock": re.compile(r".*Danalock.*", re.IGNORECASE),
        "Develco Products": re.compile(r".*Develco.*", re.IGNORECASE),
        "EasyAccess": re.compile(r".*EasyAccess.*", re.IGNORECASE),
        "FireAngel": re.compile(r".*FireAngel.*", re.IGNORECASE),
        "ID Lock": re.compile(r".*ID Lock.*", re.IGNORECASE),
        "Namron": re.compile(r".*Namron.*", re.IGNORECASE),
        "nimly": re.compile(r".*nimly.*", re.IGNORECASE),
        "Onesti Products": re.compile(r".*Onesti.*", re.IGNORECASE),
        # TODO: Add entries (+ move to consts?)
    }
    if device.serial_number:
        for manufacturer, pattern in SERIAL_MATCH.items():
            if pattern.match(device.serial_number):
                return manufacturer
    if device.model_name:
        for manufacturer, pattern in MODEL_NAME_MATCH.items():
            if pattern.match(device.model_name):
                return manufacturer
    return "Unknown"


class HomelySensorBase(CoordinatorEntity[HomelyDataUpdateCoordinator]):
    """Base class for Homely sensors."""

    # coordinator: HomelyDataUpdateCoordinator
    def __init__(
        self,
        coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        device: Device,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.device_id = str(device.id)
        self.device_name = device.name
        self.device_location = device.location
        self.device_model = device.model_name
        self.device_model_id = str(device.model_id)
        self.device_serial = device.serial_number
        self.device_manufacturer = get_manufacturer(device)
        self.location_id = location_id
        self.last_updated: datetime | None = None

    @property
    def device_info(self) -> dr.DeviceInfo:
        """Return device info."""
        return dr.DeviceInfo(
            via_device=(DOMAIN, self.location_id),
            identifiers={(DOMAIN, self.device_id)},
            name=self.device_name,
            suggested_area=self.device_location,
            model=self.device_model,
            model_id=self.device_model_id,
            serial_number=self.device_serial,
            manufacturer=self.device_manufacturer,
        )

    # def _parse_float_value(self, value: StateValue | None) -> float | None:
    #     """Parse expected numeric value as float, handling invalid values."""
    #     if value is None:
    #         return None
    #     if isinstance(value, (int, float)):
    #         return float(value)

    #     if isinstance(value, str):
    #         try:
    #             return float(value)
    #         except ValueError:
    #             _LOGGER.warning(f"Can't parse StateValue {value} to float")
    #             return None

    #     _LOGGER.warning(
    #         f"Can't parse unexpected StateValue type to float: {type(value)} = {value}"
    #     )
    #     return None

    def _get_current_device_state(self) -> Device | None:
        """Get current device state from coordinator."""
        return self.coordinator.get_device_state(self.device_id, self.location_id)

    def _get_current_sensor_state(self) -> SensorState | None:
        """Get current sensor state from coordinator.

        To be implemented in subclasses.
        """
        return None  # To be implemented in subclasses

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return additional state attributes."""
        existing_attrs = super().extra_state_attributes or {}
        attrs = dict(existing_attrs)
        if self.last_updated and isinstance(self.last_updated, datetime):
            attrs["last_updated"] = self.last_updated
        return attrs
