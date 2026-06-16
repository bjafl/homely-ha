"""Support for Homely arm/disarm events (who/when, from the WS stream)."""

from __future__ import annotations

import logging

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import HomelyDataUpdateCoordinator
from .const import DOMAIN
from .homely_api import HomelyHomeState
from .models import AlarmState

_LOGGER = logging.getLogger(__name__)

# Only final alarm states map to an action event; transitional ARM*_PENDING
# states (which also lack user info) are intentionally ignored.
_STATE_TO_EVENT: dict[AlarmState, str] = {
    AlarmState.DISARMED: "disarmed",
    AlarmState.ARMED_AWAY: "armed_away",
    AlarmState.ARMED_NIGHT: "armed_night",
    AlarmState.ARMED_STAY: "armed_home",
    AlarmState.ARMED_PARTLY: "armed_home",
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homely event entities based on a config entry."""
    coordinator: HomelyDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    if not coordinator.selected_location_ids:
        return
    entities = [
        HomelyAlarmEventEntity(coordinator, location_id, home_state)
        for location_id, home_state in coordinator.data.items()
        if location_id in coordinator.selected_location_ids
    ]
    async_add_entities(entities)


class HomelyAlarmEventEntity(
    CoordinatorEntity[HomelyDataUpdateCoordinator], EventEntity
):
    """Fires an event each time the alarm is armed or disarmed."""

    _attr_has_entity_name = True
    _attr_translation_key = "alarm_action"
    _attr_event_types = ["disarmed", "armed_away", "armed_night", "armed_home"]
    _attr_icon = "mdi:shield-account"

    def __init__(
        self,
        coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        home_state: HomelyHomeState,
    ) -> None:
        """Initialize the alarm action event entity."""
        super().__init__(coordinator)
        self._location_id = location_id
        self._device_serial = home_state.gateway_serial
        self._device_name = home_state.name
        self._attr_unique_id = f"{location_id}_alarm_action"
        # Don't replay an event that already happened before this entity existed.
        self._last_fired_key = self._event_key(home_state)

    @property
    def device_info(self) -> dr.DeviceInfo:
        """Attach to the gateway/alarm device."""
        return dr.DeviceInfo(
            identifiers={(DOMAIN, self._location_id)},
            name=self._device_name,
            model="Homely Alarm Gateway",
            serial_number=self._device_serial,
            manufacturer="Homely",
        )

    @staticmethod
    def _event_key(home_state: HomelyHomeState | None) -> object | None:
        """Return a stable identity for the last alarm event, or None."""
        event = home_state.last_alarm_event if home_state else None
        if event is None:
            return None
        if event.event_id is not None:
            return event.event_id
        return event.timestamp.isoformat() if event.timestamp else None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Fire an action event when a new arm/disarm is observed over WS."""
        home = self.coordinator.get_home_state(self._location_id)
        event = home.last_alarm_event if home else None
        if event is None:
            return
        key = self._event_key(home)
        if key == self._last_fired_key:
            return
        event_type = _STATE_TO_EVENT.get(event.state)
        if event_type is None:
            return  # transitional/unknown state — nothing actionable to report
        self._last_fired_key = key
        self._trigger_event(
            event_type,
            {
                "user_name": event.user_name,
                "user_id": str(event.user_id) if event.user_id else None,
                "state": event.state.value,
            },
        )
        self.async_write_ha_state()
