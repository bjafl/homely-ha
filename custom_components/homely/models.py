"""Data structures and validation for Homely API interaction."""

from datetime import UTC, datetime, timedelta, timezone
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, TypeAdapter

# Custom types
type StateValue = bool | int | float | str


class AlarmState(str, Enum):
    DISARMED = "DISARMED"
    ARMED_AWAY = "ARMED_AWAY"
    ARMED_NIGHT = "ARMED_NIGHT"
    ARMED_PARTLY = "ARMED_PARTLY"
    BREACHED = "BREACHED"
    ALARM_PENDING = "ALARM_PENDING"
    ALARM_STAY_PENDING = "ALARM_STAY_PENDING"
    ARMED_NIGHT_PENDING = "ARMED_NIGHT_PENDING"
    ARMED_AWAY_PENDING = "ARMED_AWAY_PENDING"


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    OWNER = "OWNER"


# Authentication Models
class AuthRequest(BaseModel):
    username: Annotated[
        str, Field(description="Same email address as used in the Homely app")
    ]
    password: Annotated[
        str, Field(description="Same password as used in the Homely app")
    ]


class TokenResponse(BaseModel):
    access_token: Annotated[str, Field(description="Access token for API requests")]
    expires_in: Annotated[int, Field(description="Token expiration time in seconds")]
    refresh_expires_in: Annotated[
        int, Field(description="Refresh token expiration time in seconds")
    ]
    refresh_token: Annotated[
        str, Field(description="Refresh token for obtaining new access tokens")
    ]
    token_type: str = "bearer"
    scope: str = ""
    session_state: str | None = None
    not_before_policy: Annotated[int | None, Field(alias="not-before-policy")] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# Location Models
class Location(BaseModel):
    name: Annotated[str, Field(description="User defined name for the location")]
    role: Annotated[
        UserRole,
        Field(description="User's role at the location/gateway"),
        BeforeValidator(lambda v: v.upper()),
    ]
    user_id: Annotated[
        UUID, Field(alias="userId", description="Unique ID for the user")
    ]
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
    model_config = ConfigDict(extra="allow")

    value: T | None = None
    last_updated: Annotated[datetime | None, Field(alias="lastUpdated")] = None


class AlarmStates(BaseModel):
    model_config = ConfigDict(extra="allow")

    alarm: SensorState[bool] | None = None
    tamper: SensorState[bool] | None = None
    flood: SensorState[bool] | None = None
    fire: SensorState[bool] | None = None


class TemperatureStates(BaseModel):
    model_config = ConfigDict(extra="allow")

    temperature: SensorState[float] | None = None
    # local_temperature: Annotated[
    #     SensorState | None, Field(alias="localTemperature")
    # ] = None  # For ELKO thermostat


class BatteryStates(BaseModel):
    model_config = ConfigDict(extra="allow")

    low: SensorState[bool] | None = None
    defect: SensorState[bool] | None = None
    voltage: SensorState[float] | None = None


class DiagnosticStates(BaseModel):
    model_config = ConfigDict(extra="allow")

    network_link_strength: Annotated[
        SensorState[int] | None, Field(alias="networklinkstrength")
    ] = None
    network_link_address: Annotated[
        SensorState[str] | None, Field(alias="networklinkaddress")
    ] = None


class MeteringStates(BaseModel):
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
    ALARM = "alarm"
    TEMPERATURE = "temperature"
    BATTERY = "battery"
    DIAGNOSTIC = "diagnostic"
    METERING = "metering"
    THERMOSTAT = "thermostat"


class AlarmFeature(BaseModel):
    states: AlarmStates


class TemperatureFeature(BaseModel):
    states: TemperatureStates


class BatteryFeature(BaseModel):
    states: BatteryStates


class DiagnosticFeature(BaseModel):
    states: DiagnosticStates


class MeteringFeature(BaseModel):
    states: MeteringStates


class ThermostatFeature(BaseModel):
    states: ThermostatStates


