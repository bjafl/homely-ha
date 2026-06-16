# Homely — sensor-data-mapping & entitets-gjennomgang

> Grunnlag: fanget app-trafikk (Homely iOS 1.28.0) + kildegjennomgang av `feature/app-api`.
> Fokus: **lese-data** (sensorer/diagnostikk/logg), ikke skrive-/kommando-verktøy.
> Entitetstype-anbefalinger bygger på HA-plattformkunnskap (HA 2025.1+); de lokale nexus-docene dekker ikke utvikler-referansen for entity-plattformer.

---

## DEL A — Gjennomgang av dagens entiteter (er typevalgene fornuftige?)

| Entitet | device_class / state_class | Vurdering |
|---|---|---|
| `HomelyAlarmStateSensor` (enum) | ENUM | ✅ Fornuftig. Overlapper med alarm-panelet, men en egen enum-sensor er nyttig for historikk/automasjon. **NB:** enum-options må matche faktiske API-verdier — `ARMED_STAY` mangler i dag (jf. `ARMED_PARTLY`-bugen). |
| `HomelyTemperatureSensor` | TEMPERATURE / MEASUREMENT | ✅ Korrekt. |
| `HomelySignalStrengthSensor` | (ingen) %, DIAGNOSTIC | ⚠️ OK, men `SensorDeviceClass.SIGNAL_STRENGTH` er dBm, ikke %, så å la device_class være tom er riktig. Bør konsolidere `signal_strength` (app-API) vs `network_link_strength` (SDK) til ett felt. |
| `HomelyEnergySensor` (delivered/received) | ENERGY / TOTAL_INCREASING | ✅ Riktig klasse. ⚠️ **Verifiser enhet/skalering** — rå `summationdelivered` er sannsynligvis Wh, må skaleres til kWh ellers blir Energy-dashboardet feil. |
| `HomelyEnergyDemandSensor` | POWER / MEASUREMENT | ✅ Riktig. ⚠️ Verifiser W vs kW. |
| `HomelyEnergyCheckSensor` (metering.check) | PROBLEM | ❓ Uklar betydning ("check"). Anbefaler å fjerne til semantikken er bekreftet — en udokumentert PROBLEM-sensor skaper falske alarmer. |
| `HomelyThermostatSensor` | TEMPERATURE (read-only) + setpoints som attributter | ⚠️ Setpoints/mode gjemt i attributter er lite oppdagbart. Hvis bare lesing: del ut egne sensorer (heating/cooling-setpoint). Hvis styring senere: en `climate`-entitet er riktig hjem. |
| Binærsensorer: motion/entry/smoke/tamper/flood | MOTION / OPENING / SMOKE / TAMPER / MOISTURE | ✅ Alle korrekte. |
| `HomelyBatteryLowSensor` / `HomelyBatteryDefectSensor` | BATTERY / PROBLEM, DIAGNOSTIC | ✅ Korrekt. |

### Tverrgående funn (dagens design)
1. **Entitetsdeteksjon via `modelName`-regex** (`RE_MOTION_SENSOR`/`RE_ENTRY_SENSOR`) er skjør. API-et gir `isAlarmDevice` (bool) + per-enhet `features` + `alarmTypes` — bruk dem i stedet for å gjette på navn.
2. **`manufacturer` er hardkodet "Homely"** i `DeviceInfo`. API-et gir `modelVendor` (`frient A/S`, `Fireangel`) — bør brukes.
3. **Ingen gateway-enhet i HA.** Gateway-en brukes kun som `serialNumber` på alarm-panelet. Den har rik egen telemetri (se Del B1) og fortjener å være sin egen HA-`device`.
4. **`sw_version` settes ikke** på DeviceInfo. Gateway-firmware finnes (`status.firmwareVersion`).
5. **Manglende `via_device`** — Zigbee-enhetene burde knyttes til gateway-enheten (`via_device`) for korrekt enhetstre.

---

## DEL B — Nye datakilder → entitets-/enhetsmapping

### B1. Hjemmesentral (gateway) som egen HA-enhet ⭐
**Kilde: `/home → gateway.features` — hentes allerede, parses ikke.** Null nye API-kall.

Ny `DeviceInfo`: `identifiers={(DOMAIN, gateway_id)}`, `manufacturer="Homely"`, `model` fra `modelId`, `sw_version=status.firmwareVersion`, `serial_number=gateway.serialNumber`. Zigbee-enheter får `via_device=(DOMAIN, gateway_id)`.

