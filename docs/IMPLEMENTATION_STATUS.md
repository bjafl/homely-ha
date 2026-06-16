# Implementasjonsstatus — sensor-data-utvidelser

> Oppslagstabell for hva som er gjort vs gjenstår, koblet mot `docs/SENSOR_DATA_MAPPING.md`
> (seksjons-/tabellnumre under refererer dit). Oppdateres fortløpende.
>
> Status: ✅ ferdig · 🚧 pågår · ⬜ ikke startet

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
| Batterinivå | `power.batteryPercent` | sensor BATTERY % (diag) | ⬜ |
| Batterispenning | `power.batteryVoltage` | sensor VOLTAGE (diag) | ⬜ |
| Forsyningsspenning | `power.powerSourceVoltage` | sensor VOLTAGE (diag) | ⬜ |
| Tilkoblingskilde | `connection.source` | sensor ENUM (diag) | ⬜ |
| Firmware (egen update-entitet) | `status.firmware*` | update-entitet | ⬜ (sw_version satt) |
| GSM-signal/operatør | `/gateways/{id}/networks` | sensor ENUM (diag) — nytt kall | ⬜ |

## Enhetsliste-felter (Tabell 4) — 🚧
| Tiltak | Felt | Status |
|---|---|---|
| `via_device` → gateway | (via `location_id`) | ✅ (allerede i `base_sensor`) |
| manufacturer | serie-prefiks (`get_manufacturer`) | ✅ delvis — kan suppleres med `modelVendor` |
| Online per enhet | `online` | ⬜ |
| Robust deteksjon via `isAlarmDevice` | `isAlarmDevice` | ⬜ |
| Alarmprofil/-reaksjon som diag-attr | `alarmProfile*`/`alarmReaction*` | ⬜ |

## Device-features ikke fanget (Tabell 5) — ⬜
| Tiltak | Feature.state | Status |
|---|---|---|
| Panikk/nødknapp | `armevent.emergencyevent` | ⬜ |
| Sirene AC/batteri/tamper | `siren.{acmains,battery,tamper}` | ⬜ |
| Keypad batteri/tamper | `panel.{battery,tamper}` | ⬜ |
| Røykvarsler-batteri | `alarm.{low,batteryDefect}` | ⬜ |

## Hendelseslogg → HA (Tabell 2/3) — ⬜
| Tiltak | Kilde | Status |
|---|---|---|
| `event.homely_alarm_action` (arm/disarm + hvem) | WS `alarm-state-changed` + history-log | ⬜ |
| `event.homely_zone_event` (entry/zone-faults) | `/gateways/{id}/history-log` | ⬜ |
| `remainingPinAttempts`-sensor | `/home` | ⬜ |

## Oppfølging / polish
| Tiltak | Status |
|---|---|
| Oversettelsesnøkler for nye gateway-entiteter (`gateway_ac_power`/`gateway_battery_low`/`gateway_online`) i `strings.json` + `translations/` | ⬜ (entiteter virker, mangler lokaliserte navn) |

## Opprydding i eksisterende (Tabell 6) — ⬜
| Tiltak | Status |
|---|---|
| Verifiser energi Wh→kWh-skalering | ⬜ |
| Vurder fjerning av `metering.check`-sensor | ⬜ |
| Thermostat: setpoints ut av attributter | ⬜ |
