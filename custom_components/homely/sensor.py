"""Support for Homely sensors."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from homeassistant.components.alarm_control_panel.const import AlarmControlPanelState
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.homely.homely_api import HomelyHomeState

from .coordinator import HomelyDataUpdateCoordinator
from .base_sensor import HomelySensorBase
from .const import DOMAIN, HomelyEntityIcons
from .models import (
    AlarmState,
    Device,
    MeteringStateName,
    SensorState,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homely sensors based on a config entry."""
    coordinator: HomelyDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    if not coordinator.selected_location_ids:
        _LOGGER.warning("No locations selected, no sensors will be created")
        return
    selected_locations_data = {
        k: v
        for k, v in coordinator.data.items()
        if k in coordinator.selected_location_ids
    }
    if not selected_locations_data:
        _LOGGER.warning("No data for selected locations, no sensors will be created")
        return

    entities = []

    for location_id, home_state in selected_locations_data.items():
        entities.append(HomelyAlarmStateSensor(coordinator, location_id, home_state))

        for device in home_state.devices:
            dev_entities = create_entities_from_device(coordinator, location_id, device)
            entities.extend(dev_entities)

    async_add_entities(entities)


def create_entities_from_device(
    coordinator: HomelyDataUpdateCoordinator,
    location_id: str,
    device: Device,
) -> list[HomelySensorBase]:
    """Create sensor entities based on device capabilities."""
    entities: list[HomelySensorBase] = []
    if device.features.temperature is not None:
        entities.append(HomelyTemperatureSensor(coordinator, location_id, device))
    if (diagnostic := device.features.diagnostic) is not None:
        if diagnostic.states.network_link_strength is not None:
            entities.append(
                HomelySignalStrengthSensor(
                    coordinator,
                    location_id,
                    device,
                )
            )
    if (metering := device.features.metering) is not None:
        if metering.states.summation_delivered is not None:
            entities.append(
                HomelyEnergySensor(
                    coordinator,
                    location_id,
                    device,
                    MeteringStateName.SUMMATION_DELIVERED,
                )
            )
        if metering.states.summation_received is not None:
            entities.append(
                HomelyEnergySensor(
                    coordinator,
                    location_id,
                    device,
                    MeteringStateName.SUMMATION_RECEIVED,
                )
            )
        if metering.states.demand is not None:
            entities.append(
                HomelyEnergyDemandSensor(
                    coordinator,
                    location_id,
                    device,
                )
            )
    if device.features.thermostat is not None:
        entities.append(
            HomelyThermostatSensor(
                coordinator,
                location_id,
                device,
            )
        )
    return entities


class HomelyTemperatureSensor(HomelySensorBase, SensorEntity):
    """Temperature sensor for Homely devices."""

    def __init__(
        self,
        coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        device: Device,
    ) -> None:
        """Initialize the temperature sensor."""
        super().__init__(
            coordinator,
            location_id,
            device,
        )
        self._attr_unique_id = f"{self.device_id}_temperature"
        self.has_entity_name = True
        self._attr_translation_key = "temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return the temperature value."""
        temperature_state = self._get_current_sensor_state()
        if not temperature_state:
            return None
        return temperature_state.value

    def _get_current_sensor_state(self) -> SensorState[float] | None:
        """Get current sensor state from coordinator."""
        device = self._get_current_device_state()
        if not device or not device.features.temperature:
            return None
        if (state := device.features.temperature.states.temperature) is not None:
            self.last_updated = state.last_updated
        return state


