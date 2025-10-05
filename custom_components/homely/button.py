"""Button entities for Homely integration."""

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.homely.homely_api import HomelyHomeState

from .const import DOMAIN
from .coordinator import HomelyDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button entity."""
    coordinator: HomelyDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = []
    for location_id in coordinator.selected_location_ids:
        home_state = coordinator.get_home_state(location_id)
        if home_state is not None:
            entities.append(RefreshButton(coordinator, location_id, home_state))

    async_add_entities(entities)


class RefreshButton(CoordinatorEntity, ButtonEntity):
    """Button entity to refresh API data."""

    def __init__(
        self,
        coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        home_state: HomelyHomeState,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)

        self._attr_name = "Trigger Refresh"
        self._attr_unique_id = f"{location_id}_refresh"
        self._attr_icon = "mdi:refresh"
        self.location_id = location_id

    @property
    def device_info(self) -> dr.DeviceInfo:
        """Return device info."""
        return dr.DeviceInfo(identifiers={(DOMAIN, self.location_id)})

    async def async_press(self) -> None:
        """Handle the button press - trigger coordinator refresh."""
        await self.coordinator.async_request_refresh()
