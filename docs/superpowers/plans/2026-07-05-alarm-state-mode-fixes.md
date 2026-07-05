# Alarm State/Mode Correctness + New-Data Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify and lock in correct alarm-state/breach mapping in the Homely HA integration using a real captured arm→trigger→disarm sequence, then land the highest-value fixes and features uncovered by the July 2026 sniff (device manufacturer/vendor, per-mode alarm-profile/reaction data, per-mode countdown config, and per-device alarm-trigger events).

**Architecture:** No architectural change. All work extends the existing pydantic `models.py` (tolerant, `_missing_`-fallback style enums; `extra="allow"` on containers), the existing per-location `HomelyHomeState` WS-event dispatch in `homely_api.py`, and existing entity patterns (`extra_state_attributes` for diagnostic data, `EventEntity` for discrete WS-driven events). No new REST endpoints are called — every fix in this plan uses data already present in the `/home` response or already-flowing (but currently unhandled) WebSocket events.

**Tech Stack:** Python 3.13, pydantic v2 (`BaseModel`, `Field(alias=...)`, `TypeAdapter` unions), Home Assistant `CoordinatorEntity`/`EventEntity`/`AlarmControlPanelEntity`/`BinarySensorEntity`, pytest (test files `tests/components/homely/test_*.py`, `pythonpath = "."`, no HA test harness required — most tests build models/entities directly with `MagicMock`).

## Global Constraints

- Python `>=3.13` (`requires-python` in `pyproject.toml`); use modern syntax already in use in this codebase (`str | None`, `type X = A | B` aliases).
- Never raise on an unrecognized enum value from the API — follow the existing `AlarmState._missing_` tolerant-fallback pattern (log a warning, return a sensible default) for any new enum this plan introduces.
- Commit style is Conventional Commits, lower-case scope in parens, e.g. `feat(alarm): ...`, `fix(device): ...` — matches `git log` on this branch (`feature/app-api`).
- Run the full suite (`pytest`) after each task, not just the new test file — several tasks touch shared fixtures (`conftest.py`) that other tests depend on.
- All new/changed model fields must be optional (`| None = None`) — the `/home` response shape is not guaranteed stable across Homely app versions, and existing code never assumes a field is present.
- Ground every piece of sample test data in the real captures already committed to `~/source/sniffs/` (`homely_alarm_roles_redacted.json`, `homely_alarm_modes_redacted.json`, `homely_new.json`) — this repo's existing tests already do this (real location/device IDs, real names), keep that convention.
- Lint/type-check before commit is available via `make lint` (`ruff check .` + `mypy custom_components/homely`) — not required per-step in this plan, but run it before the final task's commit at minimum.

---

## File Structure

| File | Change |
|---|---|
| `custom_components/homely/event.py` | Task 1: add `BREACHED` to `_STATE_TO_EVENT`. Task 7: new `HomelyDeviceAlarmEventEntity`. |
| `custom_components/homely/models.py` | Task 3: `Device.model_vendor`/`device_type`. Task 4: `AlarmReaction` enum + `Device.alarm_profile_*`/`alarm_reaction_*`. Task 5: `ExitEntryProfileSettings`/`ExitEntrySettings` + `Gateway.exit_entry_settings`. Task 6: `WsEventType` additions, `WsDeviceAlarmData`, `WsDeviceAlarmTriggeredEvent`, `WsDeviceAlarmRestoreEvent`, `WsEvent` union update. |
| `custom_components/homely/base_sensor.py` | Task 3: `get_manufacturer` prefers `device.model_vendor`. |
| `custom_components/homely/binary_sensor.py` | Task 4: `HomelyDeviceOnlineSensor.extra_state_attributes`. |
| `custom_components/homely/alarm_control_panel.py` | Task 5: `HomelyAlarmControlPanel.extra_state_attributes`. |
| `custom_components/homely/homely_api.py` | Task 6: `HomelyHomeState` new fields + `update_state` dispatch + `_process_ws_device_alarm_triggered`/`_process_ws_device_alarm_restore`. |
| `custom_components/homely/translations/en.json`, `nb.json` | Task 7: `event.device_alarm` translation key. |
| `tests/components/homely/conftest.py` | Task 3: `create_mock_device` defaults for `model_vendor`/`device_type`. |
| `tests/components/homely/test_breach_sequence_replay.py` (new) | Task 2. |
| `tests/components/homely/test_device_detection.py` | Task 3, Task 4 (extend). |
| `tests/components/homely/test_base_sensor.py` | Task 3 (extend). |
| `tests/components/homely/test_binary_sensor.py` | Task 4 (extend). |
| `tests/components/homely/test_exit_entry_settings.py` (new) | Task 5. |
| `tests/components/homely/test_device_alarm_trigger.py` (new) | Task 6, Task 7. |
| `tests/components/homely/test_alarm_event.py` | Task 1 (extend). |

---

### Task 1: Fire an event entity trigger on `BREACHED`

**Files:**
- Modify: `custom_components/homely/event.py:23-29,56`
- Test: `tests/components/homely/test_alarm_event.py`

**Interfaces:**
- Consumes: `AlarmState.BREACHED` (already exists, `custom_components/homely/models.py:32`).
- Produces: `_STATE_TO_EVENT[AlarmState.BREACHED] == "triggered"`; `"triggered"` added to `HomelyAlarmEventEntity._attr_event_types` — later tasks (Task 2) assert on this.

**Context:** `_ALARM_STATE_MAP` in `alarm_control_panel.py` already correctly maps `BREACHED` → `AlarmControlPanelState.TRIGGERED` (verified against real traffic, see `API_GAP_ANALYSIS.md` §5), so the alarm panel entity itself already shows the right state. But `event.py`'s `_STATE_TO_EVENT` — which drives the separate `HomelyAlarmEventEntity` that HA's Logbook surfaces — has no entry for `BREACHED`, so a real alarm trigger is invisible in the Logbook (only arm/disarm transitions show up today).

- [ ] **Step 1: Write the failing test**

Add to `tests/components/homely/test_alarm_event.py`, inside `class TestAlarmEventEntity:`:

```python
    def test_breached_fires_triggered_event(self):
        home = _home_state()
        ent = self._entity(home)
        # Real captured payload has userName: "" on BREACHED (see homely_alarm_roles_redacted.json)
        home.last_alarm_event = _alarm_event("BREACHED", user_name="")
        ent._handle_coordinator_update()
        ent._trigger_event.assert_called_once()
        event_type, attrs = ent._trigger_event.call_args[0]
        assert event_type == "triggered"
        assert attrs["state"] == "BREACHED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/components/homely/test_alarm_event.py::TestAlarmEventEntity::test_breached_fires_triggered_event -v`
Expected: FAIL — `ent._trigger_event.assert_called_once()` raises `AssertionError: Expected 'mock' to have been called once. Called 0 times.` because `_STATE_TO_EVENT.get(AlarmState.BREACHED)` is `None`, so `_handle_coordinator_update` returns early (`event.py:105-107`).

- [ ] **Step 3: Write minimal implementation**

In `custom_components/homely/event.py`, change:

```python
_STATE_TO_EVENT: dict[AlarmState, str] = {
    AlarmState.DISARMED: "disarmed",
    AlarmState.ARMED_AWAY: "armed_away",
    AlarmState.ARMED_NIGHT: "armed_night",
    AlarmState.ARMED_STAY: "armed_home",
    AlarmState.ARMED_PARTLY: "armed_home",
}
```

to:

```python
_STATE_TO_EVENT: dict[AlarmState, str] = {
    AlarmState.DISARMED: "disarmed",
    AlarmState.ARMED_AWAY: "armed_away",
    AlarmState.ARMED_NIGHT: "armed_night",
    AlarmState.ARMED_STAY: "armed_home",
    AlarmState.ARMED_PARTLY: "armed_home",
    AlarmState.BREACHED: "triggered",
}
```

