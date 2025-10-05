"""Constants for the Homely integration."""

DOMAIN = "homely"

FALLBACK_SCAN_INTERVAL = 30  # seconds

CONF_AVAILABLE_LOCATIONS = "available_locations"

STEP_LOCATIONS = "locations"
STEP_PICK_LOCATIONS = "pick_locations"
STEP_USER = "user"


class HomelyUrls:
    """Homely API URLs."""

    ORIGIN = "sdk.iotiliti.cloud"
    BASE = f"https://{ORIGIN}/homely"
    AUTH_LOGIN = f"{BASE}/oauth/token"
    AUTH_REFRESH = f"{BASE}/oauth/refresh"
    LOCATIONS = f"{BASE}/locations"
    HOME = f"{BASE}/home"
    # ALARM_STATE = f"{BASE}/alarm/state"
    WEBSOCKET = f"https://{ORIGIN}"


RE_MOTION_SENSOR = r".*\b(motion|pir|PIR|presence)\b.*"
RE_ENTRY_SENSOR = r".*\b(magnet|door|window|entry)\b.*"


class HomelyEntityIcons:
    """Icons for Homely entities."""

    BATTERY_LOW = "mdi:battery-10"
    BATTERY_NOT_LOW = "mdi:battery-90"
    BATTERY_DEFECT = "mdi:battery-remove"
    BATTERY_NOT_DEFECT = "mdi:battery-check"

    ALARM_DISARMED = "mdi:shield-off-outline"
    ALARM_ARMED_HOME = "mdi:shield-home"
    ALARM_ARMED_AWAY = "mdi:shield-lock"
    ALARM_ARMED_NIGHT = "mdi:shield-moon"
    ALARM_TRIGGERED = "mdi:shield-alert"
    ALARM_ARMING = "mdi:shield-sync"
    ALARM_PENDING = "mdi:shield-alert-outline"
    ALARM_UNKNOWN = "mdi:shield-question"

    SIGNAL_HIGH = "mdi:wifi-strength-4"
    SIGNAL_MEDIUM = "mdi:wifi-strength-3"
    SIGNAL_LOW = "mdi:wifi-strength-2"
    SIGNAL_VERY_LOW = "mdi:wifi-strength-1"
    SIGNAL_NONE = "mdi:wifi-strength-off"


class HomelyEntityIdSuffix:
    """Suffixes for Homely entity IDs."""

    BATTERY_LOW = "battery_low"
    BATTERY_DEFECT = "battery_defect"
    ENTRY = "entry"
    FLOOD = "flood"
    MOTION = "motion"
    ALARM = "alarm"
    TEMPERATURE = "temperature"
    ENERGY_CHECK = "energy_check"
