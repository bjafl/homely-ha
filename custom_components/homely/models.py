"""Data structures and validation for Homely API interaction."""

import logging
import re
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, TypeAdapter

_LOGGER = logging.getLogger(__name__)

# Custom types
type StateValue = bool | int | float | str


class AlarmState(str, Enum):
    """Possible alarm states for Homely system.

    Values are grounded in captured app-API (api.homely.no) traffic and the
    documented SDK API (sdk.iotiliti.cloud). Arming (exit-delay) states use the
    ARM_*_PENDING family; entry-delay states use the ALARM_*_PENDING family.
    """

    DISARMED = "DISARMED"
    ARMED_AWAY = "ARMED_AWAY"
    ARMED_NIGHT = "ARMED_NIGHT"
    ARMED_STAY = "ARMED_STAY"
    # SDK API alias for stay/home mode — kept so either API value is accepted.
    ARMED_PARTLY = "ARMED_PARTLY"
    BREACHED = "BREACHED"
    # App API (api.homely.no) arming/exit-delay states
    ARM_PENDING = "ARM_PENDING"
    ARM_NIGHT_PENDING = "ARM_NIGHT_PENDING"
    ARM_STAY_PENDING = "ARM_STAY_PENDING"
    # Entry-delay states (alarm pending before breach)
    ALARM_PENDING = "ALARM_PENDING"
    ALARM_STAY_PENDING = "ALARM_STAY_PENDING"
    # SDK API legacy arming states — kept for compatibility
    ARMED_NIGHT_PENDING = "ARMED_NIGHT_PENDING"
    ARMED_AWAY_PENDING = "ARMED_AWAY_PENDING"
    # Fallback for any value not yet known to this integration.
    UNKNOWN = "UNKNOWN"

    @classmethod
    def _missing_(cls, value: object) -> "AlarmState":
        """Best-effort map an unrecognized state instead of raising.

        A streamed alarm state must never crash or silently drop the update.
        Unknown values are surfaced (with a warning) and classified by pattern
        so a future Homely state still yields a sensible HA state:
          ALARM*PENDING -> entry delay   (ALARM_PENDING)
          ARM*PENDING   -> arming/exit   (ARM_PENDING)
          ARMED*        -> armed          (ARMED_AWAY)
          otherwise     -> UNKNOWN
        """
        text = str(value).upper()
        # ALARM* must be checked before ARM* since "ALARM" contains "ARM".
        if re.search(r"ALARM.*PENDING", text):
            guess = cls.ALARM_PENDING
        elif re.search(r"ARM.*PENDING", text):
            guess = cls.ARM_PENDING
        elif "ARMED" in text:
            guess = cls.ARMED_AWAY
        else:
            guess = cls.UNKNOWN
        _LOGGER.warning(
            "Unknown Homely alarm state %r — best-effort mapping to %s. "
            "Please report so it can be handled explicitly.",
            value,
            guess.value,
        )
        return guess


class UserRole(str, Enum):
    """User roles at a Homely location."""

    ADMIN = "ADMIN"
    OWNER = "OWNER"


# Authentication Models
class AuthRequest(BaseModel):
    """Authentication request for Homely API login."""

    username: Annotated[
        str, Field(description="Same email address as used in the Homely app")
    ]
    password: Annotated[
        str, Field(description="Same password as used in the Homely app")
    ]


class TokenResponse(BaseModel):
    """OAuth token response from Homely API."""

    access_token: Annotated[str, Field(description="Access token for API requests")]
    expires_in: Annotated[int, Field(description="Token expiration time in seconds")]
    refresh_expires_in: Annotated[
        int | None, Field(description="Refresh token expiration time in seconds")
    ] = None
    refresh_token: Annotated[
        str, Field(description="Refresh token for obtaining new access tokens")
    ]
    token_type: str = "bearer"
    scope: str = ""
    session_state: str | None = None
    not_before_policy: Annotated[int | None, Field(alias="not-before-policy")] = None


class RefreshTokenRequest(BaseModel):
    """Request to refresh an access token."""

    refresh_token: str


# Location Models
class Location(BaseModel):
    """Homely location/gateway information."""

    name: Annotated[str, Field(description="User defined name for the location")]
    role: Annotated[
        UserRole,
        Field(description="User's role at the location/gateway"),
        BeforeValidator(lambda v: v.upper()),
    ]
    user_id: Annotated[
        UUID | None, Field(alias="userId", description="Unique ID for the user")
    ] = None
    location_id: Annotated[
        UUID, Field(alias="locationId", description="Unique ID for the location")
    ]
    gateway_serial: Annotated[
        str | None,
        Field(alias="gatewayserial", description="Serial number for the gateway"),
    ] = None
    partner_code: Annotated[
        int | None,
        Field(alias="partnerCode", description="Dev partner id?"),
    ] = None