| Ny entitet | Type / device_class | Kilde-felt |
|---|---|---|
| Strømforsyning (AC) | `binary_sensor` / **POWER** (on=på nett) | `power.acPower` |
| Batterinivå | `sensor` / **BATTERY** %, MEASUREMENT, DIAGNOSTIC | `power.batteryPercent` |
| Lavt batteri | `binary_sensor` / **BATTERY**, DIAGNOSTIC | `power.batteryLow` |
| Batterispenning | `sensor` / **VOLTAGE** V, MEASUREMENT, DIAGNOSTIC | `power.batteryVoltage` |
| Forsyningsspenning | `sensor` / **VOLTAGE** V, DIAGNOSTIC | `power.powerSourceVoltage` |
| Tilkoblet (online) | `binary_sensor` / **CONNECTIVITY** | `gateway.online` |
| Tilkoblingskilde | `sensor` / **ENUM** (ethernet/wifi/gsm), DIAGNOSTIC | `connection.source` (+ `/gateways/{id}/networks`) |
| GSM-status/operatør/signal | `sensor` / **ENUM** + attributter, DIAGNOSTIC | `/gateways/{id}/networks → gsm{state,signalStrength,networkOperatorName}` |
| Firmware | `update`-entitet / **FIRMWARE** (installed=firmwareVersion, latest=firmwareTargetVersion) eller diagnostisk sensor | `status.{firmwareVersion,firmwareTargetVersion,firmwareUpdate.status}` |

> `acPower` + `batteryLow` gir deg en ekte "strømbrudd på huset"-trigger — sentralen går på backup-batteri ved nettbortfall.

### B2. Gateway-hendelseslogg → HA ⭐
**To strømmer (som du beskrev):**

**(a) Rik, markerbar:** `GET /gateways/{id}/history-log` (+ `PATCH` = marker lest, utenfor scope her).
Event-typer fanget: `armedaway`, `armedstay`, `disarmed`, `entrytriggered`, `zonechanged`, `zoneflagclear`, `uplinkstate`.
Felter: `id`, `status` (`unread`/`read`/`acknowledged`), `type`, `eventtime`, `receipt`/`receipttime` (ARC-kvittering), `requireAcknowledge`, og enten:
- `user{id,userEmail,userRole,userName}` (arm/disarm) eller
- `zone{id,device,alarm1,alarm2,tamper,test,battery_fault,ac_mains_fault,trouble_fault,supervision_fault,deviceSerialNumber,deviceId}` (zone-events).

**(b) Mindre detaljert:** `GET /alarm/activities/{id}` (DynamoDB-paginert, `data[]` + `lastKey`). Var tom i fangsten (deviceId-filtrert) — innhold ikke verifisert. Sannsynligvis det rene alarm-feed-et (arm/disarm/brudd) appen viser på forsiden.

**Anbefalt HA-mapping:**
| Behov | Entitet | Kilde |
|---|---|---|
| Arm/disarm-aktivitet (hvem/når) | `event`-entitet `homely_alarm_action`, `event_types=[armed_away,armed_stay,disarmed,...]`, attributter `user_name/user_email/user_role` | history-log arm/disarm **eller** WS `alarm-state-changed` (live, har `userName`) |
| "Sist endret av" | attributt på alarm-panelet | samme |
| Inngang utløst / zone-fault | `event`-entitet `homely_zone_event` + attributter (fault-flagg) | history-log zone-events |
| Gateway-tilkobling endret | binary_sensor CONNECTIVITY (allerede i B1) eller event | `uplinkstate` |

> **`event`-plattformen (EventEntity)** er det idiomatiske hjemmet for diskrete, tidsstemplede hendelser som dette — bedre enn å presse dem inn i en tekst-sensor. Hver event blir synlig i HA-logbook automatisk.

> **Anbefaling om kilde:** baser arm/disarm-historikk på **WS `alarm-state-changed`** (sanntid, `userName`, allerede tilkoblet) for live-bruk, og bruk `history-log` for **etterfylling ved oppstart** (den har full bruker-info + ARC-kvittering). De to strømmene utfyller hverandre — WS er live men flyktig; history-log er persistent med rikere felt.

### B3. Flere felt fra enhetslisten (`/home → devices[]`) ⭐
Hentes allerede, ignoreres i dag:

