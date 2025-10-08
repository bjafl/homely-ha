"""Homely API client for Home Assistant integration with WebSocket support."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any, Literal

import aiohttp
import socketio
from aiohttp import ClientResponse, ClientSession
from homeassistant.core import callback
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from socketio.exceptions import (
    ConnectionError as SocketIOConnectionError,
)
from socketio.exceptions import (
    DisconnectedError as SocketIODisconnectedError,
)

# import requests
# from requests import Response as HTTPResponse
from .const import HomelyUrls
from .exceptions import (
    HomelyAuthError,
    HomelyAuthExpiredError,
    HomelyAuthInvalidError,
    HomelyAuthRequestError,
    HomelyError,
    HomelyNetworkError,
    HomelyRequestError,
    HomelyStateUpdateLocationMismatchError,
    HomelyStateUpdateError,
    HomelyStateUpdateMissingTargetError,
    HomelyStateUpdateOutOfOrderError,
    HomelyValidationError,
    HomelyValueError,
    HomelyWebSocketError,
)
from .models import (
    APITokens,
    Device,
    Feature,
    HomeResponse,
    Location,
    SensorState,
    TokenResponse,
    WsAlarmChangeData,
    WsAlarmChangeEvent,
    WsDeviceChangeData,
    WsDeviceChangeEvent,
    WsEvent,
    WsEventAdapter,
)

_LOGGER = logging.getLogger(__name__)


type WebSocketEventHandler = Callable[[WsEvent | None], None]


def get_field(obj: BaseModel | dict[str, Any], name: str) -> Any:
    """Get a field value from a Pydantic model or dict by name or alias."""
    if isinstance(obj, dict):
        return obj.get(name)
    if hasattr(obj, name):
        return getattr(obj, name)
    obj_class = type(obj)
    field_name = next(
        (name for name, field in obj_class.model_fields.items() if field.alias == name),
        None,
    )
    if field_name:
        return getattr(obj, field_name)
    return None


class HomelyApi:
    """Homely API client with WebSocket support for real-time events."""

    def __init__(
        self,
        client_session: ClientSession,
        logger: logging.Logger | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize Homely API client."""
        self._logger = logger or _LOGGER
        self._request_timeout: int = kwargs.get("request_timeout", 20)
        self._locations: dict[str, Location] = {}
        self._auth: APITokens | None = None
        self._cached_credentials: dict[str, str] = {}
        self._client_session = client_session

    @property
    def locations(self) -> list[Location] | None:
        """Get cached locations."""
        if not self._locations or len(self._locations) == 0:
            return None
        return [loc.model_copy() for loc in self._locations.values()]

    @property
    def is_authenticated(self) -> bool:
        """Check if the client is authenticated, and the access token is valid."""
        return self._auth is not None and not self._auth.is_access_token_expired()

    @property
    def is_reauth_token_valid(self) -> bool:
        """Check if the client reauth token is valid."""
        return self._auth is not None and not self._auth.is_refresh_token_expired()

    @property
    def access_token(self) -> str | None:
        """Get the current access token if available."""
        if self.is_authenticated and self._auth:
            return self._auth.access_token
        return None

    async def get_access_token(
        self, auto_refresh: bool = True, auto_login: bool = False
    ) -> str:
        """Get a valid access token, refreshing if needed."""
        if not self.is_reauth_token_valid:
            if auto_login:
                await self._login()
            else:
                raise HomelyAuthExpiredError("Refresh token expired, login required")
        await self._ensure_token_valid(auto_refresh=auto_refresh)
        token = self.access_token
        if not token:
            raise HomelyAuthError(
                "No valid access token available"
            )  # should not happen
        return token

    async def _ensure_token_valid(self, auto_refresh: bool = True) -> None:
        """Check if the access token is valid and refresh if needed."""
        if self.is_authenticated:
            return
        if auto_refresh:
            if self.is_reauth_token_valid:
                await self.refresh_token()
            else:
                raise HomelyAuthError("Refresh token expired")
        else:
            raise HomelyAuthError("Access token expired")

    async def _get_auth_header(self) -> dict[str, str]:
        """Get authorization header with valid token."""
        await self._ensure_token_valid()
        return {"Authorization": f"Bearer {self.access_token}"}

    async def _make_request(
        self,
        request_type: Literal["get", "post"],
        url: str,
        include_token: bool = False,
        **kwargs: Any,
    ) -> ClientResponse:
        """Make HTTP request with optional authentication."""
        if include_token:
            kwargs.setdefault("headers", {}).update(await self._get_auth_header())
        try:
            async with asyncio.timeout(self._request_timeout):
                if request_type == "get":
                    response = await self._client_session.get(url, **kwargs)
                elif request_type == "post":
                    response = await self._client_session.post(url, **kwargs)
                else:
                    raise HomelyValueError(
                        f"Unexpected value for request_type: {request_type}"
                    )
                self._logger.debug("Response received: %s", response)
                return response
        except TimeoutError:
            raise HomelyNetworkError("Request timed out")
        except aiohttp.ClientError as e:
            raise HomelyNetworkError("Network error occurred") from e

    async def login(self, username: str, password: str) -> None:
        """Authenticate with Homely API using username and password."""
        self._cached_credentials = {"username": username, "password": password}
        await self._login(username=username, password=password)

    async def _login(self, **kwargs: Any) -> None:
        """Authenticate with Homely API."""
        username = kwargs.get("username", self._cached_credentials.get("username"))
        password = kwargs.get("password", self._cached_credentials.get("password"))
        if not username or not password:
            raise HomelyAuthInvalidError("Username and password required for login")
        response = await self._make_request(
            request_type="post",
            url=HomelyUrls.AUTH_LOGIN,
            json={"username": username, "password": password},
        )
        data = await response.json()
        if not response.ok:
            raise HomelyAuthRequestError("Login failed", data)
        token_response = TokenResponse(**data)
        self._auth = APITokens.from_token_response(token_response)

    async def refresh_token(self) -> None:
        """Refresh the access token using refresh token."""
        if not self._auth or not self._auth.refresh_token:
            raise HomelyAuthInvalidError("No refresh token available")
        if self._auth.is_refresh_token_expired():
            raise HomelyAuthExpiredError("Refresh token expired")
        response = await self._make_request(
            request_type="post",
            url=HomelyUrls.AUTH_REFRESH,
            json={"refresh_token": self._auth.refresh_token},
        )
        data = await response.json()
        if not response.ok:
            raise HomelyAuthRequestError("Token refresh failed", data)
        validated_data = TokenResponse(**data)
        self._auth = APITokens.from_token_response(validated_data)

    async def get_locations(self) -> list[Location]:
        """Get all locations accessible to the user."""
        await self._ensure_token_valid()
        response = await self._make_request(
            request_type="get", url=HomelyUrls.LOCATIONS, include_token=True
        )
        data = await response.json()
        if not response.ok:
            raise HomelyRequestError("Failed to get locations", data)
        try:
            locations = [Location(**loc) for loc in data]
            self._locations = {str(loc.location_id): loc for loc in locations}
        except PydanticValidationError as e:
            raise HomelyValidationError("Failed to parse location data", data) from e
        return self.locations or []

    async def get_location_id_names(self) -> dict[str, str]:
        """Get names of all locations accessible to the user."""
        locations = await self.get_locations()
        return {str(loc.location_id): loc.name for loc in locations}

    async def get_home(self, location_id: str) -> HomeResponse:
        """Get home status for a specific location."""
        response = await self._make_request(
            request_type="get",
            url=f"{HomelyUrls.HOME}/{location_id}",
            include_token=True,
        )
        data = await response.json()
        self._logger.debug("Json data from get_home response: %s", data)
        if not response.ok:
            raise HomelyRequestError("Failed to get home", data)
        try:
            home = HomeResponse(**data)
        except PydanticValidationError as e:
            raise HomelyValidationError("Failed to parse home response", data) from e
        return home