class HomelyAlarmStateSensor(
    CoordinatorEntity[HomelyDataUpdateCoordinator], SensorEntity
):
    """Alarm state sensor for Homely gateway."""

    _ALARM_STATE_MAP = {
        AlarmState.DISARMED: AlarmControlPanelState.DISARMED,
        AlarmState.ARMED_PARTLY: AlarmControlPanelState.ARMED_HOME,
        AlarmState.ARMED_AWAY: AlarmControlPanelState.ARMED_AWAY,
        AlarmState.ARMED_NIGHT: AlarmControlPanelState.ARMED_NIGHT,
        AlarmState.ALARM_STAY_PENDING: AlarmControlPanelState.ARMING,
        AlarmState.ARMED_NIGHT_PENDING: AlarmControlPanelState.ARMING,
        AlarmState.ARMED_AWAY_PENDING: AlarmControlPanelState.ARMING,
        AlarmState.BREACHED: AlarmControlPanelState.TRIGGERED,
        AlarmState.ALARM_PENDING: AlarmControlPanelState.PENDING,
    }  # TODO: verify mapping

    def __init__(
        self,
        coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        home_state: HomelyHomeState,
    ) -> None:
        """Initialize the alarm state sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{location_id}_alarm_state"
        self.has_entity_name = True
        self._attr_translation_key = "alarm_state"
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = [
            AlarmControlPanelState.DISARMED,
            AlarmControlPanelState.ARMED_HOME,
            AlarmControlPanelState.ARMED_AWAY,
            AlarmControlPanelState.ARMED_NIGHT,
            AlarmControlPanelState.ARMING,
            AlarmControlPanelState.PENDING,
            AlarmControlPanelState.TRIGGERED,
        ]
        self.device_manufacturer = "Homely"
        self.device_model = "Homely Alarm Gateway"
        self.device_serial = home_state.gateway_serial
        self.device_name = home_state.name
        self.user_role = home_state.user_role
        self.location_id = location_id
        self.last_updated: datetime | None = None
        self._homely_alarm_state: AlarmState | None = None

    @property
    def device_info(self) -> dr.DeviceInfo:
        """Return device info."""
        return dr.DeviceInfo(
            identifiers={(DOMAIN, self.location_id)},
            name=self.device_name,
            model=self.device_model,
            serial_number=self.device_serial,
            manufacturer=self.device_manufacturer,
        )

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return additional state attributes."""
        existing_attrs = super().extra_state_attributes or {}
        attrs = dict(existing_attrs)
        attrs["user_role"] = self.user_role
        attrs["homely_alarm_state"] = (
            self._homely_alarm_state.value if self._homely_alarm_state else None
        )
        return attrs

    @property
    def native_value(self) -> AlarmControlPanelState | None:
        """Return the alarm state value."""
        alarm_state = self._get_current_sensor_state()
        if not alarm_state:
            return None
        if alarm_state.value not in self._ALARM_STATE_MAP:
            _LOGGER.error(f"Unknown alarm state: {alarm_state}")
            return None
        return self._ALARM_STATE_MAP.get(AlarmState(alarm_state.value))

    @property
    def icon(self) -> str:
        """Return dynamic icon based on alarm state."""
        state = self.native_value

        match state:
            case AlarmControlPanelState.DISARMED:
                return HomelyEntityIcons.ALARM_DISARMED
            case AlarmControlPanelState.ARMED_HOME:
                return HomelyEntityIcons.ALARM_ARMED_HOME
            case AlarmControlPanelState.ARMED_AWAY:
                return HomelyEntityIcons.ALARM_ARMED_AWAY
            case AlarmControlPanelState.ARMED_NIGHT:
                return HomelyEntityIcons.ALARM_ARMED_NIGHT
            case AlarmControlPanelState.ARMING:
                return HomelyEntityIcons.ALARM_ARMING
            case AlarmControlPanelState.PENDING:
                return HomelyEntityIcons.ALARM_PENDING
            case AlarmControlPanelState.TRIGGERED:
                return HomelyEntityIcons.ALARM_TRIGGERED
            case _:
                return HomelyEntityIcons.ALARM_UNKNOWN

    def _get_current_sensor_state(self) -> AlarmState | None:
        """Get current sensor state from coordinator."""
        home_state = self.coordinator.get_home_state(self.location_id)
        _LOGGER.debug(f"Home state for location {self.location_id}: {home_state}")
        if not home_state or not home_state.alarm_state:
            self._homely_alarm_state = None
            return None
        self._homely_alarm_state = home_state.alarm_state
        return self._homely_alarm_state


