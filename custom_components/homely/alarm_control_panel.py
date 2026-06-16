"""Support for Homely alarm control panel."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    CodeFormat,
)
from homeassistant.components.alarm_control_panel.const import AlarmControlPanelState
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HomelyDataUpdateCoordinator
from .exceptions import HomelyError
from .models import AlarmState

_LOGGER = logging.getLogger(__name__)

_ALARM_STATE_MAP: dict[AlarmState, AlarmControlPanelState] = {
    AlarmState.DISARMED: AlarmControlPanelState.DISARMED,
    AlarmState.ARMED_AWAY: AlarmControlPanelState.ARMED_AWAY,
    AlarmState.ARMED_NIGHT: AlarmControlPanelState.ARMED_NIGHT,
    AlarmState.ARMED_STAY: AlarmControlPanelState.ARMED_HOME,
    AlarmState.ARMED_PARTLY: AlarmControlPanelState.ARMED_HOME,  # SDK alias for stay
    AlarmState.BREACHED: AlarmControlPanelState.TRIGGERED,
    # Exit/arming delay -> ARMING
    AlarmState.ARM_PENDING: AlarmControlPanelState.ARMING,
    AlarmState.ARM_NIGHT_PENDING: AlarmControlPanelState.ARMING,
    AlarmState.ARM_STAY_PENDING: AlarmControlPanelState.ARMING,
    AlarmState.ARMED_NIGHT_PENDING: AlarmControlPanelState.ARMING,  # SDK legacy
    AlarmState.ARMED_AWAY_PENDING: AlarmControlPanelState.ARMING,  # SDK legacy
    # Entry delay (alarm pending before breach) -> PENDING
    AlarmState.ALARM_PENDING: AlarmControlPanelState.PENDING,
    AlarmState.ALARM_STAY_PENDING: AlarmControlPanelState.PENDING,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homely alarm control panel based on a config entry."""
    coordinator: HomelyDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    if not coordinator.selected_location_ids:
        return

    entities = [
        HomelyAlarmControlPanel(coordinator, location_id, home_state)
        for location_id, home_state in coordinator.data.items()
        if location_id in coordinator.selected_location_ids
    ]
    async_add_entities(entities)


class HomelyAlarmControlPanel(
    CoordinatorEntity[HomelyDataUpdateCoordinator], AlarmControlPanelEntity
):
    """Alarm control panel entity for a Homely location."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_code_arm_required = False  # Homely only requires PIN to disarm, not to arm
    _attr_code_format = CodeFormat.NUMBER
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.ARM_NIGHT
    )

    def __init__(
        self,
        coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        home_state: Any,
    ) -> None:
        """Initialize the alarm control panel."""
        super().__init__(coordinator)
        self._location_id = location_id
        self._attr_unique_id = f"{location_id}_alarm_panel"
        self._device_name = home_state.name
        self._device_serial = home_state.gateway_serial

    @property
    def device_info(self) -> dr.DeviceInfo:
        """Return device info — shares device with the alarm state sensor."""
        return dr.DeviceInfo(
            identifiers={(DOMAIN, self._location_id)},
            name=self._device_name,
            model="Homely Alarm Gateway",
            serial_number=self._device_serial,
            manufacturer="Homely",
        )

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the current alarm state."""
        home_state = self.coordinator.get_home_state(self._location_id)
        if not home_state or not home_state.alarm_state:
            return None
        ha_state = _ALARM_STATE_MAP.get(home_state.alarm_state)
        if ha_state is None:
            _LOGGER.warning("Unknown Homely alarm state: %s", home_state.alarm_state)
        return ha_state

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Disarm the alarm. Requires the Homely PIN as code."""
        if not code:
            _LOGGER.error("Homely disarm requires a PIN code")
            return
        try:
            await self.coordinator.api.disarm_alarm(self._location_id, code)
        except HomelyError as err:
            _LOGGER.error("Failed to disarm Homely alarm: %s", err)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Arm alarm in away mode."""
        try:
            await self.coordinator.api.arm_alarm(self._location_id, "ARMED_AWAY")
        except HomelyError as err:
            _LOGGER.error("Failed to arm Homely alarm (away): %s", err)

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Arm alarm in home (partly) mode."""
        try:
            await self.coordinator.api.arm_alarm(self._location_id, "ARMED_STAY")
        except HomelyError as err:
            _LOGGER.error("Failed to arm Homely alarm (home): %s", err)

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        """Arm alarm in night mode."""
        try:
            await self.coordinator.api.arm_alarm(self._location_id, "ARMED_NIGHT")
        except HomelyError as err:
            _LOGGER.error("Failed to arm Homely alarm (night): %s", err)