# T = TypeVar('T', bound=StateValue)


# Sensor State Models
class SensorState[T = StateValue](BaseModel):
    """Generic sensor state with value and last updated timestamp."""

    model_config = ConfigDict(extra="allow")

    value: T | None = None
    last_updated: Annotated[datetime | None, Field(alias="lastUpdated")] = None


class AlarmStates(BaseModel):
    """Collection of alarm-related sensor states."""

    model_config = ConfigDict(extra="allow")

    alarm: SensorState[bool] | None = None
    tamper: SensorState[bool] | None = None
    flood: SensorState[bool] | None = None
    fire: SensorState[bool] | None = None


class TemperatureStates(BaseModel):
    """Collection of temperature sensor states."""

    model_config = ConfigDict(extra="allow")

    temperature: SensorState[float] | None = None
    # local_temperature: Annotated[
    #     SensorState | None, Field(alias="localTemperature")
    # ] = None  # For ELKO thermostat


class BatteryStates(BaseModel):
    """Collection of battery sensor states."""

    model_config = ConfigDict(extra="allow")

    low: SensorState[bool] | None = None
    defect: SensorState[bool] | None = None
    voltage: SensorState[float] | None = None


class DiagnosticStates(BaseModel):
    """Collection of diagnostic sensor states."""

    model_config = ConfigDict(extra="allow")

    network_link_strength: Annotated[
        SensorState[int] | None, Field(alias="networklinkstrength")
    ] = None
    network_link_address: Annotated[
        SensorState[str] | None, Field(alias="networklinkaddress")
    ] = None
    signal_strength: Annotated[
        SensorState[int] | None, Field(alias="signalStrength")
    ] = None
    online: SensorState[bool] | None = None
    tamper: SensorState[bool] | None = None


class MeteringStates(BaseModel):
    """Collection of energy metering sensor states."""

    model_config = ConfigDict(extra="allow")

    summation_delivered: Annotated[
        SensorState[int] | None, Field(alias="summationdelivered")
    ] = None
    summation_received: Annotated[
        SensorState[int] | None, Field(alias="summationreceived")
    ] = None
    demand: SensorState[int] | None = None
    check: SensorState[bool] | None = None


class ThermostatStates(BaseModel):
    """Collection of thermostat sensor states."""

    model_config = ConfigDict(extra="allow")

    local_temperature: Annotated[
        SensorState[float] | None, Field(alias="LocalTemperature")
    ] = None
    abs_min_heat_setpoint_limit: Annotated[
        SensorState | None, Field(alias="AbsMinHeatSetpointLimit")
    ] = None
    abs_max_heat_setpoint_limit: Annotated[
        SensorState | None, Field(alias="AbsMaxHeatSetpointLimit")
    ] = None
    occupied_cooling_setpoint: Annotated[
        SensorState | None, Field(alias="OccupiedCoolingSetpoint")
    ] = None
    occupied_heating_setpoint: Annotated[
        SensorState | None, Field(alias="OccupiedHeatingSetpoint")
    ] = None
    control_sequence_of_operation: Annotated[
        SensorState | None, Field(alias="ControlSequenceOfOperation")
    ] = None
    system_mode: Annotated[SensorState | None, Field(alias="SystemMode")] = None


# Feature Models
class FeatureName(str, Enum):
    """Available device feature types."""

    ALARM = "alarm"
    TEMPERATURE = "temperature"
    BATTERY = "battery"
    DIAGNOSTIC = "diagnostic"
    METERING = "metering"
    THERMOSTAT = "thermostat"
    SIREN = "siren"


class AlarmFeature(BaseModel):
    """Alarm feature container."""

    states: AlarmStates


class TemperatureFeature(BaseModel):
    """Temperature feature container."""

    states: TemperatureStates


class BatteryFeature(BaseModel):
    """Battery feature container."""

    states: BatteryStates


class DiagnosticFeature(BaseModel):
    """Diagnostic feature container."""

    states: DiagnosticStates


class MeteringFeature(BaseModel):
    """Energy metering feature container."""

    states: MeteringStates


class ThermostatFeature(BaseModel):
    """Thermostat feature container."""

    states: ThermostatStates