And change:

```python
    _attr_event_types = ["disarmed", "armed_away", "armed_night", "armed_home"]
```

to:

```python
    _attr_event_types = ["disarmed", "armed_away", "armed_night", "armed_home", "triggered"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/components/homely/test_alarm_event.py -v`
Expected: PASS (all tests in the file, including the pre-existing ones — `_STATE_TO_EVENT` gained a key, nothing was removed).

- [ ] **Step 5: Commit**

```bash
git add custom_components/homely/event.py tests/components/homely/test_alarm_event.py
git commit -m "feat(event): fire a 'triggered' action event on alarm BREACHED"
```

---

### Task 2: Regression test — replay the real captured breach sequence end-to-end

**Files:**
- Create: `tests/components/homely/test_breach_sequence_replay.py`

**Interfaces:**
- Consumes: `HomelyWebSocketClient._parse_sio_packet` (`homely_api.py:678`), `HomelyHomeState.from_ws_event` (`homely_api.py:411`), `_ALARM_STATE_MAP` (`alarm_control_panel.py:27`), `HomelyAlarmEventEntity` (`event.py:49`, now emitting `"triggered"` per Task 1).
- Produces: nothing new — this is a characterization/regression test locking in already-correct behavior against real traffic, not a new capability.

**Context:** This task depends on Task 1. Unlike `test_alarm_states.py` (unit tests against hand-built `WsAlarmChangeData` dicts) or `test_alarm_event.py` (tests the event entity against hand-built alarm events), no existing test replays the *raw Socket.IO wire frames* — literally what mitmproxy captured — through the *full* pipeline (`_parse_sio_packet` → `HomelyHomeState.from_ws_event` → `_ALARM_STATE_MAP` → event entity). This is the strongest possible guarantee that "alarm states map correctly, especially the pending-before-alarm and breach states" (the user's top priority): a test built from data that was never hand-crafted, straight from a real arm→(missed disarm attempt)→breach→disarm cycle captured 2026-07-05 (`~/source/sniffs/homely_alarm_roles_redacted.json`).

Note what is *not* covered here, and why: the real capture never showed an intermediate `ALARM_STAY_PENDING`/entry-delay WS push between `ARMED_STAY` and `BREACHED` — the location state stayed `ARMED_STAY` for the full ~20s entry-delay window and then jumped straight to `BREACHED`. So this test intentionally does not assert an entry-delay-pending intermediate state; asserting one would fabricate behavior never observed on the wire. (`ALARM_PENDING`/`ALARM_STAY_PENDING` remain in `_ALARM_STATE_MAP` for forward-compatibility/other Homely configurations, per the existing tolerant-parsing philosophy — just not exercised by this specific sequence.)

Since this task depends on Task 1 and does not itself change production code, there is no red step — it is written to already pass, and running it is the verification that Task 1 (and the pre-existing mapping) are correct end-to-end against real traffic.

- [ ] **Step 1: Write the regression test**

Create `tests/components/homely/test_breach_sequence_replay.py`:

```python
"""Regression test: replay the exact raw WS frames from a real arm→trigger→breach→
disarm cycle (STAY profile, 2026-07-05) and assert each step maps to the correct HA
alarm state and fires the correct event-entity event.

Frames are copied verbatim (with tokens redacted at capture time, not here — these
frames carry no secrets) from ~/source/sniffs/homely_alarm_roles_redacted.json.
"""

from unittest.mock import MagicMock

from homeassistant.components.alarm_control_panel.const import AlarmControlPanelState

from custom_components.homely.alarm_control_panel import _ALARM_STATE_MAP
from custom_components.homely.event import HomelyAlarmEventEntity
from custom_components.homely.homely_api import HomelyHomeState, HomelyWebSocketClient

LOCATION_ID = "f32bf453-23f9-4986-9a0c-195a06c99961"

# Raw Socket.IO event frames, byte-for-byte as captured (ack-id digits included).
FRAME_ARM_STAY_PENDING = (
    '422197096["message",{"type":"alarm-state-changed","eventData":'
    '{"locationId":"f32bf453-23f9-4986-9a0c-195a06c99961","state":"ARM_STAY_PENDING",'
    '"timestamp":"2026-07-05T16:53:52.021Z","partnerCode":1275}}]'
)
FRAME_ARMED_STAY = (
    '422197122["message",{"type":"alarm-state-changed","eventData":'
    '{"locationId":"f32bf453-23f9-4986-9a0c-195a06c99961","state":"ARMED_STAY",'
    '"timestamp":"2026-07-05T16:54:12.039Z","userId":"5fcb044d-2f2b-43fb-9ca3-8b3869342be7",'
    '"userName":"Bjarte Test Lode","eventId":2701,"partnerCode":1275}}]'
)
FRAME_BREACHED = (
    '422197257["message",{"type":"alarm-state-changed","eventData":'
    '{"locationId":"f32bf453-23f9-4986-9a0c-195a06c99961","state":"BREACHED",'
    '"timestamp":"2026-07-05T16:55:16.766Z","userName":"","eventId":2705,'
    '"partnerCode":1275}}]'
)
FRAME_DISARMED = (
    '422197272["message",{"type":"alarm-state-changed","eventData":'
    '{"locationId":"f32bf453-23f9-4986-9a0c-195a06c99961","state":"DISARMED",'
    '"timestamp":"2026-07-05T16:55:21.480Z","userId":"e8ef1246-b8e5-4cae-ac01-6d49e84effc8",'
    '"userName":"Bjarte Fl\\u00f8 Lode","eventId":2708,'
    '"deviceId":"adee071e-3428-4808-bafd-9b9bd7353869","partnerCode":1275}}]'
)


def _client() -> HomelyWebSocketClient:
    return HomelyWebSocketClient(api=MagicMock(), location_id=LOCATION_ID)


def _initial_state() -> HomelyHomeState:
    return HomelyHomeState.model_validate({"location_id": LOCATION_ID, "devices": []})


class TestRealBreachSequenceReplay:
    def test_full_sequence_maps_to_expected_ha_states(self):
        client = _client()
        state = _initial_state()

        _, ev = client._parse_sio_packet(FRAME_ARM_STAY_PENDING)
        state = HomelyHomeState.from_ws_event(state, ev, ignore_unhandled_event_types=True)
        assert _ALARM_STATE_MAP[state.alarm_state] == AlarmControlPanelState.ARMING

        _, ev = client._parse_sio_packet(FRAME_ARMED_STAY)
        state = HomelyHomeState.from_ws_event(state, ev, ignore_unhandled_event_types=True)
        assert _ALARM_STATE_MAP[state.alarm_state] == AlarmControlPanelState.ARMED_HOME

        _, ev = client._parse_sio_packet(FRAME_BREACHED)
        state = HomelyHomeState.from_ws_event(state, ev, ignore_unhandled_event_types=True)
        assert _ALARM_STATE_MAP[state.alarm_state] == AlarmControlPanelState.TRIGGERED
        assert state.last_alarm_event.event_id == 2705

        _, ev = client._parse_sio_packet(FRAME_DISARMED)
        state = HomelyHomeState.from_ws_event(state, ev, ignore_unhandled_event_types=True)
        assert _ALARM_STATE_MAP[state.alarm_state] == AlarmControlPanelState.DISARMED
        assert state.last_alarm_event.user_name == "Bjarte Flø Lode"

    def test_breach_and_disarm_fire_expected_action_events(self):
        client = _client()
        state = _initial_state()
        for frame in (FRAME_ARM_STAY_PENDING, FRAME_ARMED_STAY):
            _, ev = client._parse_sio_packet(frame)
            state = HomelyHomeState.from_ws_event(state, ev, ignore_unhandled_event_types=True)

        coordinator = MagicMock()
        coordinator.get_home_state = MagicMock(return_value=state)
        entity = HomelyAlarmEventEntity(coordinator, LOCATION_ID, state)
        entity._trigger_event = MagicMock()
        entity.async_write_ha_state = MagicMock()

        _, ev = client._parse_sio_packet(FRAME_BREACHED)
        state = HomelyHomeState.from_ws_event(state, ev, ignore_unhandled_event_types=True)
        coordinator.get_home_state.return_value = state
        entity._handle_coordinator_update()
        assert entity._trigger_event.call_args[0][0] == "triggered"

        _, ev = client._parse_sio_packet(FRAME_DISARMED)
        state = HomelyHomeState.from_ws_event(state, ev, ignore_unhandled_event_types=True)
        coordinator.get_home_state.return_value = state
        entity._handle_coordinator_update()
        assert entity._trigger_event.call_args[0][0] == "disarmed"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/components/homely/test_breach_sequence_replay.py -v`
Expected: PASS. If `test_breach_and_disarm_fire_expected_action_events` fails with `triggered` missing, Task 1 was not completed first — do it before this task.

- [ ] **Step 3: Commit**

```bash
git add tests/components/homely/test_breach_sequence_replay.py
git commit -m "test(alarm): regression-test the real captured arm/breach/disarm sequence"
```

---

### Task 3: `Device.model_vendor`/`device_type` fields; prefer API-reported vendor over heuristics

**Files:**
- Modify: `custom_components/homely/models.py:344-386` (`Device`)
- Modify: `custom_components/homely/base_sensor.py:32-75` (`get_manufacturer`)
- Modify: `tests/components/homely/conftest.py:119-143` (`create_mock_device`)
- Test: `tests/components/homely/test_device_detection.py`, `tests/components/homely/test_base_sensor.py`

**Interfaces:**
- Consumes: nothing from other tasks in this plan.
- Produces: `Device.model_vendor: str | None`, `Device.device_type: str | None` — consumed by Task 4 sample data (both fields appear on the same real devices used there) but Task 4 does not depend on this task's code changes, only shares sample data conventions.

**Context:** `get_manufacturer()` (`base_sensor.py:32`) guesses manufacturer from a serial-number MAC-OUI prefix or a model-name regex. The real `/home` response already reports the authoritative value directly (`modelVendor: "frient A/S"`, `"Fireangel"`) — confirmed in the July 2026 sniff (`API_GAP_ANALYSIS.md` §2, `~/source/sniffs/homely_new.json`) — but `Device` has no field for it, and pydantic's default `extra="ignore"` (no `model_config` on `Device`) silently drops it. Prefer the authoritative value; keep the heuristics as a fallback for older/incomplete API responses.

**⚠️ Fixture hazard:** `create_mock_device` (`conftest.py:119`) builds `MagicMock(spec=Device)`. Once `Device` gains a `model_vendor` field, *every* other test using `create_mock_device()` without passing `model_vendor` will get an auto-generated truthy child `MagicMock()` for that attribute (not `None`) — which would make `get_manufacturer`'s new "prefer model_vendor" branch wrongly fire for every existing test and break `test_get_manufacturer`'s serial/model-name assertions. Step 3 below adds explicit `None` defaults for both new attributes in `create_mock_device`, in the same commit as the model change, so the full suite stays green.

- [ ] **Step 1: Write the failing test**

Add to `tests/components/homely/test_device_detection.py`, new class:

```python
class TestDeviceModelVendorAndType:
    """API-reported manufacturer/connectivity type (2026-07 sniff)."""

    def test_parses_model_vendor_and_device_type(self):
        # Real device from the sniff: "Vaskeromsdør" entry sensor.
        dev = Device.model_validate(
            {
                "id": "067721f1-f16a-41da-930b-05ae26eee802",
                "name": "Vaskeromsdør",
                "online": True,
                "modelId": "9b765375-e3f4-4627-b73c-b4143ce86c2c",
                "modelName": "Alarm Entry Sensor 2",
                "modelVendor": "frient A/S",
                "deviceType": "ZIGBEE",
                "features": {"alarm": {"states": {"alarm": {"value": False}}}},
            }
        )
        assert dev.model_vendor == "frient A/S"
        assert dev.device_type == "ZIGBEE"

    def test_missing_model_vendor_is_none(self):
        dev = Device.model_validate(
            {
                "id": "067721f1-f16a-41da-930b-05ae26eee802",
                "online": True,
                "modelId": "9b765375-e3f4-4627-b73c-b4143ce86c2c",
                "features": {"alarm": {"states": {"alarm": {"value": False}}}},
            }
        )
        assert dev.model_vendor is None
        assert dev.device_type is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/components/homely/test_device_detection.py::TestDeviceModelVendorAndType -v`
Expected: FAIL — `AttributeError: 'Device' object has no attribute 'model_vendor'` (the field does not exist yet; `modelVendor`/`deviceType` in the input dict are silently ignored by pydantic's default `extra="ignore"`).

- [ ] **Step 3: Write minimal implementation**

In `custom_components/homely/models.py`, in the `Device` class, after the `sensors_connected_device_type` field (`models.py:379-385`) and before `features: DeviceFeatures`:

```python
    model_vendor: Annotated[
        str | None,
        Field(alias="modelVendor", description="Manufacturer name reported by the API"),
    ] = None
    device_type: Annotated[
        str | None,
        Field(alias="deviceType", description="Connectivity type, e.g. ZIGBEE"),
    ] = None
```

In `tests/components/homely/conftest.py`, in `create_mock_device` (`conftest.py:119-143`), add two lines next to the existing explicit defaults:

```python
    device.is_alarm_device = None
    device.sensors_connected_device_type = None
    device.model_vendor = None
    device.device_type = None
```

- [ ] **Step 4: Run test to verify it passes, and run the full suite**

Run: `pytest tests/components/homely/test_device_detection.py -v`
Expected: PASS.

Run: `pytest`
Expected: PASS (no regressions from the `conftest.py` change — confirms the fixture-hazard fix above was necessary and sufficient).

- [ ] **Step 5: Commit**

```bash
git add custom_components/homely/models.py tests/components/homely/conftest.py tests/components/homely/test_device_detection.py
git commit -m "feat(device): parse modelVendor/deviceType from the app API"
```

- [ ] **Step 6: Write the second failing test (manufacturer preference)**

Add to `tests/components/homely/test_base_sensor.py`, inside `class TestHomelySensorBase:` (after `test_get_manufacturer`):

```python
    def test_get_manufacturer_prefers_api_reported_vendor(
        self, mock_coordinator_basic
    ):
        """When the API reports modelVendor, use it verbatim over heuristics."""
        device = create_mock_device(
            serial_number="0015BC123456",  # would otherwise heuristically match "frient"
            model_vendor="Fireangel",
        )
        sensor = HomelySensorBase(mock_coordinator_basic, TEST_LOCATION_ID, device)
        assert sensor.device_manufacturer == "Fireangel"
```

- [ ] **Step 7: Run test to verify it fails**

Run: `pytest "tests/components/homely/test_base_sensor.py::TestHomelySensorBase::test_get_manufacturer_prefers_api_reported_vendor" -v`
Expected: FAIL — `assert 'frient' == 'Fireangel'` (the serial-number heuristic wins because `get_manufacturer` does not check `model_vendor` yet).

- [ ] **Step 8: Write minimal implementation**

In `custom_components/homely/base_sensor.py`, insert two lines at the top of `get_manufacturer` (`base_sensor.py:32-34`), immediately after the docstring and before the `SERIAL_MATCH = {` line — the rest of the function body (the `SERIAL_MATCH`/`MODEL_NAME_MATCH` dicts and the matching loop, `base_sensor.py:34-75`) stays exactly as-is, unindented and unchanged:

```python
def get_manufacturer(device: Device) -> str:
    """Get the manufacturer for a Homely device."""
    if device.model_vendor:
        return device.model_vendor
    SERIAL_MATCH = {
        "frient": re.compile(r"^0015BC"),  # Develco Products AS (frient)
        # ... unchanged ...
```

- [ ] **Step 9: Run test to verify it passes, and run the full suite**

Run: `pytest tests/components/homely/test_base_sensor.py -v`
Expected: PASS.

Run: `pytest`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add custom_components/homely/base_sensor.py tests/components/homely/test_base_sensor.py
git commit -m "fix(device): prefer API-reported modelVendor over MAC/model-name guessing"
```

---

### Task 4: Per-device alarm-profile membership + reaction type (incl. new `FOLLOWER` value)

**Files:**
- Modify: `custom_components/homely/models.py:18-75` (add `AlarmReaction` enum near `AlarmState`), `models.py:344-386` (`Device` fields)
- Modify: `custom_components/homely/binary_sensor.py:579-600` (`HomelyDeviceOnlineSensor`)
- Test: `tests/components/homely/test_device_detection.py`, `tests/components/homely/test_binary_sensor.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `AlarmReaction` enum (`NORMAL`/`ENTRY_EXIT`/`FOLLOWER`/`UNKNOWN`), `Device.alarm_profile_away/night/stay: bool | None`, `Device.alarm_reaction_away/night/stay: AlarmReaction | None`.

**Context:** July 2026 sniff (`PATCH /devices/{id}/alarm-reaction`, `~/source/sniffs/homely_alarm_modes_redacted.json`) confirmed a third real reaction value, `FOLLOWER`, alongside the two already documented (`NORMAL`, `ENTRY_EXIT`) — see `API_GAP_ANALYSIS.md` §1/§2. None of these six per-device fields are parsed today (`Device` has no `model_config`, so pydantic silently drops them). Follow the existing tolerant-enum convention (`AlarmState._missing_`) for `AlarmReaction` so a future/unknown reaction value never crashes state processing.

- [ ] **Step 1: Write the failing test**

Add to `tests/components/homely/test_device_detection.py` (add `AlarmReaction` to the existing `from custom_components.homely.models import Device` import line, making it `from custom_components.homely.models import AlarmReaction, Device`):

```python
class TestAlarmProfileAndReactionFields:
    """Per-mode alarm-profile membership + reaction type (2026-07 sniff).

    FOLLOWER is a real reaction value confirmed live via
    PATCH /devices/{id}/alarm-reaction {"alarmReactionStay": "FOLLOWER"}.
    """

    def test_parses_profile_and_reaction_fields(self):
        dev = Device.model_validate(
            {
                "id": "067721f1-f16a-41da-930b-05ae26eee802",
                "name": "Vaskeromsdør",
                "online": True,
                "modelId": "9b765375-e3f4-4627-b73c-b4143ce86c2c",
                "alarmProfileAway": True,
                "alarmProfileNight": True,
                "alarmProfileStay": True,
                "alarmReactionAway": "ENTRY_EXIT",
                "alarmReactionNight": "NORMAL",
                "alarmReactionStay": "ENTRY_EXIT",
                "features": {"alarm": {"states": {"alarm": {"value": False}}}},
            }
        )
        assert dev.alarm_profile_away is True
        assert dev.alarm_profile_night is True
        assert dev.alarm_profile_stay is True
        assert dev.alarm_reaction_away is AlarmReaction.ENTRY_EXIT
        assert dev.alarm_reaction_night is AlarmReaction.NORMAL
        assert dev.alarm_reaction_stay is AlarmReaction.ENTRY_EXIT

    def test_follower_reaction_value_parses(self):
        dev = Device.model_validate(
            {
                "id": "067721f1-f16a-41da-930b-05ae26eee802",
                "online": True,
                "modelId": "9b765375-e3f4-4627-b73c-b4143ce86c2c",
                "alarmReactionStay": "FOLLOWER",
                "features": {"alarm": {"states": {"alarm": {"value": False}}}},
            }
        )
        assert dev.alarm_reaction_stay is AlarmReaction.FOLLOWER

    def test_unknown_reaction_value_does_not_raise(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            dev = Device.model_validate(
                {
                    "id": "067721f1-f16a-41da-930b-05ae26eee802",
                    "online": True,
                    "modelId": "9b765375-e3f4-4627-b73c-b4143ce86c2c",
                    "alarmReactionAway": "SOMETHING_NEW",
                    "features": {"alarm": {"states": {"alarm": {"value": False}}}},
                }
            )
        assert dev.alarm_reaction_away is AlarmReaction.UNKNOWN
        assert "SOMETHING_NEW" in caplog.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/components/homely/test_device_detection.py::TestAlarmProfileAndReactionFields -v`
Expected: FAIL — `ImportError: cannot import name 'AlarmReaction'` (does not exist yet).

- [ ] **Step 3: Write minimal implementation**

In `custom_components/homely/models.py`, add a new enum right after the `AlarmState` class (i.e. after `models.py:74`, before `class UserRole`):

```python
class AlarmReaction(str, Enum):
    """How a device reacts within an alarm profile it belongs to."""

    NORMAL = "NORMAL"
    ENTRY_EXIT = "ENTRY_EXIT"
    FOLLOWER = "FOLLOWER"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def _missing_(cls, value: object) -> "AlarmReaction":
        """Best-effort map an unrecognized reaction instead of raising."""
        _LOGGER.warning(
            "Unknown Homely alarm reaction %r — defaulting to UNKNOWN. "
            "Please report so it can be handled explicitly.",
            value,
        )
        return cls.UNKNOWN
```

Then in the `Device` class, after the new `device_type` field added in Task 3 (and before `features: DeviceFeatures`):

```python
    alarm_profile_away: Annotated[
        bool | None, Field(alias="alarmProfileAway")
    ] = None
    alarm_profile_night: Annotated[
        bool | None, Field(alias="alarmProfileNight")
    ] = None
    alarm_profile_stay: Annotated[
        bool | None, Field(alias="alarmProfileStay")
    ] = None
    alarm_reaction_away: Annotated[
        AlarmReaction | None, Field(alias="alarmReactionAway")
    ] = None
    alarm_reaction_night: Annotated[
        AlarmReaction | None, Field(alias="alarmReactionNight")
    ] = None
    alarm_reaction_stay: Annotated[
        AlarmReaction | None, Field(alias="alarmReactionStay")
    ] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/components/homely/test_device_detection.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/homely/models.py tests/components/homely/test_device_detection.py
git commit -m "feat(device): parse per-mode alarm-profile membership and reaction type"
```

- [ ] **Step 6: Write the failing test for the diagnostic attributes**

Add to `tests/components/homely/test_binary_sensor.py`, new class (imports `AlarmReaction` locally inside the test — this file has no existing top-level import of it):

```python
class TestHomelyDeviceOnlineSensorAlarmAttributes:
    """Alarm-profile/-reaction diagnostic attributes (2026-07 sniff)."""

    def test_exposes_profile_and_reaction_attributes(
        self, mock_device, mock_coordinator_basic
    ):
        from custom_components.homely.models import AlarmReaction

        sensor = HomelyDeviceOnlineSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        device_state = MagicMock()
        device_state.alarm_profile_away = True
        device_state.alarm_profile_night = False
        device_state.alarm_profile_stay = True
        device_state.alarm_reaction_away = AlarmReaction.ENTRY_EXIT
        device_state.alarm_reaction_night = AlarmReaction.NORMAL
        device_state.alarm_reaction_stay = AlarmReaction.FOLLOWER
        sensor._get_current_device_state = MagicMock(return_value=device_state)

        attrs = sensor.extra_state_attributes

        assert attrs["alarm_profile_away"] is True
        assert attrs["alarm_profile_night"] is False
        assert attrs["alarm_profile_stay"] is True
        assert attrs["alarm_reaction_away"] == "ENTRY_EXIT"
        assert attrs["alarm_reaction_night"] == "NORMAL"
        assert attrs["alarm_reaction_stay"] == "FOLLOWER"

    def test_no_device_state_omits_alarm_attrs(
        self, mock_device, mock_coordinator_basic
    ):
        sensor = HomelyDeviceOnlineSensor(
            mock_coordinator_basic, TEST_LOCATION_ID, mock_device
        )
        sensor._get_current_device_state = MagicMock(return_value=None)
        attrs = sensor.extra_state_attributes
        assert "alarm_profile_away" not in attrs
```

- [ ] **Step 7: Run test to verify it fails**

Run: `pytest tests/components/homely/test_binary_sensor.py::TestHomelyDeviceOnlineSensorAlarmAttributes -v`
Expected: FAIL — `KeyError: 'alarm_profile_away'` (`HomelyDeviceOnlineSensor` has no `extra_state_attributes` override yet, so it inherits the base `{"last_updated": ...}`-only implementation).

- [ ] **Step 8: Write minimal implementation**

In `custom_components/homely/binary_sensor.py`, add to `HomelyDeviceOnlineSensor` (`binary_sensor.py:579-600`), after the existing `is_on` property:

```python
    @property
    def extra_state_attributes(self) -> dict[str, bool | str | None]:
        """Expose alarm-profile membership and per-mode reaction type."""
        existing_attrs = super().extra_state_attributes or {}
        attrs: dict[str, bool | str | None] = dict(existing_attrs)
        device = self._get_current_device_state()
        if device is None:
            return attrs
        attrs["alarm_profile_away"] = device.alarm_profile_away
        attrs["alarm_profile_night"] = device.alarm_profile_night
        attrs["alarm_profile_stay"] = device.alarm_profile_stay
        attrs["alarm_reaction_away"] = (
            device.alarm_reaction_away.value if device.alarm_reaction_away else None
        )
        attrs["alarm_reaction_night"] = (
            device.alarm_reaction_night.value if device.alarm_reaction_night else None
        )
        attrs["alarm_reaction_stay"] = (
            device.alarm_reaction_stay.value if device.alarm_reaction_stay else None
        )
        return attrs
```

- [ ] **Step 9: Run test to verify it passes, and run the full suite**

Run: `pytest tests/components/homely/test_binary_sensor.py -v`
Expected: PASS.

Run: `pytest`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add custom_components/homely/binary_sensor.py tests/components/homely/test_binary_sensor.py
git commit -m "feat(device): expose alarm-profile/-reaction as diagnostic attributes"
```

---

### Task 5: Per-mode countdown/sound config (`gateway.exitEntrySettings`) as alarm-panel attributes

**Files:**
- Modify: `custom_components/homely/models.py:447-467` (new models + `Gateway` field)
- Modify: `custom_components/homely/alarm_control_panel.py:64-112` (`HomelyAlarmControlPanel`)
- Create: `tests/components/homely/test_exit_entry_settings.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `ExitEntryProfileSettings`, `ExitEntrySettings`, `Gateway.exit_entry_settings: ExitEntrySettings | None`; `HomelyAlarmControlPanel.extra_state_attributes` dict with keys `{away,night,stay}_{entry_time,exit_time,entry_sound_time,exit_sound_time,squawk_level}` plus `siren_level_entry_exit`/`siren_level_alarm`.

**Context:** This is the exact data that answers "do we have good documentation on the alarm modes" from the July 2026 sniff (`PATCH /gateways/{id}/exit-entry`, confirmed values in `API_GAP_ANALYSIS.md` §2: Away 30/60s, Night 40/20s, Stay 20/20s entry/exit). It's already fetched by the existing `/home` call (`Gateway` has `model_config = ConfigDict(extra="allow")`, `models.py:460`) but has no typed field and nothing reads it — so it's technically present but invisible and unverified against schema drift. Exposing it on the alarm panel entity means users can literally see their configured delay times in the HA UI without any new API call.

- [ ] **Step 1: Write the failing test**

Create `tests/components/homely/test_exit_entry_settings.py`:

```python
"""Tests for gateway.exitEntrySettings — per-mode countdown/sound config.

Values match the real config captured 2026-07-05 via PATCH /gateways/{id}/exit-entry
(see ~/source/sniffs/homely_alarm_modes_redacted.json, API_GAP_ANALYSIS.md §2).
"""

from unittest.mock import MagicMock

from custom_components.homely.alarm_control_panel import HomelyAlarmControlPanel
from custom_components.homely.models import ExitEntrySettings, Gateway

EXIT_ENTRY_DATA = {
    "alarmProfileAway": {
        "entryTime": 30,
        "entrySoundTime": 25,
        "exitTime": 60,
        "exitSoundTime": 30,
        "squawkLevel": "MediumLevelSound",
    },
    "alarmProfileNight": {
        "entryTime": 40,
        "entrySoundTime": 30,
        "exitTime": 20,
        "exitSoundTime": 0,
        "squawkLevel": "LowLevelSound",
    },
    "alarmProfileStay": {
        "entryTime": 20,
        "entrySoundTime": 20,
        "exitTime": 20,
        "exitSoundTime": 5,
        "squawkLevel": "LowLevelSound",
    },
    "sirenLevelStayDelay": "LowLevelSound",
    "sirenLevelEntryExit": "HighLevelSound",
    "sirenLevelNightDelay": "LowLevelSound",
    "sirenLevelAlarm": "VeryHighLevelSound",
}

LOCATION_ID = "f32bf453-23f9-4986-9a0c-195a06c99961"


class TestExitEntrySettingsModel:
    def test_parses_all_three_profiles(self):
        settings = ExitEntrySettings.model_validate(EXIT_ENTRY_DATA)
        assert settings.alarm_profile_away.exit_time == 60
        assert settings.alarm_profile_night.entry_time == 40
        assert settings.alarm_profile_stay.entry_time == 20
        assert settings.siren_level_alarm == "VeryHighLevelSound"

    def test_gateway_carries_exit_entry_settings(self):
        gw = Gateway.model_validate(
            {
                "id": "eafa2c31-3eb4-41a3-90cf-19f498e7a2b7",
                "online": True,
                "exitEntrySettings": EXIT_ENTRY_DATA,
            }
        )
        assert gw.exit_entry_settings is not None
        assert gw.exit_entry_settings.alarm_profile_stay.exit_time == 20


class TestAlarmControlPanelExitEntryAttributes:
    def test_exposes_per_mode_countdown_attrs(self):
        gw = Gateway.model_validate(
            {
                "id": "eafa2c31-3eb4-41a3-90cf-19f498e7a2b7",
                "online": True,
                "exitEntrySettings": EXIT_ENTRY_DATA,
            }
        )
        home_state = MagicMock()
        home_state.gateway = gw
        home_state.name = "Hjem"
        home_state.gateway_serial = "020000014000F13D"
        coordinator = MagicMock()
        coordinator.get_home_state = MagicMock(return_value=home_state)

        panel = HomelyAlarmControlPanel(coordinator, LOCATION_ID, home_state)
        attrs = panel.extra_state_attributes

        assert attrs["away_exit_time"] == 60
        assert attrs["night_entry_time"] == 40
        assert attrs["stay_entry_time"] == 20
        assert attrs["siren_level_alarm"] == "VeryHighLevelSound"

    def test_no_gateway_returns_none(self):
        home_state = MagicMock()
        home_state.gateway = None
        coordinator = MagicMock()
        coordinator.get_home_state = MagicMock(return_value=home_state)
        panel = HomelyAlarmControlPanel(coordinator, LOCATION_ID, home_state)
        assert panel.extra_state_attributes is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/components/homely/test_exit_entry_settings.py -v`
Expected: FAIL — `ImportError: cannot import name 'ExitEntrySettings'` (does not exist yet).

- [ ] **Step 3: Write minimal implementation**

In `custom_components/homely/models.py`, add right before `class Gateway(BaseModel):` (`models.py:457`):

```python
class ExitEntryProfileSettings(BaseModel):
    """Countdown + arming-sound config for one alarm profile (Away/Night/Stay)."""

    model_config = ConfigDict(extra="allow")

    entry_time: Annotated[int | None, Field(alias="entryTime")] = None
    entry_sound_time: Annotated[int | None, Field(alias="entrySoundTime")] = None
    exit_time: Annotated[int | None, Field(alias="exitTime")] = None
    exit_sound_time: Annotated[int | None, Field(alias="exitSoundTime")] = None
    squawk_level: Annotated[str | None, Field(alias="squawkLevel")] = None


class ExitEntrySettings(BaseModel):
    """Per-mode countdown/sound config + siren levels (`gateway.exitEntrySettings`)."""

    model_config = ConfigDict(extra="allow")

    alarm_profile_away: Annotated[
        ExitEntryProfileSettings | None, Field(alias="alarmProfileAway")
    ] = None
    alarm_profile_night: Annotated[
        ExitEntryProfileSettings | None, Field(alias="alarmProfileNight")
    ] = None
    alarm_profile_stay: Annotated[
        ExitEntryProfileSettings | None, Field(alias="alarmProfileStay")
    ] = None
    siren_level_stay_delay: Annotated[
        str | None, Field(alias="sirenLevelStayDelay")
    ] = None
    siren_level_entry_exit: Annotated[
        str | None, Field(alias="sirenLevelEntryExit")
    ] = None
    siren_level_night_delay: Annotated[
        str | None, Field(alias="sirenLevelNightDelay")
    ] = None
    siren_level_alarm: Annotated[str | None, Field(alias="sirenLevelAlarm")] = None
```

Then add one field to `Gateway` (`models.py:457-466`), after `features`:

```python
    exit_entry_settings: Annotated[
        ExitEntrySettings | None, Field(alias="exitEntrySettings")
    ] = None
```

In `custom_components/homely/alarm_control_panel.py`, add to `HomelyAlarmControlPanel` (`alarm_control_panel.py:103-112`), right after the `alarm_state` property:

```python
    @property
    def extra_state_attributes(self) -> dict[str, int | str | None] | None:
        """Expose configured entry/exit delay + sound levels per alarm mode."""
        home_state = self.coordinator.get_home_state(self._location_id)
        settings = (
            home_state.gateway.exit_entry_settings
            if home_state and home_state.gateway
            else None
        )
        if settings is None:
            return None
        attrs: dict[str, int | str | None] = {}
        for mode, profile in (
            ("away", settings.alarm_profile_away),
            ("night", settings.alarm_profile_night),
            ("stay", settings.alarm_profile_stay),
        ):
            if profile is None:
                continue
            attrs[f"{mode}_entry_time"] = profile.entry_time
            attrs[f"{mode}_exit_time"] = profile.exit_time
            attrs[f"{mode}_entry_sound_time"] = profile.entry_sound_time
            attrs[f"{mode}_exit_sound_time"] = profile.exit_sound_time
            attrs[f"{mode}_squawk_level"] = profile.squawk_level
        attrs["siren_level_entry_exit"] = settings.siren_level_entry_exit
        attrs["siren_level_alarm"] = settings.siren_level_alarm
        return attrs
```

- [ ] **Step 4: Run test to verify it passes, and run the full suite**

Run: `pytest tests/components/homely/test_exit_entry_settings.py -v`
Expected: PASS.

Run: `pytest`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/homely/models.py custom_components/homely/alarm_control_panel.py tests/components/homely/test_exit_entry_settings.py
git commit -m "feat(alarm): expose per-mode entry/exit countdown config as panel attributes"
```

---

### Task 6: Handle `device-alarm-triggered`/`device-alarm-restore` WebSocket events

**Files:**
- Modify: `custom_components/homely/models.py:608-756` (`WsEventType`, new WS models, `WsEvent` union)
- Modify: `custom_components/homely/homely_api.py:402-544` (`HomelyHomeState`)
- Create: `tests/components/homely/test_device_alarm_trigger.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `WsDeviceAlarmData` (fields `alarm_type: str`, `device_id: UUID`, `location_id: UUID`, `event_time: datetime | None`), `HomelyHomeState.last_device_alarm_triggered`/`last_device_alarm_restored: WsDeviceAlarmData | None`, `HomelyHomeState.last_device_alarm_triggered_seq`/`last_device_alarm_restored_seq: int` (monotonic counters, used by Task 7 for dedup) — Task 7 consumes these four attributes plus `_process_ws_device_alarm_triggered`/`_process_ws_device_alarm_restore` are exercised directly by this task's own tests.

**Context:** Real capture (2026-07-05, `~/source/sniffs/homely_alarm_roles_redacted.json`) showed these two WS event types firing alongside the location-level `alarm-state-changed` BREACHED/DISARMED events, carrying per-device detail (`{"type": "BURGLARY", "deviceId": ..., "locationId": ..., "eventTime": ...}` for triggered; restore has no `eventTime`). Today they parse as generic `WsEventUnknown` (any `type: str` + `data: dict` matches) and are silently dropped in `HomelyHomeState.update_state`'s `else` branch, since the coordinator always calls `from_ws_event(..., ignore_unhandled_event_types=True)` (`coordinator.py:354-359`). This was previously blocked in `docs/IMPLEMENTATION_STATUS.md` as needing a new rate-limited REST call (`homely_zone_event`, `/gateways/{id}/history-log`) — these WS events sidestep that entirely: zero new REST calls, already flowing.

Use a monotonic per-type sequence counter (not the event payload's own identity) for dedup in Task 7, because the real `device-alarm-restore` payload carries no timestamp or id at all — nothing in the payload itself is suitable as a stable dedup key.

- [ ] **Step 1: Write the failing test**

Create `tests/components/homely/test_device_alarm_trigger.py`:

```python
"""Tests for per-device alarm trigger/restore WS events.

Grounded in real captured traffic (2026-07-05, BURGLARY on an entry sensor):
see ~/source/sniffs/homely_alarm_roles_redacted.json.
"""

import pytest

from custom_components.homely.exceptions import HomelyStateUpdateLocationMismatchError
from custom_components.homely.homely_api import HomelyHomeState
from custom_components.homely.models import WsDeviceAlarmData

LOCATION_ID = "f32bf453-23f9-4986-9a0c-195a06c99961"
DEVICE_ID = "8a70e463-5f3d-445f-9ab3-5fbd25318c0b"


def _home_state() -> HomelyHomeState:
    return HomelyHomeState.model_validate({"location_id": LOCATION_ID, "devices": []})


def _triggered(alarm_type="BURGLARY", device_id=DEVICE_ID, location_id=LOCATION_ID):
    return WsDeviceAlarmData.model_validate(
        {
            "type": alarm_type,
            "deviceId": device_id,
            "locationId": location_id,
            "eventTime": "2026-07-05T16:54:56.733Z",
        }
    )


def _restored(alarm_type="BURGLARY", device_id=DEVICE_ID, location_id=LOCATION_ID):
    # Real payload carries no eventTime on restore.
    return WsDeviceAlarmData.model_validate(
        {"type": alarm_type, "deviceId": device_id, "locationId": location_id}
    )


class TestHomeStateStoresDeviceAlarmEvents:
    def test_triggered_stores_event_and_bumps_seq(self):
        home = _home_state()
        home._process_ws_device_alarm_triggered(_triggered())
        assert home.last_device_alarm_triggered.alarm_type == "BURGLARY"
        assert str(home.last_device_alarm_triggered.device_id) == DEVICE_ID
        assert home.last_device_alarm_triggered_seq == 1

    def test_restored_stores_event_and_bumps_seq(self):
        home = _home_state()
        home._process_ws_device_alarm_restore(_restored())
        assert home.last_device_alarm_restored.alarm_type == "BURGLARY"
        assert home.last_device_alarm_restored_seq == 1

    def test_second_trigger_bumps_seq_again(self):
        home = _home_state()
        home._process_ws_device_alarm_triggered(_triggered())
        home._process_ws_device_alarm_triggered(_triggered())
        assert home.last_device_alarm_triggered_seq == 2

    def test_location_mismatch_raises(self):
        home = _home_state()
        wrong = _triggered(location_id="00000000-0000-0000-0000-000000000000")
        with pytest.raises(HomelyStateUpdateLocationMismatchError):
            home._process_ws_device_alarm_triggered(wrong)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/components/homely/test_device_alarm_trigger.py -v`
Expected: FAIL — `ImportError: cannot import name 'WsDeviceAlarmData'` (does not exist yet).

- [ ] **Step 3: Write minimal implementation**

In `custom_components/homely/models.py`, change `WsEventType` (`models.py:613-617`):

```python
class WsEventType(str, Enum):
    """WebSocket event types from Homely."""

    DEVICE_STATE_CHANGED = "device-state-changed"
    ALARM_STATE_CHANGED = "alarm-state-changed"
    DEVICE_ALARM_TRIGGERED = "device-alarm-triggered"
    DEVICE_ALARM_RESTORE = "device-alarm-restore"
```

Add new models right after `WsAlarmChangeData` (`models.py:714-724`), before `WsEventUnknown`:

```python
class WsDeviceAlarmData(BaseModel):
    """WebSocket per-device alarm trigger/restore event data."""

    model_config = ConfigDict(extra="allow")

    alarm_type: Annotated[str, Field(alias="type")]
    device_id: Annotated[UUID, Field(alias="deviceId")]
    location_id: Annotated[UUID, Field(alias="locationId")]
    event_time: Annotated[datetime | None, Field(alias="eventTime")] = None
```

Add two new event wrapper models after `WsAlarmChangeEvent` (`models.py:746-752`), before `type WsEvent = ...`:

```python
class WsDeviceAlarmTriggeredEvent(BaseModel):
    """WebSocket per-device alarm trigger event (e.g. BURGLARY)."""

    model_config = ConfigDict(extra="allow")

    type: Literal[WsEventType.DEVICE_ALARM_TRIGGERED] = (
        WsEventType.DEVICE_ALARM_TRIGGERED
    )
    data: WsDeviceAlarmData


class WsDeviceAlarmRestoreEvent(BaseModel):
    """WebSocket per-device alarm restore event (condition cleared)."""

    model_config = ConfigDict(extra="allow")

    type: Literal[WsEventType.DEVICE_ALARM_RESTORE] = WsEventType.DEVICE_ALARM_RESTORE
    data: WsDeviceAlarmData
```

Change the union (`models.py:755`):

```python
type WsEvent = (
    WsDeviceChangeEvent
    | WsAlarmChangeEvent
    | WsDeviceAlarmTriggeredEvent
    | WsDeviceAlarmRestoreEvent
    | WsEventUnknown
)
WsEventAdapter: TypeAdapter[WsEvent] = TypeAdapter(WsEvent)
```

In `custom_components/homely/homely_api.py`, add the import (extend the existing `from .models import (...)` block at the top, `homely_api.py:39-56`) with `WsDeviceAlarmData`, `WsDeviceAlarmTriggeredEvent`, `WsDeviceAlarmRestoreEvent`.

In `HomelyHomeState` (`homely_api.py:402-410`), add two data fields and two counters after `last_alarm_event`:

```python
    last_alarm_event: WsAlarmChangeData | None = None
    last_device_alarm_triggered: WsDeviceAlarmData | None = None
    last_device_alarm_triggered_seq: int = 0
    last_device_alarm_restored: WsDeviceAlarmData | None = None
    last_device_alarm_restored_seq: int = 0
```

In `update_state` (`homely_api.py:468-487`), add two branches before the final `else`:

```python
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
        elif isinstance(event, WsDeviceAlarmTriggeredEvent):
            self._process_ws_device_alarm_triggered(event.data)
        elif isinstance(event, WsDeviceAlarmRestoreEvent):
            self._process_ws_device_alarm_restore(event.data)
        else:
            if not ignore_unhandled_event_types:
                raise HomelyStateUpdateError(
                    f"Cannot process event type {event.type}"
                    + " - unhandled or unknown event type"
                )
```

Add the two new handler methods after `_process_ws_alarm_state_update` (`homely_api.py:534-543`):

```python
    def _process_ws_device_alarm_triggered(self, update_data: WsDeviceAlarmData) -> None:
        """Record a per-device alarm trigger (e.g. BURGLARY) from the WS stream."""
        location_id = str(update_data.location_id)
        if location_id != str(self.location_id):
            raise HomelyStateUpdateLocationMismatchError(
                f"Location ID {location_id} in update does not match"
                + f" location ID {self.location_id} of this home state"
            )
        self.last_device_alarm_triggered = update_data
        self.last_device_alarm_triggered_seq += 1

    def _process_ws_device_alarm_restore(self, update_data: WsDeviceAlarmData) -> None:
        """Record a per-device alarm restore (condition cleared) from the WS stream."""
        location_id = str(update_data.location_id)
        if location_id != str(self.location_id):
            raise HomelyStateUpdateLocationMismatchError(
                f"Location ID {location_id} in update does not match"
                + f" location ID {self.location_id} of this home state"
            )
        self.last_device_alarm_restored = update_data
        self.last_device_alarm_restored_seq += 1
```

- [ ] **Step 4: Run test to verify it passes, and run the full suite**

Run: `pytest tests/components/homely/test_device_alarm_trigger.py -v`
Expected: PASS.

Run: `pytest`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/homely/models.py custom_components/homely/homely_api.py tests/components/homely/test_device_alarm_trigger.py
git commit -m "feat(alarm): handle device-alarm-triggered/restore WS events"
```

---

### Task 7: New per-device alarm-trigger event entity

**Files:**
- Modify: `custom_components/homely/event.py:1-46` (imports, `async_setup_entry`, new entity class)
- Modify: `custom_components/homely/translations/en.json:147-151`, `custom_components/homely/translations/nb.json:147-151`
- Test: `tests/components/homely/test_device_alarm_trigger.py` (extend, from Task 6)

**Interfaces:**
- Consumes: `HomelyHomeState.last_device_alarm_triggered`/`last_device_alarm_restored` + `..._seq` counters (Task 6).
- Produces: `HomelyDeviceAlarmEventEntity` (new `EventEntity`, one per device where `device.is_alarm_device` is true), `_attr_event_types = ["triggered", "restored"]`.

**Context:** This is the concrete new feature enabled by Task 6 — a per-device event entity (shows up in HA's Logbook, attached to that specific device, not the shared alarm-panel device) firing `triggered`/`restored` with the `alarm_type` (e.g. `BURGLARY`) whenever that device's `device-alarm-triggered`/`device-alarm-restore` WS event arrives. Mirrors the existing `HomelyAlarmEventEntity` pattern (startup-replay guard, `_trigger_event` + `async_write_ha_state`) but keyed by device instead of location, and using the sequence-counter dedup from Task 6 instead of an event-id/timestamp key (the real restore payload has neither).

- [ ] **Step 1: Write the failing test**

Add to `tests/components/homely/test_device_alarm_trigger.py` (created in Task 6):

```python
from unittest.mock import MagicMock


def _coordinator(home):
    c = MagicMock()
    c.get_home_state = MagicMock(return_value=home)
    return c


class TestDeviceAlarmEventEntity:
    def _entity(self, home):
        from custom_components.homely.event import HomelyDeviceAlarmEventEntity

        device = MagicMock()
        device.id = DEVICE_ID
        ent = HomelyDeviceAlarmEventEntity(_coordinator(home), LOCATION_ID, device, home)
        ent._trigger_event = MagicMock()
        ent.async_write_ha_state = MagicMock()
        return ent

    def test_fires_triggered_for_matching_device(self):
        home = _home_state()
        ent = self._entity(home)
        home._process_ws_device_alarm_triggered(_triggered())
        ent._handle_coordinator_update()
        ent._trigger_event.assert_called_once()
        event_type, attrs = ent._trigger_event.call_args[0]
        assert event_type == "triggered"
        assert attrs["alarm_type"] == "BURGLARY"

    def test_ignores_trigger_for_other_device(self):
        home = _home_state()
        ent = self._entity(home)
        home._process_ws_device_alarm_triggered(
            _triggered(device_id="00000000-0000-0000-0000-000000000001")
        )
        ent._handle_coordinator_update()
        ent._trigger_event.assert_not_called()

    def test_fires_restored_after_triggered(self):
        home = _home_state()
        ent = self._entity(home)
        home._process_ws_device_alarm_triggered(_triggered())
        ent._handle_coordinator_update()
        home._process_ws_device_alarm_restore(_restored())
        ent._handle_coordinator_update()
        assert ent._trigger_event.call_args[0][0] == "restored"

    def test_does_not_replay_event_present_at_startup(self):
        home = _home_state()
        home._process_ws_device_alarm_triggered(_triggered())
        ent = self._entity(home)  # created AFTER the event already happened
        ent._handle_coordinator_update()
        ent._trigger_event.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/components/homely/test_device_alarm_trigger.py::TestDeviceAlarmEventEntity -v`
Expected: FAIL — `ImportError: cannot import name 'HomelyDeviceAlarmEventEntity'` (does not exist yet).

- [ ] **Step 3: Write minimal implementation**

In `custom_components/homely/event.py`, add to the imports at the top: add `Device` to a new `from .models import AlarmState, Device` (currently just `from .models import AlarmState`, `event.py:17`).

Change `async_setup_entry` (`event.py:32-46`):

```python
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homely event entities based on a config entry."""
    coordinator: HomelyDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    if not coordinator.selected_location_ids:
        return
    entities: list[HomelyAlarmEventEntity | HomelyDeviceAlarmEventEntity] = [
        HomelyAlarmEventEntity(coordinator, location_id, home_state)
        for location_id, home_state in coordinator.data.items()
        if location_id in coordinator.selected_location_ids
    ]
    for location_id, home_state in coordinator.data.items():
        if location_id not in coordinator.selected_location_ids:
            continue
        for device in home_state.devices:
            if device.is_alarm_device:
                entities.append(
                    HomelyDeviceAlarmEventEntity(
                        coordinator, location_id, device, home_state
                    )
                )
    async_add_entities(entities)
```

Add the new entity class at the end of `event.py`, after `HomelyAlarmEventEntity`:

```python
class HomelyDeviceAlarmEventEntity(
    CoordinatorEntity[HomelyDataUpdateCoordinator], EventEntity
):
    """Fires per-device alarm trigger/restore events (e.g. BURGLARY) from the WS stream."""

    _attr_has_entity_name = True
    _attr_translation_key = "device_alarm"
    _attr_event_types = ["triggered", "restored"]
    _attr_icon = "mdi:shield-alert"

    def __init__(
        self,
        coordinator: HomelyDataUpdateCoordinator,
        location_id: str,
        device: Device,
        home_state: HomelyHomeState,
    ) -> None:
        """Initialize the per-device alarm trigger event entity."""
        super().__init__(coordinator)
        self._location_id = location_id
        self._device_id = str(device.id)
        self._attr_unique_id = f"{self._device_id}_alarm_trigger"
        # Don't replay events that already happened before this entity existed.
        self._last_triggered_seq = home_state.last_device_alarm_triggered_seq
        self._last_restored_seq = home_state.last_device_alarm_restored_seq

    @property
    def device_info(self) -> dr.DeviceInfo:
        """Attach to the existing device entity (not the gateway/panel)."""
        return dr.DeviceInfo(identifiers={(DOMAIN, self._device_id)})

    @callback
    def _handle_coordinator_update(self) -> None:
        """Fire a triggered/restored event when a new WS event targets this device."""
        home = self.coordinator.get_home_state(self._location_id)
        if home is None:
            return
        triggered = home.last_device_alarm_triggered
        if (
            triggered is not None
            and str(triggered.device_id) == self._device_id
            and home.last_device_alarm_triggered_seq != self._last_triggered_seq
        ):
            self._last_triggered_seq = home.last_device_alarm_triggered_seq
            self._trigger_event("triggered", {"alarm_type": triggered.alarm_type})
            self.async_write_ha_state()
            return
        restored = home.last_device_alarm_restored
        if (
            restored is not None
            and str(restored.device_id) == self._device_id
            and home.last_device_alarm_restored_seq != self._last_restored_seq
        ):
            self._last_restored_seq = home.last_device_alarm_restored_seq
            self._trigger_event("restored", {"alarm_type": restored.alarm_type})
            self.async_write_ha_state()
```

In `custom_components/homely/translations/en.json`, change the `event` section (`en.json:147-151`):

```json
    "event": {
      "alarm_action": {
        "name": "Alarm Action"
      },
      "device_alarm": {
        "name": "Alarm Trigger"
      }
    }
```

In `custom_components/homely/translations/nb.json`, change the `event` section (`nb.json:147-151`):

```json
    "event": {
      "alarm_action": {
        "name": "Alarmhandling"
      },
      "device_alarm": {
        "name": "Alarmutløsning"
      }
    }
```

- [ ] **Step 4: Run test to verify it passes, and run the full suite**

Run: `pytest tests/components/homely/test_device_alarm_trigger.py -v`
Expected: PASS.

Run: `pytest`
Expected: PASS.

Run: `make lint`
Expected: no new `ruff`/`mypy` errors.

- [ ] **Step 5: Commit**

```bash
git add custom_components/homely/event.py custom_components/homely/translations/en.json custom_components/homely/translations/nb.json tests/components/homely/test_device_alarm_trigger.py
git commit -m "feat(event): per-device alarm-trigger/-restore event entity"
```

---

## Explicitly out of scope for this plan

Considered from the July 2026 sniff but deliberately not included here (larger/separate decisions, not needed for alarm-state/mode correctness):

- Role management UI (`GET/PUT /locations/{id}/users`), `GET /guest-users` (possible 4th `GUEST` role, unconfirmed content), `GET /invitations/sent/{id}` — a location-membership feature, unrelated to alarm-state correctness.
- `POST /alarm/pin` (change PIN) — would need a new HA service action; no alarm-state-mapping dependency.
- Live WS-driven updates for `exit-entry-settings-changed`/`device-info-changed` (Task 5 reads config only via the existing periodic `/home` refresh) — real value is low since this config rarely changes while HA is running; revisit only if requested.
- `alarm-pin-updated` WS event — no entity to attach it to without a PIN-management feature; skip.
