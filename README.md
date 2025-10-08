# Homely Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.1.0+-green.svg)

Native Home Assistant integration for Homely alarm systems with real-time WebSocket updates and multi-location support.

**Related**: [hansrune/homely-tools](https://github.com/hansrune/homely-tools) - MQTT-based alternative with Domoticz support

---

## Features

### Real-Time Updates

- WebSocket push notifications for instant state changes
- Automatic reconnection with exponential backoff
- REST API fallback when WebSocket unavailable
- Dynamic polling (30s-30min based on connection health)

### Supported Entities

- **Binary Sensors**: Motion, entry (door/window), flood, smoke, tamper, battery status
- **Sensors**: Alarm state, temperature, signal strength, energy/metering
- **Buttons**: Manual refresh trigger

### Multi-Location

- Manage multiple Homely locations from single HA instance
- Independent WebSocket per location

---

## Installation

### HACS (Recommended)

1. HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/bjafl/homely-ha` (Integration)
3. Install and restart Home Assistant

_Working for future inclusion in HACS_

### Manual

Copy `custom_components/homely` to your HA `custom_components` directory and restart.

---

## Setup

1. **Settings** → **Devices & Services** → **+ Add Integration**
2. Search "Homely"
3. Enter credentials (same as Homely app)
4. Select locations to monitor

**Reconfigure**: Click **Configure** on the integration card to change locations.

---

## Requirements

- Home Assistant 2025.1.0+
- Active Homely alarm system
- Internet connectivity (cloud API)

---

## Architecture

```
Homely Cloud API (sdk.iotiliti.cloud)
    ↓
[REST API] ← Initial state & periodic validation
[WebSocket] ← Real-time push updates
    ↓
DataUpdateCoordinator → HA Entities
```

**Hybrid approach**: WebSocket primary, REST fallback/validation

---

## Development

Claude AI has been used in development. See [CLAUDE.md](CLAUDE.md) for generated project details, and  [QUALITY_ASSESSMENT.md](QUALITY_ASSESSMENT.md) for analysis of current quality standards and goals.

**API Documentation**: [bjafl/homely-api-docs](https://github.com/bjafl/homely-api-docs)

**Quick Start**
```bash
pip install -e ".[dev]"
pre-commit install
pytest                    # Run tests (85% coverage)
ruff check . && mypy custom_components/homely
```

**Docker Test Server**

Test the integration in a containerized Home Assistant instance:

```bash
# Start test server
docker compose up -d

# View logs
docker compose logs -f

# Stop server
docker compose down
```

Access at `http://localhost:8123`. The integration is automatically available at **Settings** → **Devices & Services** → **Add Integration** → **Homely**.

Configuration stored in `.ha_docker_test/config/`.

*Note: If you need `sudo` for docker commands, add yourself to the docker group: `sudo usermod -aG docker $USER` (logout/login required)*

---

## Troubleshooting

**WebSocket not updating**
- Check logs for connection errors
- Integration auto-reconnects (exponential backoff)
- REST polling continues as fallback
- Use "Trigger Refresh" button for manual update

**Authentication errors**
- Verify credentials match Homely app
- Token refresh is automatic
- Reload integration if issues persist

**No entities**
- Ensure at least one location selected during setup
- Check Homely system has configured devices
- Review HA logs for errors

---

## Known Limitations

- Cloud-dependent (no local API available)
- Read-only (arm/disarm not yet implemented)
- Requires internet connectivity

---

## Contributing

1. Fork repository
2. Create feature branch
3. Add tests (maintain ≥85% coverage)
4. Run `pre-commit run --all-files`
5. Submit PR

See [QUALITY_ASSESSMENT.md](QUALITY_ASSESSMENT.md) for quality standards.

---

## Project Status

**Version**: 0.1.0 (Beta)
**Quality Tier**: Bronze-Ready (90% complete)
**Type Coverage**: 87% (116/133 functions)
**Test Coverage**: 85%

### Recent Improvements
- ✅ WebSocket alarm state updates
- ✅ Docker test environment
- ✅ MyPy clean, comprehensive docstrings
- ✅ Branding assets created
- ✅ API documentation (bjafl/homely-api-docs)

### Roadmap

**High Priority (v1.0)**
- [ ] Submit to home-assistant/brands (30 min + approval wait)
- [ ] Fix config paths in pyproject.toml line 99
- [ ] Alarm control platform (arm/disarm/arm_night/arm_home)
- [ ] Submit to HACS default repository

**Medium Priority (v1.1+)**
- [ ] Increase test coverage to 90%+
- [ ] Complete type hints (17 functions remaining)
- [ ] Configuration options (polling intervals, entity filtering)
- [ ] Example automations documentation

**Low Priority (v1.2+)**
- [ ] Diagnostic sensors (connection status, API metrics)
- [ ] Additional translations
- [ ] Performance optimizations

---

### Quality Metrics

- **Type annotations**: 87% (up from 68%, target: 100%)
- **Test coverage**: 85% (Bronze ✅, Silver needs 90%+)
- **Linting**: Clean (ruff + mypy)
- **Docstrings**: Needs review

See [QUALITY_ASSESSMENT.md](QUALITY_ASSESSMENT.md) for detailed analysis.

---

## Support

- **Issues**: [GitHub Issues](https://github.com/bjafl/homely-ha/issues)
- **Documentation**: [GitHub Repository](https://github.com/bjafl/homely-ha)

---

## License

MIT License - see [LICENSE](LICENSE)

---

## Acknowledgments

- [Homely](https://homely.no/) alarm system
- [Home Assistant](https://www.home-assistant.io/)
- [HACS](https://hacs.xyz/)
- [hansrune/homely-tools](https://github.com/hansrune/homely-tools) - Pioneering MQTT integration
- Developed with [Claude Code](https://claude.ai/code) by Anthropic