class HomelyHomeState(HomeResponse):
    """Represents the state of a Homely location.

    Extends HomeResponse with methods to update and handle Homely home state data.
    """

    @classmethod
    def from_ws_event(
        cls,
        previous_state: HomelyHomeState,
        event: WsEvent,
        ignore_missing_states: bool = False,
        ignore_outdated_values: bool = True,
        ignore_unhandled_event_types: bool = False,
    ) -> HomelyHomeState:
        """Create copy of HomelyHomeState and apply updates from a WebSocket event."""
        new_state = previous_state.model_copy()
        new_state.update_state(
            event,
            ignore_missing_states=ignore_missing_states,
            ignore_outdated_values=ignore_outdated_values,
            ignore_unhandled_event_types=ignore_unhandled_event_types,
        )
        return new_state

    @classmethod
    def from_response(cls, response: HomeResponse) -> HomelyHomeState:
        """Create HomelyHomeState from HomeResponse."""
        return cls.model_validate(response.model_dump(by_alias=True))

    def get_device(self, device_id: str) -> Device | None:
        """Get a device by its ID.

        Args:
            device_id: The ID (uuid as string) of the device to retrieve.

        Returns:
            The Device object if found, otherwise None.
        """
        return next((dev for dev in self.devices if str(dev.id) == device_id), None)

    def get_device_feature_state(
        self, device_id: str, feature_name: str, state_name: str
    ) -> SensorState | None:
        """Get the SensorState of a specific feature on a device.

        Args:
            device_id: The ID (uuid as string) of the device.
            feature_name: The name of the feature to look for.
            state_name: The name of the state within the feature.

        Returns:
            The SensorState object if found, otherwise None.
        """
        device = self.get_device(device_id)
        try:
            feature: Feature | None = (
                get_field(device.features, feature_name) if device else None
            )
            return get_field(feature.states, state_name) if feature else None
        except AttributeError:
            return None

    def update_state(
        self,
        event: WsEvent,
        ignore_missing_states: bool = False,
        ignore_outdated_values: bool = True,
        ignore_unhandled_event_types: bool = False,
    ) -> None:
        """Update the home state based on WebSocket event data."""
        if isinstance(event, WsDeviceChangeEvent):
            self._process_ws_device_state_update(
                event.data, ignore_missing_states, ignore_outdated_values
            )
        elif isinstance(event, WsAlarmChangeEvent):
            self._process_ws_alarm_state_update(event.data)
        else:
            if not ignore_unhandled_event_types:
                raise HomelyStateUpdateError(
                    f"Cannot process event type {event.type}"
                    + " - unhandled or unknown event type"
                )

    def _process_ws_device_state_update(
        self,
        update_data: WsDeviceChangeData,
        ignore_missing_states: bool = False,
        ignore_outdated_values: bool = True,
    ) -> None:
        """Update device state based on device change event data."""
        # Validate location ID
        location_id = str(update_data.root_location_id)
        if location_id != str(self.location_id):
            raise HomelyStateUpdateLocationMismatchError(
                f"Location ID {location_id} in update does not match"
                + f" location ID {self.location_id} of this home state"
            )
        # Find target state to update
        device_id = str(update_data.device_id)
        target_device = self.get_device(device_id)
        if not target_device:
            raise HomelyValueError(f"Device ID {device_id} not found in home state")
        for change in update_data.changes:
            target_state = self.get_device_feature_state(
                device_id, change.feature, change.state_name
            )
            if not target_state:
                if ignore_missing_states:
                    continue
                raise HomelyStateUpdateMissingTargetError(
                    f"Can't find existing {change.state_name} for feature {change.feature} on"
                    + f" device {device_id}. Update failed."
                )
            if (
                target_state.last_updated is not None
                and change.last_updated is not None
                and target_state.last_updated > change.last_updated
            ):
                if ignore_outdated_values:
                    continue
                raise HomelyStateUpdateOutOfOrderError(
                    f"Update for {change.state_name} on feature {change.feature} of device"
                    + f" {device_id} is out of order (older than current state). Update"
                    + " failed."
                )
            # Update target state
            target_state.value = change.value
            target_state.last_updated = change.last_updated

    def _process_ws_alarm_state_update(self, data: WsAlarmChangeData) -> None:
        raise NotImplementedError(
            "Alarm state change processing not implemented"
        )  # TODO


