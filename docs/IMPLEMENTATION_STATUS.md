# Implementasjonsstatus — sensor-data-utvidelser

> Oppslagstabell for hva som er gjort vs gjenstår, koblet mot `docs/SENSOR_DATA_MAPPING.md`
> (seksjons-/tabellnumre under refererer dit). Oppdateres fortløpende.
>
> Status: ✅ ferdig · 🚧 pågår · ⬜ ikke startet

---

## 🤝 Handoff til neste agent (les dette først)

**Branch:** `feature/app-api` (IKKE merget til `main`). Alt arbeid under skjer her.

**Kjør tester:** `.venv/bin/python -m pytest tests/ -p no:cacheprovider`
- Coverage-gate: 85 % (ligger nå på ~90 %). Bruk `--no-cov` for raske enkeltkjøringer.
- `ruff`/`mypy` er IKKE installert i `.venv` — de kjøres via pre-commit. Skriv mypy-ren kode (full annotering, ingen `# type: ignore`).
- **TDD brukes konsekvent**: skriv failing test → se RED → minimal kode → GREEN. Se `superpowers:test-driven-development`.

**Datakilder (fanget app-API-trafikk):**
- `~/source/sniffs/homely_sniffs.json` — ren, filtrert Homely-trafikk (REST + WS). Primær referanse.
- `/tmp/capture.mitm` — full mitmproxy-dump (rik gateway-logg her).
- Analyse: `API_GAP_ANALYSIS.md`, `docs/SENSOR_DATA_MAPPING.md` (datamapping + entitetstype-tabeller).

**Etablerte mønstre (følg disse):**
- **Gateway-entiteter:** arve `HomelyGatewayEntity`-mixin (`base_sensor.py`) — fester på `(DOMAIN, location_id)`-enheten + setter firmware som `sw_version`. Brukt av gateway-sensorer i `binary_sensor.py` og `sensor.py`.
- **Alarm-state:** `AlarmState`-enum har `_missing_` med regex-fallback (ukjent verdi → best-effort + WARNING, krasjer aldri). Kanonisk `_ALARM_STATE_MAP` bor i `alarm_control_panel.py` og importeres av `sensor.py` (ikke dupliser).
- **Event-entitet:** `HomelyHomeState.last_alarm_event` lagrer siste WS-alarm-event; `event.py` fyrer på coordinator-update (replayer aldri pre-eksisterende event).
- **Translations:** `custom_components/homely/translations/{en,nb}.json`, struktur `entity.<platform>.<key>.name`. **Legg til for HVER ny entitet** (begge språk).
- **Test-mock:** `conftest.create_mock_device_features()` defaulter ALLE features til `None` (speiler modellen). Legger du til en ny feature i `DeviceFeatures`, legg den til som `None` der også.

**Anbefalt neste steg (prioritert):**
1. **#3 `isAlarmDevice`-deteksjon** (kall-fritt) — erstatt skjør `modelName`-regex i `binary_sensor.pick_alarm_classes` med `device.isAlarmDevice` + feature-tilstedeværelse. Krever å parse `isAlarmDevice` i `Device`-modellen.
2. **#5 Opprydding** — verifiser energi-skalering (Wh→kWh i `HomelyEnergySensor`), vurder å fjerne `metering.check`-sensoren (uklar semantikk).
3. **#4 GSM/wifi-signal** — nytt kall `GET /gateways/{id}/networks` (gsm.state/signalStrength/operator). Krever utvidelse av coordinator-henting.
4. **#6 `event.homely_zone_event`** — zone-faults fra `GET /gateways/{id}/history-log` (nytt kall; rik logg med ac_mains_fault/battery_fault per sone).
- Småting: røykvarsler-batteri via `alarm.{low,batteryDefect}`.
- **Bevisst utelatt:** panikk/nødknapp (`armevent.emergencyevent`) — brukeren utsatte den.

**Commits så langt på branchen (nyeste sist):**
`3e3127e` alarm-robusthet+gateway · `f4af60c` docs · `4a8e9b9` gateway-tallsensorer+mixin · `d0d7288` remainingPinAttempts · `d1a4d6d` device-online · `03cd883` event-entitet · `3f81fb3` siren/keypad

---

