"""Support for Homely alarm control panel."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
)
from homeassistant.components.alarm_control_panel.const import AlarmControlPanelState
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HomelyDataUpdateCoordinator
from .models import AlarmState

_LOGGER = logging.getLogger(__name__)

_ALARM_STATE_MAP: dict[AlarmState, AlarmControlPanelState] = {
    AlarmState.DISARMED: AlarmControlPanelState.DISARMED,
    AlarmState.ARMED_AWAY: AlarmControlPanelState.ARMED_AWAY,
    AlarmState.ARMED_NIGHT: AlarmControlPanelState.ARMED_NIGHT,
    AlarmState.ARMED_PARTLY: AlarmControlPanelState.ARMED_HOME,
    AlarmState.BREACHED: AlarmControlPanelState.TRIGGERED,
    AlarmState.ALARM_PENDING: AlarmControlPanelState.PENDING,
    AlarmState.ALARM_STAY_PENDING: AlarmControlPanelState.ARMING,
    AlarmState.ARMED_NIGHT_PENDING: AlarmControlPanelState.ARMING,
    AlarmState.ARMED_AWAY_PENDING: AlarmControlPanelState.ARMING,
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
    _attr_supported_features = AlarmControlPanelEntityFeature(0)

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
        """Send disarm command — not yet implemented."""
        _LOGGER.warning("Disarm not yet supported by Homely integration")

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command — not yet implemented."""
        _LOGGER.warning("Arm away not yet supported by Homely integration")

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send arm home command — not yet implemented."""
        _LOGGER.warning("Arm home (partly) not yet supported by Homely integration")

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        """Send arm night command — not yet implemented."""
        _LOGGER.warning("Arm night not yet supported by Homely integration")