class HomelyWebSocketClient:
    """WebSocket client for Homely API real-time events."""

    def __init__(
        self,
        api: HomelyApi,
        location_id: str,
        logger: logging.Logger | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize WebSocket client for Homely location.

        Args:
            api: An authenticated HomelyApi instance.
            location_id: The ID of the location to connect to.
            logger: Optional logger instance.
            kwargs: Additional options:
                - name: Optional name for the WebSocket client.
                - max_reconnection_attempts: Max reconnection attempts (default 5).
                - socketio_logger: Optional logger for Socket.IO.
                - engineio_logger: Optional logger for Engine.IO.
        """
        self._api = api
        self._location_id = location_id
        self._websocket_event_callbacks: dict[str, list[WebSocketEventHandler]] = (
            defaultdict(list)
        )
        self._should_disconnect = False
        self._current_reconnection_attempt = 0
        self._logger = logger or _LOGGER
        self._name: str | None = kwargs.get("name", None)
        self._max_reconnection_attempts = kwargs.get("max_reconnection_attempts", 5)
        socketio_logger = kwargs.get("socketio_logger", None)
        if not isinstance(socketio_logger, logging.Logger):
            socketio_logger = logging.getLogger(
                f"{self._logger.name}.socketio_{self.name}"
            )
        engineio_logger = kwargs.get("engineio_logger", None)
        if not isinstance(engineio_logger, logging.Logger):
            engineio_logger = logging.getLogger(
                f"{self._logger.name}.engineio_{self.name}"
            )
        self._sio = socketio.AsyncClient(
            logger=socketio_logger,
            engineio_logger=engineio_logger,
        )

    @property
    def name(self) -> str:
        """Get the name of the WebSocket client."""
        return self._name or self._location_id

    @property
    def location_id(self) -> str:
        """Get the location ID the WebSocket client is associated with."""
        return self._location_id

    @property
    def connected(self) -> bool:
        """Check if the WebSocket client is connected."""
        return bool(self._sio and self._sio.connected)

    async def connect(self) -> None:
        """Connect to WebSocket for real-time events."""
        try:
            auth_header = await self._api._get_auth_header()
            token = self._api.access_token
            if not token:
                raise HomelyAuthError("HomelyApi failed to provide access token")
        except HomelyError as e:
            self._logger.error(
                f"WebSocket {self.name}: error getting auth from HomelyApi",
                exc_info=True,
            )
            raise HomelyWebSocketError(
                "Failed to get authentication token for WebSocket"
            ) from e

        location_id = str(self._location_id)
        url = f"{HomelyUrls.WEBSOCKET}?locationId={location_id}&token=Bearer%20{token}"
        headers = {**auth_header, "locationId": location_id}

        self._setup_sio_events()
        try:
            await self._sio.connect(url, headers=headers)
            if not self._sio.connected:
                self._logger.error(
                    f"WebSocket {self.name}: failed connection check after connect."
                )
                raise HomelyWebSocketError("Failed to connect to WebSocket")
        except (SocketIOConnectionError, SocketIODisconnectedError) as e:
            self._logger.error(
                f"WebSocket {self.name}: connection error", exc_info=True
            )
            raise HomelyWebSocketError("Failed to connect to WebSocket") from e
        except ValueError as e:
            self._logger.error(
                f"WebSocket {self.name}: invalid connection parameters", exc_info=True
            )
            raise HomelyWebSocketError("Invalid connection parameters") from e
        except TimeoutError as e:
            self._logger.error(
                f"WebSocket {self.name}: connection timed out", exc_info=True
            )
            raise HomelyWebSocketError("WebSocket connection timed out") from e
        except HomelyWebSocketError:
            raise
        except Exception as e:
            self._logger.error(
                f"WebSocket {self.name}: unexpected error during connect", exc_info=True
            )
            raise HomelyWebSocketError(
                "Unexpected error during WebSocket connect"
            ) from e

    async def _try_reconnect(self, timeout: int = 5) -> bool:
        """Attempt to reconnect the WebSocket."""
        if self._should_disconnect:
            return False
        self._current_reconnection_attempt += 1
        if self._current_reconnection_attempt > self._max_reconnection_attempts:
            self._should_disconnect = True
            return False
        self._logger.info(f"Trying to reconnect WebSocket {self.name}")
        await asyncio.sleep(timeout)
        await self.connect()
        return True

    def _setup_sio_events(self) -> None:
        """Set up Socket.IO event handlers."""

        @callback
        @self._sio.event  # type: ignore[misc]
        def connect() -> None:
            self._logger.info(f"WebSocket {self.name}: connected")
            self._handle_event("connect")

        @callback
        @self._sio.event  # type: ignore[misc]
        def disconnect() -> None:
            self._logger.info(f"WebSocket {self.name}: disconnected")
            self._handle_event("disconnect")

        @callback
        @self._sio.event  # type: ignore[misc]
        def event(data: dict[str, Any]) -> None:
            self._logger.debug(
                "Homely event received on websocket %s: %s", self.name, data
            )
            try:
                ws_event = WsEventAdapter.validate_python(data)
                self._handle_event("event", ws_event)
            except PydanticValidationError:
                self._logger.error(
                    "Invalid WebSocket event data on websocket %s: %s",
                    self.name,
                    exc_info=True,
                )

    def register_event_callback(
        self,
        callback: WebSocketEventHandler,
        event_type: Literal["event", "connect", "disconnect"] = "event",
    ) -> None:
        """Register a callback for WebSocket events."""
        self._websocket_event_callbacks[event_type].append(callback)
        self._logger.debug(
            f"Registered callback for WebSocket {event_type} events at websocket {self.name}"
        )

    def unregister_event_callback(
        self,
        callback: WebSocketEventHandler,
        event_type: Literal["event", "connect", "disconnect"] | None = None,
    ) -> None:
        """Unregister a specific callback for WebSocket events."""
        selected_callbacks = [
            cb
            for ev_type, cbs in self._websocket_event_callbacks.items()
            for cb in cbs
            if not event_type or event_type == ev_type
        ]
        if callback in selected_callbacks:
            if event_type is None:
                for cbs in self._websocket_event_callbacks.values():
                    if callback in cbs:
                        cbs.remove(callback)
            else:
                self._websocket_event_callbacks[event_type].remove(callback)
            self._logger.debug(
                f"Unregistered callback {event_type or 'all'} events at websocket {self.name}"
            )

    @callback
    def _handle_event(
        self,
        event_type: Literal["event", "connect", "disconnect"],
        event_data: WsEvent | None = None,
    ) -> None:
        """Handle incoming WebSocket event and dispatch to registered callbacks."""
        selected_callbacks = self._websocket_event_callbacks.get(event_type, [])
        self._logger.debug(
            f"Dispatching {len(selected_callbacks)} callbacks for {event_type} event at websocket {self.name}"
        )
        for event_callback in selected_callbacks:
            try:
                if event_data and event_type == "event":
                    event_callback(event_data)
                else:
                    event_callback(None)
            except Exception:
                self._logger.error(
                    f"Error in event callback for {event_type} at websocket {self.name}",
                    exc_info=True,
                )

    async def disconnect(self) -> None:
        """Disconnect the WebSocket."""
        self._should_disconnect = True
        await self._sio.disconnect()

    async def wait(self) -> None:
        """Lock until WebSocket is disconnected."""
        if not self.connected:
            raise HomelyWebSocketError("Websocket not connected")
        while not self._should_disconnect:
            try:
                await self._sio.wait()
            except (SocketIODisconnectedError, SocketIOConnectionError):
                self._logger.error(
                    "WebSocket disconnected while waiting for response", exc_info=True
                )
                await self._try_reconnect()

    def __del__(self) -> None:
        """Best-effort cleanup warning."""
        if self._sio and self._sio.connected:
            self._logger.warning(
                "WebSocket not properly closed. Use 'async with' or call disconnect() explicitly."
            )