class HomelySignalStrengthSensor(HomelySensorBase, SensorEntity):
    """Diagnostic sensor for Homely devices."""

    def __init__(
        self,
        coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        device: Device,
    ) -> None:
        """Initialize the diagnostic sensor."""
        super().__init__(
            coordinator,
            location_id,
            device,
        )
        self._attr_unique_id = f"{self.device_id}_signal_strength"
        self.has_entity_name = True
        self._attr_translation_key = "signal_strength"
        self._attr_native_unit_of_measurement = "%"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self.network_link_address: str | None = None

    @property
    def icon(self) -> str:
        """Return dynamic icon based on signal strength."""
        if self.native_value is None:
            return HomelyEntityIcons.SIGNAL_NONE

        strength = self.native_value

        if strength >= 80:
            return HomelyEntityIcons.SIGNAL_HIGH
        elif strength >= 60:
            return HomelyEntityIcons.SIGNAL_MEDIUM
        elif strength >= 40:
            return HomelyEntityIcons.SIGNAL_LOW
        else:
            return HomelyEntityIcons.SIGNAL_VERY_LOW

    @property
    def native_value(self) -> int | None:
        """Return the network link strength value."""
        diagnostic_state = self._get_current_sensor_state()
        if not diagnostic_state:
            return None
        return diagnostic_state.value

    def _get_current_sensor_state(self) -> SensorState[int] | None:
        """Get current sensor state from coordinator."""
        device = self._get_current_device_state()
        if not device or not device.features.diagnostic:
            return None
        if (
            state := device.features.diagnostic.states.network_link_strength
        ) is not None:
            self.last_updated = state.last_updated
        if (
            network_link_address
            := device.features.diagnostic.states.network_link_address
        ) is not None:
            self.network_link_address = network_link_address.value
        return state

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return additional state attributes."""
        existing_attrs = super().extra_state_attributes or {}
        attrs = dict(existing_attrs)
        if self.network_link_address:
            attrs["network_link_address"] = self.network_link_address
        return attrs


class HomelyEnergySensor(HomelySensorBase):
    """Energy sensor for Homely devices."""

    def __init__(
        self,
        coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        device: Device,
        metering_type: Literal[
            MeteringStateName.SUMMATION_DELIVERED,
            MeteringStateName.SUMMATION_RECEIVED,
        ],
    ) -> None:
        """Initialize the metering sensor."""
        super().__init__(coordinator, location_id, device)
        self._metering_type = metering_type
        self._meter_type_short = (
            "delivered"
            if metering_type == MeteringStateName.SUMMATION_DELIVERED
            else "received"
        )
        self._attr_unique_id = f"{self.device_id}_energy_{self._meter_type_short}"
        self.has_entity_name = True
        self._attr_translation_key = f"energy_{self._meter_type_short}"
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = (
            UnitOfEnergy.KILO_WATT_HOUR
        )  # TODO: verify

    @property
    def native_value(self) -> int | None:
        """Return the metering delivered value."""
        metering_state = self._get_current_sensor_state()
        if not metering_state:
            return None
        return metering_state.value

    def _get_current_sensor_state(self) -> SensorState[int] | None:
        """Get current sensor state from coordinator."""
        device = self._get_current_device_state()
        if not device or not device.features.metering:
            return None
        match self._metering_type:
            case MeteringStateName.SUMMATION_RECEIVED:
                state = device.features.metering.states.summation_received
            case MeteringStateName.SUMMATION_DELIVERED:
                state = device.features.metering.states.summation_delivered
        if state is not None:
            self.last_updated = state.last_updated
        return state


class HomelyEnergyDemandSensor(HomelySensorBase, SensorEntity):
    """Energy demand sensor for Homely devices."""

    def __init__(
        self,
        coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        device: Device,
    ) -> None:
        """Initialize the energy demand sensor."""
        super().__init__(coordinator, location_id, device)
        self._attr_unique_id = f"{self.device_id}_energy_demand"
        self.has_entity_name = True
        self._attr_name = "Energy Demand"
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        """Return the energy demand value."""
        metering_state = self._get_current_sensor_state()
        if not metering_state:
            return None
        return metering_state.value

    def _get_current_sensor_state(self) -> SensorState[int] | None:
        """Get current sensor state from coordinator."""
        device = self._get_current_device_state()
        if not device or not device.features.metering:
            return None
        if (state := device.features.metering.states.demand) is not None:
            self.last_updated = state.last_updated
        return state


class HomelyThermostatSensor(HomelySensorBase):
    """Thermostat sensor for Homely devices.

    Api is read only, so implemented as temperature sensor, not climate control.
    """

    def __init__(
        self,
        coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        device: Device,
    ) -> None:
        """Initialize the thermostat sensor."""
        super().__init__(coordinator, location_id, device)
        self._attr_unique_id = f"{self.device_id}_thermostat"
        self.has_entity_name = True
        self._attr_translation_key = "thermostat"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return the temperature value."""
        temperature_state = self._get_current_sensor_state()
        if not temperature_state:
            return None
        return temperature_state.value

    def _get_current_sensor_state(self) -> SensorState[float] | None:
        """Get current sensor state from coordinator."""
        device = self._get_current_device_state()
        if not device or not device.features.thermostat:
            return None
        temperature_state = device.features.thermostat.states.local_temperature
        if not temperature_state:
            temperature_state = getattr(
                device.features.thermostat.states, "temperature", None
            )
        if temperature_state is not None:
            self.last_updated = temperature_state.last_updated
        return temperature_state

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return additional state attributes."""
        existing_attrs = super().extra_state_attributes or {}
        attrs = dict(existing_attrs)
        device = self._get_current_device_state()
        if not device or not device.features.thermostat:
            return attrs
        thermostat_states = device.features.thermostat.states.model_dump()
        for key, value in thermostat_states.items():
            if key not in ["local_temperature", "temperature"] and value is not None:
                attrs[key] = value.value
        return attrs