class SirenStates(BaseModel):
    """Collection of siren states."""

    model_config = ConfigDict(extra="allow")

    alarm: SensorState[bool] | None = None
    acmains: SensorState[bool] | None = None
    battery: SensorState[bool] | None = None
    tamper: SensorState[bool] | None = None


class SirenFeature(BaseModel):
    """Siren feature container."""

    states: SirenStates


class PanelStates(BaseModel):
    """Collection of keypad/panel states."""

    model_config = ConfigDict(extra="allow")

    tamper: SensorState[bool] | None = None
    battery: SensorState[bool] | None = None


class PanelFeature(BaseModel):
    """Keypad/panel feature container."""

    states: PanelStates


class DeviceFeatures(BaseModel):
    """Collection of all possible device features."""

    alarm: AlarmFeature | None = None
    temperature: TemperatureFeature | None = None
    battery: BatteryFeature | None = None
    diagnostic: DiagnosticFeature | None = None
    metering: MeteringFeature | None = None
    thermostat: ThermostatFeature | None = None
    siren: SirenFeature | None = None
    panel: PanelFeature | None = None


# Device Models
class Device(BaseModel):
    """Homely device with all features and states."""

    id: Annotated[UUID, Field(description="Unique ID for the device")]
    name: Annotated[
        str | None, Field(description="User defined name for the device")
    ] = None
    serial_number: Annotated[
        str | None,
        Field(alias="serialNumber", description="Serial number for the device"),
    ] = None
    location: Annotated[
        str | None, Field(description="Floor and room name if set for the device")
    ] = None
    online: Annotated[bool, Field(description="Device online status")]
    model_id: Annotated[
        UUID, Field(alias="modelId", description="Unique ID for the model")
    ]
    model_name: Annotated[
        str | None, Field(alias="modelName", description="Model name")
    ] = None
    # App API fields
    location_id: Annotated[
        UUID | None, Field(alias="locationId", description="Sub-location UUID")
    ] = None
    root_location_id: Annotated[
        UUID | None, Field(alias="rootLocationId", description="Root location UUID")
    ] = None
    gateway_id: Annotated[
        UUID | None, Field(alias="gatewayId", description="Gateway UUID")
    ] = None
    is_alarm_device: Annotated[
        bool | None,
        Field(alias="isAlarmDevice", description="Whether the device is part of the alarm"),
    ] = None
    sensors_connected_device_type: Annotated[
        str | None,
        Field(
            alias="sensorsConnectedDeviceType",
            description="Door/window type for entry sensors; None for motion sensors",
        ),
    ] = None
    features: DeviceFeatures


# Gateway (hjemmesentral) Models
class GatewayPowerStates(BaseModel):
    """Power/battery states reported by the gateway."""

    model_config = ConfigDict(extra="allow")

    ac_power: Annotated[SensorState[bool] | None, Field(alias="acPower")] = None
    battery_percent: Annotated[
        SensorState[int] | None, Field(alias="batteryPercent")
    ] = None
    battery_low: Annotated[SensorState[bool] | None, Field(alias="batteryLow")] = None
    battery_voltage: Annotated[
        SensorState[float] | None, Field(alias="batteryVoltage")
    ] = None
    power_source_voltage: Annotated[
        SensorState[float] | None, Field(alias="powerSourceVoltage")
    ] = None


class GatewayConnectionStates(BaseModel):
    """Connectivity states reported by the gateway."""

    model_config = ConfigDict(extra="allow")

    source: SensorState[str] | None = None


class GatewayStatusStates(BaseModel):
    """Firmware/status states reported by the gateway."""

    model_config = ConfigDict(extra="allow")

    firmware_version: Annotated[
        SensorState[str] | None, Field(alias="firmwareVersion")
    ] = None
    firmware_target_version: Annotated[
        SensorState[str] | None, Field(alias="firmwareTargetVersion")
    ] = None


class GatewayPowerFeature(BaseModel):
    """Gateway power feature container."""

    states: GatewayPowerStates


class GatewayConnectionFeature(BaseModel):
    """Gateway connection feature container."""

    states: GatewayConnectionStates


class GatewayStatusFeature(BaseModel):
    """Gateway status feature container."""

    states: GatewayStatusStates


class GatewayFeatures(BaseModel):
    """Collection of gateway telemetry features."""

    model_config = ConfigDict(extra="allow")

    power: GatewayPowerFeature | None = None
    connection: GatewayConnectionFeature | None = None
    status: GatewayStatusFeature | None = None