class DeviceFeatures(BaseModel):
    alarm: AlarmFeature | None = None
    temperature: TemperatureFeature | None = None
    battery: BatteryFeature | None = None
    diagnostic: DiagnosticFeature | None = None
    metering: MeteringFeature | None = None
    thermostat: ThermostatFeature | None = None


# Device Models
class Device(BaseModel):
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
    features: DeviceFeatures


# Home API Response Model
class HomeResponse(BaseModel):
    location_id: Annotated[
        UUID, Field(alias="locationId", description="Unique ID for the location")
    ]
    gateway_serial: Annotated[str | None, Field(alias="gatewayserial")] = None
    name: Annotated[str | None, Field(description="Name of the location")] = None
    alarm_state: Annotated[
        AlarmState,
        Field(alias="alarmState", description="Current alarm state"),
        BeforeValidator(lambda v: v.upper()),
    ]
    user_role: Annotated[
        UserRole,
        Field(alias="userRoleAtLocation", description="User role at the location"),
        BeforeValidator(lambda v: v.upper()),
    ]
    devices: Annotated[
        list[Device], Field(description="List of devices in the location")
    ]


# Error Response Models
class ErrorResponse(BaseModel):
    statusCode: int
    message: str | list[str]


# Helper func to get current time
def time_now(tz: timezone = UTC, buffer_seconds: int = 0) -> datetime:
    return datetime.now(tz) + timedelta(seconds=buffer_seconds)


class APITokens(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: datetime | None = None
    refresh_expires_at: datetime | None = None

    @classmethod
    def from_token_response(cls, response: TokenResponse) -> "APITokens":
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
        if not self.expires_at:
            return False
        return time_now(buffer_seconds=buffer_seconds) >= self.expires_at

    def is_refresh_token_expired(self, buffer_seconds: int = 30) -> bool:
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
    DEVICE_STATE_CHANGED = "device-state-changed"
    ALARM_STATE_CHANGED = "alarm-state-changed"


class AlarmStateName(str, Enum):
    ALARM = "alarm"
    TAMPER = "tamper"
    FLOOD = "flood"
    FIRE = "fire"


class TemperatureStateName(str, Enum):
    TEMPERATURE = "temperature"
    LOCAL_TEMPERATURE = "localTemperature"


class BatteryStateName(str, Enum):
    LOW = "low"
    DEFECT = "defect"
    VOLTAGE = "voltage"


class DiagnosticStateName(str, Enum):
    NETWORK_LINK_STRENGTH = "networklinkstrength"
    NETWORK_LINK_ADDRESS = "networklinkaddress"


class MeteringStateName(str, Enum):
    SUMMATION_DELIVERED = "summationdelivered"
    SUMMATION_RECEIVED = "summationreceived"
    DEMAND = "demand"
    CHECK = "check"


class ThermostatStateName(str, Enum):
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
    model_config = ConfigDict(extra="allow")

    feature: Annotated[FeatureName | str, Field(alias="feature")]
    state_name: Annotated[StateName | str, Field(alias="stateName")]
    value: StateValue | None = None
    last_updated: Annotated[datetime | None, Field(alias="lastUpdated")] = None


# TODO: unsure about the exact model here...
class WsDeviceChangeData(BaseModel):
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
    model_config = ConfigDict(extra="allow")

    location_id: Annotated[UUID, Field(alias="locationId")]
    state: AlarmState


# TODO: unsure about the exact model here...
class WsEventUnknown(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    data: dict[str, Any]


class WsDeviceChangeEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal[WsEventType.DEVICE_STATE_CHANGED] = WsEventType.DEVICE_STATE_CHANGED
    data: WsDeviceChangeData


class WsAlarmChangeEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal[WsEventType.ALARM_STATE_CHANGED] = WsEventType.ALARM_STATE_CHANGED
    data: WsAlarmChangeData


type WsEvent = WsDeviceChangeEvent | WsAlarmChangeEvent | WsEventUnknown
WsEventAdapter = TypeAdapter(WsEvent)
