"""Homely API client for Home Assistant integration with WebSocket support."""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
from collections import defaultdict
from collections.abc import Callable
from typing import Any, Literal

import aiohttp
from aiohttp import ClientResponse, ClientSession, ClientWebSocketResponse, WSMsgType
from homeassistant.core import callback
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

# import requests
# from requests import Response as HTTPResponse
from .const import APP_API_CLIENT_ID, APP_API_CLIENT_SECRET, HomelyUrls
from .exceptions import (
    HomelyAuthError,
    HomelyAuthExpiredError,
    HomelyAuthInvalidError,
    HomelyAuthRequestError,
    HomelyError,
    HomelyNetworkError,
    HomelyRateLimitError,
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
    Gateway,
    GatewayLogEntry,
    GatewayNetworks,
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
        request_type: Literal["get", "post", "patch"],
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
                elif request_type == "patch":
                    response = await self._client_session.patch(url, **kwargs)
                else:
                    raise HomelyValueError(
                        f"Unexpected value for request_type: {request_type}"
                    )
                self._logger.debug("Response received: %s", response)
                if response.status == 429:
                    try:
                        data = await response.json()
                        retry_after = int(data.get("retryAfter", 60))
                    except Exception:
                        retry_after = 60
                    raise HomelyRateLimitError(
                        f"Rate limited, retry after {retry_after}s", retry_after
                    )
                return response
        except HomelyRateLimitError:
            raise
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
            json={
                "client_id": APP_API_CLIENT_ID,
                "client_secret": APP_API_CLIENT_SECRET,
                "grant_type": "password",
                "username": username,
                "password": password,
            },
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
            json={
                "client_id": APP_API_CLIENT_ID,
                "client_secret": APP_API_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": self._auth.refresh_token,
            },
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
        """Get home status for a specific location.

        Combines /home/{id} (devices + gateway + location metadata) with
        /alarm/state/{id} (alarm state), as the app API splits these across
        two endpoints.
        """
        home_resp = await self._make_request(
            request_type="get",
            url=f"{HomelyUrls.HOME}/{location_id}",
            include_token=True,
        )
        if not home_resp.ok:
            try:
                err_data = await home_resp.json()
            except Exception:
                err_data = {}
            raise HomelyRequestError("Failed to get home", err_data)
        home_data = await home_resp.json()
        self._logger.debug("Json data from get_home response: %s", home_data)

        alarm_state: AlarmState | None = None
        try:
            alarm_resp = await self._make_request(
                request_type="get",
                url=f"{HomelyUrls.ALARM_STATE}/{location_id}",
                include_token=True,
            )
            if alarm_resp.ok:
                alarm_data = await alarm_resp.json()
                alarm_state = alarm_data.get("state")
            else:
                self._logger.warning(
                    "Alarm state unavailable for %s (HTTP %s)", location_id, alarm_resp.status
                )
        except HomelyRateLimitError:
            raise
        except HomelyError as err:
            self._logger.warning("Could not fetch alarm state for %s: %s", location_id, err)

        cached_location = self._locations.get(location_id)
        try:
            gateway_data = home_data.get("gateway")
            home = HomeResponse(
                location_id=home_data["location"]["id"],
                name=home_data["location"].get("name"),
                gateway_serial=(gateway_data or {}).get("serialNumber"),
                gateway=Gateway.model_validate(gateway_data) if gateway_data else None,
                remaining_pin_attempts=home_data.get("remainingPinAttempts"),
                alarm_state=alarm_state,
                user_role=cached_location.role if cached_location else None,
                devices=[Device.model_validate(d) for d in home_data.get("devices", [])],
            )
        except (PydanticValidationError, KeyError) as e:
            raise HomelyValidationError("Failed to parse home response", home_data) from e
        return home


    async def arm_alarm(self, location_id: str, alarm_profile: str) -> None:
        """Arm the alarm with the given profile (ARMED_AWAY / ARMED_NIGHT / ARMED_STAY)."""
        response = await self._make_request(
            request_type="post",
            url=HomelyUrls.ALARM_ARM,
            include_token=True,
            json={"locationId": location_id, "alarmProfile": alarm_profile},
        )
        if not response.ok:
            try:
                data = await response.json()
            except Exception:
                data = {}
            raise HomelyRequestError(
                f"Failed to arm alarm ({response.status})", data
            )

    async def disarm_alarm(self, location_id: str, pin: str) -> None:
        """Disarm the alarm with the user's PIN code."""
        response = await self._make_request(
            request_type="post",
            url=HomelyUrls.ALARM_DISARM,
            include_token=True,
            json={"pin": pin, "locationId": location_id},
        )
        if not response.ok:
            try:
                data = await response.json()
            except Exception:
                data = {}
            raise HomelyRequestError(
                f"Failed to disarm alarm ({response.status})", data
            )


    async def get_gateway_networks(self, gateway_id: str) -> GatewayNetworks | None:
        """Return connectivity detail for the gateway (GSM / Wi-Fi)."""
        response = await self._make_request(
            request_type="get",
            url=f"{HomelyUrls.GATEWAYS}/{gateway_id}/networks",
            include_token=True,
        )
        if not response.ok:
            _LOGGER.warning("Gateway networks fetch failed (%s)", response.status)
            return None
        return GatewayNetworks.model_validate(await response.json())

    async def get_gateway_log(self, gateway_id: str) -> list[GatewayLogEntry]:
        """Return history-log entries for the gateway."""
        response = await self._make_request(
            request_type="get",
            url=f"{HomelyUrls.GATEWAYS}/{gateway_id}/history-log",
            include_token=True,
        )
        if not response.ok:
            _LOGGER.warning("Gateway history-log fetch failed (%s)", response.status)
            return []
        data = await response.json()
        return [GatewayLogEntry.model_validate(e) for e in (data or [])]

    async def mark_gateway_log_read(self, gateway_id: str) -> None:
        """Mark all gateway history-log entries as acknowledged."""
        response = await self._make_request(
            request_type="patch",
            url=f"{HomelyUrls.GATEWAYS}/{gateway_id}/history-log",
            include_token=True,
            json={"acknowledgeAll": True},
        )
        if not response.ok:
            try:
                data = await response.json()
            except Exception:
                data = {}
            raise HomelyRequestError(
                f"Failed to mark gateway log as read ({response.status})", data
            )


class HomelyHomeState(HomeResponse):
    """Represents the state of a Homely location.

    Extends HomeResponse with methods to update and handle Homely home state data.
    """

    # Last alarm-state-changed event received over WebSocket (carries who/when).
    last_alarm_event: WsAlarmChangeData | None = None

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
        new_state = previous_state.model_copy(deep=True)
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
        # Only validate using rootLocationId; locationId may be a sub-location (room) UUID
        if update_data.root_location_id is not None and str(update_data.root_location_id) != str(self.location_id):
            raise HomelyStateUpdateLocationMismatchError(
                f"Root location ID {update_data.root_location_id} in update does not match"
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

    def _process_ws_alarm_state_update(self, update_data: WsAlarmChangeData) -> None:
        """Update alarm state based on alarm change event data."""
        location_id = str(update_data.location_id)
        if location_id != str(self.location_id):
            raise HomelyStateUpdateLocationMismatchError(
                f"Location ID {location_id} in update does not match"
                + f" location ID {self.location_id} of this home state"
            )
        self.alarm_state = update_data.state
        self.last_alarm_event = update_data


class HomelyWebSocketClient:
    """EIO=3 / Socket.IO v2 WebSocket client for Homely app API."""

    _WS_POLL_PATH = "/socket.io/"

    def __init__(
        self,
        api: HomelyApi,
        location_id: str,
        logger: logging.Logger | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize WebSocket client for a Homely location."""
        self._api = api
        self._location_id = location_id
        self._websocket_event_callbacks: dict[str, list[WebSocketEventHandler]] = (
            defaultdict(list)
        )
        self._should_disconnect = False
        self._logger = logger or _LOGGER
        self._name: str | None = kwargs.get("name", None)
        self._ws: ClientWebSocketResponse | None = None
        self._ping_interval: float = 25.0

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
        return self._ws is not None and not self._ws.closed

    async def connect(self) -> None:
        """Connect using EIO=3 (Socket.IO v2) direct WebSocket protocol."""
        try:
            await self._api._get_auth_header()
            token = self._api.access_token
            if not token:
                raise HomelyAuthError("HomelyApi failed to provide access token")
        except HomelyError as e:
            raise HomelyWebSocketError(
                "Failed to get authentication token for WebSocket"
            ) from e

        location_id = str(self._location_id)
        ws_base = HomelyUrls.WEBSOCKET.replace("https://", "wss://") + self._WS_POLL_PATH

        # Direct WebSocket — server auto-connects to namespace (no polling handshake)
        qs = urllib.parse.urlencode({
            "EIO": "3",
            "transport": "websocket",
            "locationId": location_id,
            "token": f"Bearer {token}",
        })
        ws_url = f"{ws_base}?{qs}"

        _connected = False
        try:
            async with asyncio.timeout(15):
                self._ws = await self._api._client_session.ws_connect(
                    ws_url,
                    headers={
                        "Origin": HomelyUrls.WEBSOCKET,
                        "Authorization": f"Bearer {token}",
                        "locationId": location_id,
                    },
                    autoping=False,
                )

            # EIO=3 open packet
            eio_open = await asyncio.wait_for(self._ws.receive(), timeout=10)
            if eio_open.type != WSMsgType.TEXT or not eio_open.data.startswith("0"):
                raise HomelyWebSocketError(
                    f"Expected EIO open packet, got: {eio_open.data!r}"
                )
            eio_data = json.loads(eio_open.data[1:])
            self._ping_interval = eio_data.get("pingInterval", 25000) / 1000

            # Server auto-connects us to the namespace — wait for '40'
            # Do NOT send our own '40'; sending it causes immediate server disconnect
            ns_auto = await asyncio.wait_for(self._ws.receive(), timeout=10)
            if not (ns_auto.type == WSMsgType.TEXT and ns_auto.data == "40"):
                raise HomelyWebSocketError(
                    f"Expected server namespace auto-connect '40', got: {ns_auto.data!r}"
                )

            # Authenticate within the namespace
            auth_payload = json.dumps(
                {"token": f"Bearer {token}", "locationId": location_id}
            )
            await self._ws.send_str(f'42["authentication",{auth_payload}]')
            auth_resp = await asyncio.wait_for(self._ws.receive(), timeout=10)
            if auth_resp.type != WSMsgType.TEXT or not auth_resp.data.startswith("42"):
                raise HomelyWebSocketError(
                    f"Unexpected auth response: {auth_resp.data!r}"
                )
            rest = auth_resp.data[2:]
            if rest and rest[0].isdigit():
                bracket = rest.index("[")
                rest = rest[bracket:]
            auth_inner = json.loads(rest)
            if not (auth_inner[0] == "authenticated" and auth_inner[1] == True):  # noqa: E712
                raise HomelyWebSocketError(
                    f"Authentication failed: {auth_resp.data!r}"
                )
            _connected = True

        except HomelyWebSocketError:
            raise
        except TimeoutError as e:
            raise HomelyWebSocketError("WebSocket connection timed out") from e
        except aiohttp.ClientError as e:
            raise HomelyWebSocketError("WebSocket connection error") from e
        except Exception as e:
            raise HomelyWebSocketError(
                f"Unexpected error during WebSocket connect: {e}"
            ) from e
        finally:
            if not _connected and self._ws and not self._ws.closed:
                await self._ws.close()
                self._ws = None

        self._logger.info("WebSocket %s: authenticated and connected (EIO=3)", self.name)
        self._handle_event("connect")

    def _parse_sio_packet(self, raw: str) -> tuple[str | None, WsEvent | None]:
        """Parse a Socket.IO event packet, return (ack_id, event).

        App API format: 42<id>["message", {"type": "...", "eventData": {...}}]
        """
        try:
            # Extract optional numeric ack ID between "42" and "["
            rest = raw[2:]
            ack_id: str | None = None
            if rest and rest[0].isdigit():
                bracket = rest.index("[")
                ack_id = rest[:bracket]
                rest = rest[bracket:]
            payload: list[Any] = json.loads(rest)
            event_name: str = payload[0]
            inner: Any = payload[1] if len(payload) > 1 else {}
        except (json.JSONDecodeError, IndexError, ValueError):
            self._logger.warning("WebSocket %s: malformed event: %r", self.name, raw)
            return None, None

        # App API wraps events in a "message" envelope
        if event_name == "message" and isinstance(inner, dict):
            event_type = inner.get("type", "")
            event_data = inner.get("eventData", {})
        else:
            event_type = event_name
            event_data = inner

        envelope = {"type": event_type, "data": event_data}
        try:
            return ack_id, WsEventAdapter.validate_python(envelope)
        except PydanticValidationError:
            self._logger.debug(
                "WebSocket %s: unrecognised event type %r", self.name, event_type
            )
            return ack_id, None

    def register_event_callback(
        self,
        callback: WebSocketEventHandler,
        event_type: Literal["event", "connect", "disconnect"] = "event",
    ) -> None:
        """Register a callback for WebSocket events."""
        self._websocket_event_callbacks[event_type].append(callback)

    def unregister_event_callback(
        self,
        callback: WebSocketEventHandler,
        event_type: Literal["event", "connect", "disconnect"] | None = None,
    ) -> None:
        """Unregister a specific callback for WebSocket events."""
        for ev_type, cbs in self._websocket_event_callbacks.items():
            if event_type is None or ev_type == event_type:
                if callback in cbs:
                    cbs.remove(callback)

    @callback
    def _handle_event(
        self,
        event_type: Literal["event", "connect", "disconnect"],
        event_data: WsEvent | None = None,
    ) -> None:
        """Dispatch a WebSocket event to all registered callbacks."""
        for event_callback in self._websocket_event_callbacks.get(event_type, []):
            try:
                event_callback(event_data if event_type == "event" else None)
            except Exception:
                self._logger.error(
                    "Error in %s callback on websocket %s",
                    event_type, self.name, exc_info=True,
                )

    async def disconnect(self) -> None:
        """Disconnect the WebSocket."""
        self._should_disconnect = True
        if self._ws and not self._ws.closed:
            await self._ws.close()

    async def wait(self) -> None:
        """Listen for events until disconnected."""
        if not self.connected:
            self._handle_event("disconnect")
            return

        ping_task = asyncio.create_task(self._heartbeat_loop())
        try:
            assert self._ws is not None
            async for msg in self._ws:
                if self._should_disconnect:
                    break
                if msg.type == WSMsgType.TEXT:
                    data = msg.data
                    if data == "2":  # EIO=3 server ping — must pong
                        await self._ws.send_str("3")
                    elif data == "3":  # EIO=3 pong (response to our ping)
                        pass
                    elif data == "41":  # Socket.IO namespace disconnect
                        self._logger.warning(
                            "WebSocket %s: server namespace disconnect", self.name
                        )
                        break
                    elif data.startswith("42"):  # Socket.IO event
                        ack_id, ws_event = self._parse_sio_packet(data)
                        if ack_id:
                            await self._ws.send_str(f"43{ack_id}[]")
                        if ws_event:
                            self._handle_event("event", ws_event)
                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    self._logger.warning(
                        "WebSocket %s: connection dropped (%s)", self.name, msg.type
                    )
                    break
        except Exception:
            self._logger.error(
                "WebSocket %s: error in listen loop", self.name, exc_info=True
            )
        finally:
            ping_task.cancel()
            if not self._should_disconnect:
                self._handle_event("disconnect")

    async def _heartbeat_loop(self) -> None:
        """Send EIO=3 pings to keep the connection alive."""
        while self.connected and not self._should_disconnect:
            await asyncio.sleep(self._ping_interval)
            if self.connected:
                try:
                    await self._ws.send_str("2")  # type: ignore[union-attr]
                except Exception:
                    break
