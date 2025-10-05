"""Support for Homely binary sensors."""

from __future__ import annotations

import logging
import re

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import HomelyDataUpdateCoordinator
from .base_sensor import HomelySensorBase
from .const import (
    DOMAIN,
    RE_ENTRY_SENSOR,
    RE_MOTION_SENSOR,
    HomelyEntityIcons,
    HomelyEntityIdSuffix,
)
from .models import (
    Device,
    SensorState,
)

_LOGGER = logging.getLogger(__name__)

type HomelyAlarmSensor = (
    HomelyEntrySensor
    | HomelyTamperSensor
    | HomelyFloodSensor
    | HomelySmokeSensor
    | HomelyMotionSensor
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homely binary sensors based on a config entry."""
    coordinator: HomelyDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    if not coordinator.selected_location_ids:
        _LOGGER.warning("No locations selected, no binary sensors will be created")
        return
    selected_locations_data = {
        k: v
        for k, v in coordinator.data.items()
        if k in coordinator.selected_location_ids
    }
    if not selected_locations_data:
        _LOGGER.warning(
            "No data for selected locations, no binary sensors will be created"
        )
        return

    entities = []

    for location_id, home_state in selected_locations_data.items():
        for device in home_state.devices:
            dev_entities = create_binary_entities_from_device(
                coordinator, location_id, device
            )
            entities.extend(dev_entities)

    async_add_entities(entities)


def pick_alarm_classes(device: Device) -> list[type[HomelyAlarmSensor]] | None:
    """Identify available alarm sensors to register for device."""
    alarm = device.features.alarm
    if not alarm:
        return None
    model_name = device.model_name.lower() if device.model_name else ""
    classes: list[type[HomelyAlarmSensor]] = []
    if alarm.states.fire is not None:
        classes.append(HomelySmokeSensor)
    if alarm.states.flood is not None:
        classes.append(HomelyFloodSensor)
    if alarm.states.tamper is not None:
        classes.append(HomelyTamperSensor)
    if alarm.states.alarm is not None:
        if re.match(RE_MOTION_SENSOR, model_name):
            classes.append(HomelyMotionSensor)
        elif re.match(RE_ENTRY_SENSOR, model_name):
            classes.append(HomelyEntrySensor)
    return classes


def create_binary_entities_from_device(
    coordinator: HomelyDataUpdateCoordinator,
    location_id: str,
    device: Device,
) -> list[HomelySensorBase[bool]]:
    """Create binary sensor entities based on device capabilities."""
    entities: list[HomelySensorBase[bool]] = []
    sensor_args = (coordinator, location_id, device)
    if (alarm_classes := pick_alarm_classes(device)) is not None:
        for alarm_cls in alarm_classes:
            _LOGGER.debug(
                "Creating %s for device %s (%s)",
                alarm_cls.__name__,
                device.name,
                device.id,
            )
            entities.append(alarm_cls(*sensor_args))
    if (battery := device.features.battery) is not None:
        if battery.states.low is not None:
            entities.append(HomelyBatteryLowSensor(*sensor_args))
        if battery.states.defect is not None:
            entities.append(HomelyBatteryDefectSensor(*sensor_args))
    if (metering := device.features.metering) is not None:
        if metering.states.check is not None:
            entities.append(HomelyEnergyCheckSensor(*sensor_args))
    return entities


class HomelyBinarySensorBase(HomelySensorBase[bool], BinarySensorEntity):
    """Base class for Homely binary sensors."""

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        sensor_state = self._get_current_sensor_state()
        if not sensor_state:
            return None
        return bool(sensor_state.value)


class HomelyMotionSensor(HomelyBinarySensorBase):
    """Homely motion sensor."""

    def __init__(
        self,
        coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        device: Device,
    ) -> None:
        """Initialize the motion sensor."""
        super().__init__(
            coordinator,
            location_id,
            device,
        )
        self._attr_unique_id = f"{self.device_id}_motion"
        self.has_entity_name = True
        # self._attr_name = "Motion"
        self._attr_translation_key = "motion"
        self._attr_device_class = BinarySensorDeviceClass.MOTION

    def _get_current_sensor_state(self) -> SensorState[bool] | None:
        """Get current sensor state from coordinator."""
        device = self._get_current_device_state()
        if not device or not device.features.alarm:
            return None
        state = device.features.alarm.states.alarm
        if state is not None:
            self.last_updated = state.last_updated
        return state


class HomelyEntrySensor(HomelyBinarySensorBase):
    """Homely entry sensor for door/window sensors."""

    def __init__(
        self,
        coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        device: Device,
    ) -> None:
        """Initialize the entry/exit delay sensor."""
        super().__init__(
            coordinator,
            location_id,
            device,
        )
        self._attr_unique_id = f"{self.device_id}_opening"
        self.has_entity_name = True
        self._attr_translation_key = "opening"
        self._attr_device_class = BinarySensorDeviceClass.OPENING

    def _get_current_sensor_state(self) -> SensorState[bool] | None:
        """Get current sensor state from coordinator."""
        device = self._get_current_device_state()
        if not device or not device.features.alarm:
            return None
        state = device.features.alarm.states.alarm
        if state is not None:
            self.last_updated = state.last_updated
        return state


class HomelySmokeSensor(HomelyBinarySensorBase):
    """Homely smoke sensor."""

    def __init__(
        self,
        coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        device: Device,
    ) -> None:
        """Initialize the smoke alarm sensor."""
        super().__init__(
            coordinator,
            location_id,
            device,
        )
        self._attr_unique_id = f"{self.device_id}_smoke"
        self.has_entity_name = True
        self._attr_translation_key = "smoke"
        self._attr_device_class = BinarySensorDeviceClass.SMOKE

    def _get_current_sensor_state(self) -> SensorState[bool] | None:
        """Get current sensor state from coordinator."""
        device = self._get_current_device_state()
        if not device or not device.features.alarm:
            return None
        state = device.features.alarm.states.fire
        if state is not None:
            self.last_updated = state.last_updated
        return state


class HomelyTamperSensor(HomelyBinarySensorBase):
    """Homely tamper sensor."""

    def __init__(
        self,
        coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        device: Device,
    ) -> None:
        """Initialize the tamper alarm sensor."""
        super().__init__(
            coordinator,
            location_id,
            device,
        )
        self._attr_unique_id = f"{self.device_id}_tamper"
        self.has_entity_name = True
        self._attr_translation_key = "tamper"
        self._attr_device_class = BinarySensorDeviceClass.TAMPER

    def _get_current_sensor_state(self) -> SensorState[bool] | None:
        """Get current sensor state from coordinator."""
        device = self._get_current_device_state()
        if not device or not device.features.alarm:
            return None
        state = device.features.alarm.states.tamper
        if state is not None:
            self.last_updated = state.last_updated
        return state


class HomelyFloodSensor(HomelyBinarySensorBase):
    """Homely flood sensor."""

    def __init__(
        self,
        coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        device: Device,
    ) -> None:
        """Initialize the flood alarm sensor."""
        super().__init__(
            coordinator,
            location_id,
            device,
        )
        self._attr_unique_id = f"{self.device_id}_flood"
        self.has_entity_name = True
        self._attr_translation_key = "flood"
        self._attr_device_class = BinarySensorDeviceClass.MOISTURE

    def _get_current_sensor_state(self) -> SensorState[bool] | None:
        """Get current sensor state from coordinator."""
        device = self._get_current_device_state()
        if not device or not device.features.alarm:
            return None
        state = device.features.alarm.states.flood
        if state is not None:
            self.last_updated = state.last_updated
        return state


class HomelyBatteryLowSensor(HomelyBinarySensorBase):
    """Battery sensor for Homely devices."""

    def __init__(
        self,
        coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        device: Device,
    ) -> None:
        """Initialize the battery sensor."""
        super().__init__(
            coordinator,
            location_id,
            device,
        )
        self._attr_unique_id = f"{self.device_id}_battery_low_alarm"
        self.has_entity_name = True
        self._attr_translation_key = "battery_low"
        self._attr_device_class = BinarySensorDeviceClass.BATTERY
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self.voltage: float | None = None

    def _get_current_sensor_state(self) -> SensorState[bool] | None:
        """Get current sensor state from coordinator."""
        device = self._get_current_device_state()
        if not device or not device.features.battery:
            return None
        state = device.features.battery.states.low
        if state is not None:
            self.last_updated = state.last_updated
        if device.features.battery.states.voltage is not None:
            self.voltage = device.features.battery.states.voltage.value
        return state

    @property
    def extra_state_attributes(self) -> dict[str, float | None]:
        """Return the state attributes."""
        existing_attrs = super().extra_state_attributes or {}
        attrs = dict(existing_attrs)
        if self.voltage is not None:
            attrs["voltage"] = self.voltage
        return attrs

    @property
    def icon(self) -> str:
        """Return dynamic icon based on battery low state."""
        if self.is_on:
            return HomelyEntityIcons.BATTERY_LOW
        return HomelyEntityIcons.BATTERY_NOT_LOW


class HomelyBatteryDefectSensor(HomelyBinarySensorBase):
    """Battery defect alarm sensor."""

    def __init__(
        self,
        coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        device: Device,
    ) -> None:
        """Initialize the battery sensor."""
        super().__init__(
            coordinator,
            location_id,
            device,
        )
        self._attr_unique_id = f"{self.device_id}_{HomelyEntityIdSuffix.BATTERY_DEFECT}"
        self.has_entity_name = True
        self._attr_translation_key = HomelyEntityIdSuffix.BATTERY_DEFECT
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    def _get_current_sensor_state(self) -> SensorState[bool] | None:
        """Get current sensor state from coordinator."""
        device = self._get_current_device_state()
        if not device or not device.features.battery:
            return None
        state = device.features.battery.states.defect
        if state is not None:
            self.last_updated = state.last_updated
        return state

    @property
    def icon(self) -> str:
        """Return dynamic icon based on battery defect state."""
        if self.is_on:
            return HomelyEntityIcons.BATTERY_DEFECT
        return HomelyEntityIcons.BATTERY_NOT_DEFECT


class HomelyEnergyCheckSensor(HomelyBinarySensorBase):
    """Metering check value from API, dont know what it signifies."""

    # TODO: Investigate

    def __init__(
        self,
        coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        device: Device,
    ) -> None:
        """Initialize the energy check sensor."""
        super().__init__(coordinator, location_id, device)
        self._attr_unique_id = f"{self.device_id}_{HomelyEntityIdSuffix.ENERGY_CHECK}"
        self.has_entity_name = True
        self._attr_translation_key = HomelyEntityIdSuffix.ENERGY_CHECK
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM  # TODO: verify

    def _get_current_sensor_state(self) -> SensorState[bool] | None:
        """Get current sensor state from coordinator."""
        device = self._get_current_device_state()
        if not device or not device.features.metering:
            return None
        if (state := device.features.metering.states.check) is not None:
            self.last_updated = state.last_updated
        return state