## Alarm-state-robusthet (tidligere arbeid)
| Tiltak | Status | Hvor |
|---|---|---|
| `ARMED_STAY` (fiks `ARMED_PARTLY`-regresjon) | ✅ | models/alarm_control_panel/sensor |
| `ARM_STAY_PENDING` → ARMING | ✅ | models + state-map |
| `ALARM_STAY_PENDING` → PENDING | ✅ | state-map |
| Tolerant state-parsing + regex-fallback + WARNING | ✅ | `models.AlarmState._missing_` |
| Dedupe av duplikat state-map | ✅ | sensor importerer kanonisk map |

## Gateway / hjemmesentral som egen enhet (Tabell 1) — 🚧
Kilde: `/home → gateway.features` (ingen nye kall). Tester: `tests/.../test_gateway.py`.

| Entitet | Kildefelt | Type / device_class | Status |
|---|---|---|---|
| Modell-parsing av `gateway.features` | power/connection/status | pydantic `Gateway` + `HomeResponse.gateway` | ✅ |
| Gateway-enhet (DeviceInfo + `sw_version`) | gateway + `firmwareVersion` | fester på `(DOMAIN, location_id)` | ✅ |
| AC-strøm | `power.acPower` | binary_sensor POWER | ✅ |
| Lavt batteri | `power.batteryLow` | binary_sensor BATTERY (diag) | ✅ |
| Tilkoblet | `gateway.online` | binary_sensor CONNECTIVITY (diag) | ✅ |
| Batterinivå | `power.batteryPercent` | sensor BATTERY % (diag) | ✅ |
| Batterispenning | `power.batteryVoltage` | sensor VOLTAGE (diag) | ✅ |
| Forsyningsspenning | `power.powerSourceVoltage` | sensor VOLTAGE (diag) | ✅ |
| Tilkoblingskilde | `connection.source` | sensor ENUM (diag) | ✅ |
| Delt mixin `HomelyGatewayEntity` (base_sensor) | — | refaktor | ✅ |
| Firmware (egen update-entitet) | `status.firmware*` | update-entitet | ⬜ (sw_version satt) |
| GSM-signal/operatør | `/gateways/{id}/networks` | sensor ENUM (diag) — nytt kall | ⬜ |

## Enhetsliste-felter (Tabell 4) — 🚧
| Tiltak | Felt | Status |
|---|---|---|
| `via_device` → gateway | (via `location_id`) | ✅ (allerede i `base_sensor`) |
| manufacturer | serie-prefiks (`get_manufacturer`) | ✅ delvis — kan suppleres med `modelVendor` |
| Online per enhet | `online` | ✅ (binary_sensor CONNECTIVITY per enhet) |
| Robust deteksjon via `isAlarmDevice` + `sensorsConnectedDeviceType` | strukturert motion/entry, regex som fallback | ✅ |
| Alarmprofil/-reaksjon som diag-attr | `alarmProfile*`/`alarmReaction*` | ⬜ |

## Device-features ikke fanget (Tabell 5) — 🚧
| Tiltak | Feature.state | Status |
|---|---|---|
| Panikk/nødknapp | `armevent.emergencyevent` | ⬜ (utelatt nå) |
| Sirene AC/batteri/tamper | `siren.{acmains,battery,tamper}` | ✅ (POWER/BATTERY/TAMPER) |
| Keypad tamper | `panel.tamper` | ✅ (TAMPER) |
| Keypad batteri | `panel.battery` | ⬜ (dekkes av `battery`-feature) |
| Røykvarsler-batteri | `alarm.{low,batteryDefect}` | ⬜ |

## Hendelseslogg → HA (Tabell 2/3) — ⬜
| Tiltak | Kilde | Status |
|---|---|---|
| `event.alarm_action` (arm/disarm + hvem) | WS `alarm-state-changed` | ✅ (lagrer `last_alarm_event`, fyrer på coordinator-update) |
| `event.homely_zone_event` (entry/zone-faults) | `/gateways/{id}/history-log` | ⬜ (krever nytt kall) |
| `remainingPinAttempts`-sensor (diag, på alarm-enheten) | `/home` | ✅ |

## Oppfølging / polish
| Tiltak | Status |
|---|---|
| Oversettelsesnøkler for gateway-entiteter (en + nb) | ✅ (alle 7 gateway-entiteter) |

## Opprydding i eksisterende (Tabell 6) — ⬜
| Tiltak | Status |
|---|---|
| Verifiser energi Wh→kWh-skalering | ⬜ |
| Vurder fjerning av `metering.check`-sensor | ⬜ |
| Thermostat: setpoints ut av attributter | ⬜ |
