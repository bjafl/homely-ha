"""Button entities for Homely integration."""

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.homely.homely_api import HomelyApi, HomelyHomeState
from .models import Gateway

from .const import DOMAIN
from .coordinator import GatewayExtrasCoordinator, HomelyDataUpdateCoordinator


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
        if home_state is None:
            continue
        entities.append(RefreshButton(coordinator, location_id, home_state))
        extras = coordinator.gateway_extras_coordinators.get(location_id)
        gateway = getattr(home_state, "gateway", None)
        if extras is not None and gateway is not None:
            entities.append(
                GatewayExtrasRefreshButton(extras, coordinator, location_id, gateway)
            )
            entities.append(
                GatewayMarkLogReadButton(
                    extras, coordinator, location_id, gateway, coordinator.api
                )
            )

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


class _GatewayExtrasButtonBase(CoordinatorEntity["GatewayExtrasCoordinator"], ButtonEntity):
    """Base for buttons that operate on gateway extras (slow-poll data)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        extras_coordinator: "GatewayExtrasCoordinator",
        main_coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        gateway: "Gateway",
    ) -> None:
        super().__init__(extras_coordinator)
        self._main_coordinator = main_coordinator
        self._location_id = location_id
        self._gateway_serial = gateway.serial_number

    @property
    def device_info(self) -> dr.DeviceInfo:
        return dr.DeviceInfo(
            identifiers={(DOMAIN, self._location_id)},
            manufacturer="Homely",
            model="Homely Alarm Gateway",
            serial_number=self._gateway_serial,
        )


class GatewayExtrasRefreshButton(_GatewayExtrasButtonBase):
    """Trigger an immediate refresh of gateway extras (networks + log)."""

    def __init__(
        self,
        extras_coordinator: "GatewayExtrasCoordinator",
        main_coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        gateway: "Gateway",
    ) -> None:
        super().__init__(extras_coordinator, main_coordinator, location_id, gateway)
        self._attr_unique_id = f"{location_id}_gateway_extras_refresh"
        self._attr_translation_key = "gateway_extras_refresh"
        self._attr_icon = "mdi:refresh"

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()


class GatewayMarkLogReadButton(_GatewayExtrasButtonBase):
    """Mark all gateway history-log entries as acknowledged."""

    def __init__(
        self,
        extras_coordinator: "GatewayExtrasCoordinator",
        main_coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        gateway: "Gateway",
        api: "HomelyApi",
    ) -> None:
        super().__init__(extras_coordinator, main_coordinator, location_id, gateway)
        self._api = api
        self._attr_unique_id = f"{location_id}_gateway_mark_log_read"
        self._attr_translation_key = "gateway_mark_log_read"
        self._attr_icon = "mdi:bell-check"

    async def async_press(self) -> None:
        await self._api.mark_gateway_log_read(self._gateway_serial)
        await self.coordinator.async_request_refresh()