class Gateway(BaseModel):
    """Homely gateway (hjemmesentral) with telemetry features."""

    model_config = ConfigDict(extra="allow")

    id: UUID
    serial_number: Annotated[str | None, Field(alias="serialNumber")] = None
    model_id: Annotated[UUID | None, Field(alias="modelId")] = None
    online: bool = True
    features: GatewayFeatures | None = None


# Gateway extras — fetched on a slow cadence (networks + history log)
class GatewayGsm(BaseModel):
    model_config = ConfigDict(extra="allow")

    state: str | None = None
    signal_strength: Annotated[str | None, Field(alias="signalStrength")] = None
    network_operator_name: Annotated[
        str | None, Field(alias="networkOperatorName")
    ] = None


class GatewayWifi(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    connected: bool | None = None


class GatewayNetworks(BaseModel):
    model_config = ConfigDict(extra="allow")

    connection_source: Annotated[
        str | None, Field(alias="connectionSource")
    ] = None
    wifi_network: Annotated[GatewayWifi | None, Field(alias="wifiNetwork")] = None
    gsm: GatewayGsm | None = None


class GatewayLogEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    status: str
    type: str


_SEEN_LOG_STATUSES = frozenset({"read", "acknowledged"})


def count_unread_log_entries(entries: list[GatewayLogEntry]) -> int:
    return sum(1 for e in entries if e.status not in _SEEN_LOG_STATUSES)


# Home API Response Model — normalised from the nested app-API response
class HomeResponse(BaseModel):
    """Complete home state from Homely API."""

    model_config = ConfigDict(populate_by_name=True)

    location_id: UUID
    name: str | None = None
    gateway_serial: str | None = None
    gateway: Gateway | None = None
    remaining_pin_attempts: Annotated[
        int | None, Field(alias="remainingPinAttempts")
    ] = None
    alarm_state: Annotated[
        AlarmState | None,
        BeforeValidator(lambda v: v.upper() if isinstance(v, str) else v),
    ] = None
    user_role: UserRole | None = None
    devices: list[Device]


# Error Response Models
class ErrorResponse(BaseModel):
    """API error response structure."""

    statusCode: int
    message: str | list[str]


# Helper func to get current time
def time_now(tz: timezone = UTC, buffer_seconds: int = 0) -> datetime:
    """Get current time with optional buffer for token expiry checks."""
    return datetime.now(tz) + timedelta(seconds=buffer_seconds)


class APITokens(BaseModel):
    """OAuth tokens with expiration tracking."""

    access_token: str
    refresh_token: str
    expires_at: datetime | None = None
    refresh_expires_at: datetime | None = None

    @classmethod
    def from_token_response(cls, response: TokenResponse) -> "APITokens":
        """Create APITokens from a TokenResponse."""
        now = time_now()
        return cls(
            access_token=response.access_token,
            refresh_token=response.refresh_token,
            expires_at=(
                now + timedelta(seconds=response.expires_in)
                if response.expires_in
                else None
            ),
            refresh_expires_at=(
                now + timedelta(seconds=response.refresh_expires_in)
                if response.refresh_expires_in
                else None
            ),
        )

    def is_access_token_expired(self, buffer_seconds: int = 30) -> bool:
        """Check if the access token is expired or about to expire."""
        if not self.expires_at:
            return False
        return time_now(buffer_seconds=buffer_seconds) >= self.expires_at

    def is_refresh_token_expired(self, buffer_seconds: int = 30) -> bool:
        """Check if the refresh token is expired or about to expire."""
        if not self.refresh_expires_at:
            return False
        return time_now(buffer_seconds=buffer_seconds) >= self.refresh_expires_at


# Type aliases
type LocationsResponse = list[Location]
type RequestBody = AuthRequest
type Feature = (
    AlarmFeature
    | TemperatureFeature
    | BatteryFeature
    | DiagnosticFeature
    | MeteringFeature
    | ThermostatFeature
)

type StateCollection = (
    AlarmStates
    | TemperatureStates
    | BatteryStates
    | DiagnosticStates
    | MeteringStates
    | ThermostatStates
)

# WebSocket interfaces. Don't have docs here,
# so mostly guesswork at this point...


# TODO: unsure about the values here...
class WsEventType(str, Enum):
    """WebSocket event types from Homely."""

    DEVICE_STATE_CHANGED = "device-state-changed"
    ALARM_STATE_CHANGED = "alarm-state-changed"


class AlarmStateName(str, Enum):
    """Alarm state names for WebSocket updates."""

    ALARM = "alarm"
    TAMPER = "tamper"
    FLOOD = "flood"
    FIRE = "fire"


class TemperatureStateName(str, Enum):
    """Temperature state names for WebSocket updates."""

    TEMPERATURE = "temperature"
    LOCAL_TEMPERATURE = "localTemperature"


class BatteryStateName(str, Enum):
    """Battery state names for WebSocket updates."""

    LOW = "low"
    DEFECT = "defect"
    VOLTAGE = "voltage"


class DiagnosticStateName(str, Enum):
    """Diagnostic state names for WebSocket updates."""

    NETWORK_LINK_STRENGTH = "networklinkstrength"
    NETWORK_LINK_ADDRESS = "networklinkaddress"
    SIGNAL_STRENGTH = "signalStrength"
    ONLINE = "online"
    TAMPER = "tamper"


class MeteringStateName(str, Enum):
    """Energy metering state names for WebSocket updates."""

    SUMMATION_DELIVERED = "summationdelivered"
    SUMMATION_RECEIVED = "summationreceived"
    DEMAND = "demand"
    CHECK = "check"


class ThermostatStateName(str, Enum):
    """Thermostat state names for WebSocket updates."""

    LOCAL_TEMPERATURE = "LocalTemperature"
    ABS_MIN_HEAT_SETPOINT_LIMIT = "AbsMinHeatSetpointLimit"
    ABS_MAX_HEAT_SETPOINT_LIMIT = "AbsMaxHeatSetpointLimit"
    OCCUPIED_COOLING_SETPOINT = "OccupiedCoolingSetpoint"
    OCCUPIED_HEATING_SETPOINT = "OccupiedHeatingSetpoint"
    CONTROL_SEQUENCE_OF_OPERATION = "ControlSequenceOfOperation"
    SYSTEM_MODE = "SystemMode"


type StateName = (
    AlarmStateName
    | TemperatureStateName
    | BatteryStateName
    | DiagnosticStateName
    | MeteringStateName
    | ThermostatStateName
)


# TODO: unsure about the exact model here...
class WsStateChangeData(SensorState):
    """WebSocket state change data for a single sensor."""

    model_config = ConfigDict(extra="allow")

    feature: Annotated[FeatureName | str, Field(alias="feature")]
    state_name: Annotated[StateName | str, Field(alias="stateName")]
    value: StateValue | None = None
    last_updated: Annotated[datetime | None, Field(alias="lastUpdated")] = None


# TODO: unsure about the exact model here...
class WsDeviceChangeData(BaseModel):
    """WebSocket device state change event data."""

    model_config = ConfigDict(extra="allow")

    location_id: Annotated[UUID, Field(alias="locationId")]
    device_id: Annotated[UUID, Field(alias="deviceId")]
    root_location_id: Annotated[UUID | None, Field(alias="rootLocationId")] = None
    gateway_id: Annotated[UUID | None, Field(alias="gatewayId")] = None
    model_id: Annotated[UUID | None, Field(alias="modelId")] = None
    change: WsStateChangeData
    changes: list[WsStateChangeData]
    partner_code: int | None = None  # Dev partner id ?


# TODO: unsure about the exact model here...
class WsAlarmChangeData(BaseModel):
    """WebSocket alarm state change event data."""

    model_config = ConfigDict(extra="allow")

    location_id: Annotated[UUID, Field(alias="locationId")]
    state: AlarmState
    user_id: Annotated[UUID | None, Field(alias="userId")] = None
    user_name: Annotated[str | None, Field(alias="userName")] = None
    timestamp: Annotated[datetime, Field(alias="timestamp")]
    event_id: Annotated[int | str | None, Field(alias="eventId")] = None


# TODO: unsure about the exact model here...
class WsEventUnknown(BaseModel):
    """Unknown WebSocket event type."""

    model_config = ConfigDict(extra="allow")

    type: str
    data: dict[str, Any]


class WsDeviceChangeEvent(BaseModel):
    """WebSocket device state change event."""

    model_config = ConfigDict(extra="allow")

    type: Literal[WsEventType.DEVICE_STATE_CHANGED] = WsEventType.DEVICE_STATE_CHANGED
    data: WsDeviceChangeData


class WsAlarmChangeEvent(BaseModel):
    """WebSocket alarm state change event."""

    model_config = ConfigDict(extra="allow")

    type: Literal[WsEventType.ALARM_STATE_CHANGED] = WsEventType.ALARM_STATE_CHANGED
    data: WsAlarmChangeData


type WsEvent = WsDeviceChangeEvent | WsAlarmChangeEvent | WsEventUnknown
WsEventAdapter: TypeAdapter[WsEvent] = TypeAdapter(WsEvent)