| Felt | Forslag |
|---|---|
| `modelVendor` | → `DeviceInfo.manufacturer` (erstatt hardkodet "Homely") |
| `deviceType` (`ZIGBEE`) | diagnostisk attributt |
| `isAlarmDevice` | robust entitetsdeteksjon + diagnostisk attributt |
| `online` (per enhet) | `binary_sensor` CONNECTIVITY per enhet |
| `alarmProfileNight/Stay/Away` | diagnostiske attributter (hvilke profiler enheten inngår i) |
| `alarmReactionNight/Stay/Away` (`NORMAL`/`ENTRY_EXIT`) | diagnostisk attributt (forklarer inngangsforsinkelse) |
| `features.alarm.{low,batteryDefect}` | røykvarsler-batteri (egne enheter mangler battery-feature, men rapporterer via alarm) |
| `features.alarm.sensitivitylevel` | diagnostisk sensor |
| **`features.armevent.emergencyevent`** (keypad) | ⭐ `binary_sensor` SAFETY / event — **panikk-/nødknapp** |
| `features.panel.{battery,tamper}` (keypad) | keypad-batteri/tamper-sensorer |
| `features.siren.{acmains,battery,tamper,conflevel}` | sirene: `acmains` → binary_sensor POWER, battery, tamper |

### B4. `remainingPinAttempts` (location-nivå) ⭐
**Kilde: `/home` top-nivå — hentes allerede.** → `sensor` (DIAGNOSTIC, antall PIN-forsøk igjen). Direkte nyttig: gir varsel før lockout, og forklarer disarm-feil i UI (jf. `code 2023, "Remaining attempts: N"`).

### B5. Tidsserie per enhet (`/features-history`)
`GET /devices/{id}/features-history?limit=&offset=` gir per-feature-tidsserie (`featureState`, `value`, `lastUpdated`).
**Anbefaling (i tråd med din intuisjon):** *ikke* gjør dette til primærkilde. Siden integrasjonen allerede følger WS-strømmede state-endringer, fører HA sin egen `recorder`-historikk — vanligvis bedre og finere oppløst. Bruk `features-history` kun som **valgfri etterfylling ved oppstart** for å tette hullet siden forrige tilkobling (avansert/lav prioritet). Gateway-power-historikk er det eneste stedet dette gir unik verdi *hvis* gateway-power ikke strømmes via WS — bør verifiseres.

---

## DEL C — Sammendrag: anbefalte nye entiteter

**Ny enhet: Hjemmesentral (gateway)**
- binary_sensor: AC-strøm (POWER), lavt batteri (BATTERY), tilkoblet (CONNECTIVITY)
- sensor: batteri % (BATTERY), batterispenning (VOLTAGE), forsyningsspenning (VOLTAGE), tilkoblingskilde (ENUM), GSM (ENUM+attr)
- update/diag: firmware
- event: `homely_alarm_action`, `homely_zone_event`

**Eksisterende enheter — utvidelser**
- alarm-panel: attributt `last_changed_by` (WS `userName`)
- per enhet: online (CONNECTIVITY), manufacturer=`modelVendor`, via_device=gateway, alarmprofil-attributter
- keypad: panikk (SAFETY), batteri, tamper
- sirene: AC (POWER), batteri, tamper
- location: `remainingPinAttempts` (DIAGNOSTIC)

**Opprydding i eksisterende**
- Legg `ARMED_STAY` til alarm-state-enum (fiks `ARMED_PARTLY`-bug)
- Verifiser energi-enhet/skalering (Wh→kWh, W)
- Vurder å fjerne `metering.check`-sensoren til semantikk er bekreftet
- Bytt `modelName`-regex-deteksjon mot `isAlarmDevice` + feature-tilstedeværelse

---

## Datakilde-oppsummering (hva er allerede hentet vs nytt kall)

| Datakilde | Status | Nytt API-kall? |
|---|---|---|
| gateway.features (AC/batteri/firmware/connection) | i `/home` | **Nei** |
| `remainingPinAttempts`, device-ekstrafelter, alarmprofiler | i `/home` | **Nei** |
| arm/disarm "av hvem" | WS `alarm-state-changed` | **Nei** (allerede tilkoblet) |
| Rik hendelseslogg (zone-faults, ARC, etterfylling) | `/gateways/{id}/history-log` | Ja |
| GSM/wifi-detaljer | `/gateways/{id}/networks` | Ja |
| Mindre detaljert alarm-feed | `/alarm/activities/{id}` | Ja (innhold uverifisert) |
| Per-enhet tidsserie | `/devices/{id}/features-history` | Ja (lav prioritet) |

> Mye av den høyest-verdifulle utvidelsen krever **ingen nye kall** — den ligger i `/home`-responsen integrasjonen allerede mottar, men bare parser ~30 % av.
