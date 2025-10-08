# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Home Assistant custom integration for Homely alarm systems. The integration connects to the Homely API (sdk.iotiliti.cloud) to monitor and control alarm systems, sensors, and devices. It uses both REST API polling and WebSocket connections for real-time updates.

## Development Commands

### Setup and Installation
```bash
pip install -e ".[dev]"  # Install with dev dependencies
pre-commit install       # Set up pre-commit hooks
```

### Testing
```bash
pytest                           # Run all tests
pytest tests/components/homely/test_coordinator.py  # Run specific test file
pytest -k test_name              # Run specific test by name
make test                        # Alternative via makefile
make coverage                    # Generate coverage report (htmlcov/index.html)
```

**Coverage requirement**: 85% minimum (configured in pyproject.toml)

### Linting and Formatting
```bash
ruff check .                     # Run linting
ruff format .                    # Format code
ruff check --fix .               # Auto-fix linting issues
mypy custom_components/homely    # Type checking (NOTE: uses 'homely' not 'your_integration')
make lint                        # Run both ruff and mypy
make format                      # Format and auto-fix
make pre-commit                  # Run all pre-commit hooks
```

### Cleanup
```bash
make clean  # Remove build artifacts, cache, and coverage files
```

## Architecture

### Core Components

**API Client** (`homely_api.py`):
- `HomelyApi`: REST API client for authentication and data fetching
  - Token management with automatic refresh
  - Location and device data retrieval
- `HomelyWebSocketClient`: Real-time event handling via Socket.IO
  - Manages WebSocket connections per location
  - Auto-reconnection with exponential backoff
- `HomelyHomeState`: State container that merges REST API data with WebSocket updates
  - Validates and applies incremental updates from WebSocket events
  - Tracks last_updated timestamps to prevent out-of-order updates

**Data Coordinator** (`coordinator.py`):
- `HomelyDataUpdateCoordinator`: Manages data flow and WebSocket lifecycle
  - Maintains dict of `HomelyHomeState` objects keyed by location_id
  - Dynamic polling interval based on WebSocket health (30s-30min)
  - Handles WebSocket reconnection with exponential backoff (30s to 5min)
  - Rate-limits error-triggered refreshes (max 1 per 60s)

**Data Models** (`models.py`):
- Pydantic models for all API data structures
- `WsEvent` types: `WsDeviceChangeEvent`, `WsAlarmChangeEvent` with discriminated union via `WsEventAdapter`
- State tracking: `SensorState`, `Feature`, `Device`, `HomeResponse`
- Authentication: `TokenResponse`, `APITokens` (with expiry tracking)

**Entities**:
- `binary_sensor.py`: Motion, entry, flood sensors, battery status
- `sensor.py`: Temperature, signal strength, energy check
- `button.py`: Control actions
- All entities inherit from `HomelyEntity` in `base_sensor.py`

**Config Flow** (`config_flow.py`):
- Multi-step setup: credentials → location selection
- Options flow for changing selected locations

### Data Flow

1. **Initial Setup**: Config entry → API login → Fetch locations → Create coordinator → Fetch initial state via REST
2. **Runtime Updates**:
   - WebSocket events → `_handle_ws_update()` → Apply to `HomelyHomeState` → Trigger entity updates
   - Fallback polling via `_async_update_data()` when WebSockets unavailable or as periodic validation
3. **Reconnection**: WebSocket disconnect → `_handle_ws_disconnect()` → `_schedule_reconnect()` with backoff

### Important Implementation Details

**mypy Configuration**: Note that makefile line 19 incorrectly references `custom_components/your_integration`, but should target `custom_components/homely`. The pre-commit hooks correctly target `custom_components/`.

**Ruff Configuration**:
- Line length: 88 characters
- Target: Python 3.13
- Enforces docstrings (D rules) except in tests
- McCabe complexity limit: 25

**Test Configuration**:
- Async mode: auto
- Coverage source: `custom_components/homely` (NOT `your_integration` as in line 175 of pyproject.toml)
- Uses `pytest-homeassistant-custom-component` framework

**WebSocket Event Processing**:
- Events must match location_id or raise `HomelyStateUdateLocationMismatchError`
- Updates with older timestamps are ignored by default (`ignore_outdated_values=True`)
- Missing target states can be ignored or raise `HomelyStateUpdateMissingTargetError`

## Key Patterns

**Getting device state**: Use `coordinator.get_device_state(device_id, location_id)` rather than directly accessing coordinator.data

**Accessing nested state values**: Use `get_field()` helper (homely_api.py:65) to safely access Pydantic model fields by name or alias

**WebSocket callbacks**: Always use `@callback` decorator for WebSocket event handlers to ensure they run in event loop

**Token management**: API automatically refreshes tokens. Use `await api.get_access_token()` for guaranteed valid token

## HACS Integration

This integration is configured for HACS (Home Assistant Community Store) via hacs.json. Minimum Home Assistant version: 2025.1.0
