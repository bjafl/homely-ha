# Homely app-API — gap-analyse

> Diff mellom **fanget app-trafikk** (mitmproxy-dump av Homely iOS-app 1.28.0, juni 2026) og **hva `homely` HA-integrasjonen (`feature/app-api`) faktisk bruker**.
> Mål: kartlegge informasjon og funksjonalitet som finnes i API-et men som integrasjonen ikke utnytter.
> Lokasjon i dumpen: `f32bf453-…` ("Hjem"), 11 enheter, gateway `eafa2c31-…`.

## TL;DR — størst verdi først

1. **`remainingPinAttempts`** ligger i `/home`-responsen — integrasjonen kaster det. Å eksponere det (sensor + logge i disarm-feil) ville gjort hele disarm-PIN-saken selvforklarende.
2. **`armevent` / `panel`-features på keypad** (panikk/nød-knapp, keypad-batteri/tamper) fanges ikke → en sikkerhetsfunksjon mangler i HA.
3. **15 REST-endepunkter** appen bruker kalles aldri av integrasjonen (rules-engine, scenes, device-groups, activity-logs, gateway-nettverk/wifi, ARC-abonnement, feature-historikk).
4. **Siren- og AC-mains-tilstand** parses ikke → ingen "alarm utløst (sirene)"- eller "strømbrudd på sirene"-sensor.
5. Rik **device-metadata** (rom-hierarki, adresse/GPS, alarmprofiler/-reaksjoner per enhet, `isAlarmDevice`, `deviceType`) ignoreres.

---

## 1. Endepunkter appen bruker — som integrasjonen ALDRI kaller

Integrasjonen kaller kun: `oauth/v2/token`, `oauth/v2/refresh-token`, `/locations`, `/home/{id}`, `/alarm/state/{id}`, `/alarm/arm`, `/alarm/disarm`, og WebSocket. Alt under er fanget i appen men ubrukt:

| Endepunkt | Hva det gir | HA-potensial |
|---|---|---|
| `GET /rule-engine/rules?locationId=` | Automasjonsregler ("God morgen" kl 06:30 → DISARM, "Sov godt" kl 23:00 → ARMED_STAY) m/ `alarmMode`, `ruleType`, triggers, ukedager | Vis/styr Homely-regler; lese-bekreft hvorfor alarmen skifter selv |
| `GET /device-groups?locationId=` | Enhetsgrupper | Gruppering/rom i HA |
| `GET /device-groups/scenes?locationId=` | Scener | Knapp/scene-entiteter |
| `GET /alarm/activities/{id}?deviceId=` | Alarm-hendelseslogg (DynamoDB-paginert, `data[]`, `lastKey`) | Logbook: hvem armet/disarmet når, brudd |
| `GET /devices/{id}/activity-log` | Per-enhet hendelseslogg | Diagnostikk/historikk |
| `GET /devices/{id}/features-history?limit=&offset=` | **Full tidsserie per feature-state** (`value`, `lastUpdated`, 34 pkt/kall) | Historikk-import, langtidsstatistikk |
| `GET /gateways/{id}/networks` | `connectionSource`, `wifiNetwork{name,connected}`, `gsm{state,signalStrength,networkOperatorName}` | Gateway-helse: wifi/GSM-tilkobling + signalstyrke som sensorer |
| `GET /gateways/{id}/features/wlan/states/configuration` | `ssid`, `encryption`, `autoConnect` | Diagnostikk |
| `GET /gateways/{id}/history-log` (+ `PATCH`) | Gateway hendelseslogg (tekst) | Diagnostikk |
| `GET /arc/membership/{id}/status` | ARC-status (Alarm Response Center / vekterabonnement) | Binær/diag-sensor: er proff-overvåkning aktiv |
| `GET /locations/{id}/services` | Tilgjengelige tjenester for lokasjonen | Feature-gating |
| `GET /dashboard` | (tomt `{}` her) | Sannsynligvis ubrukelig |

---

## 2. Felter i `/home`-responsen som integrasjonen ignorerer

Integrasjonen parser kun: `location.{id,name}`, `gateway.serialNumber`, `devices[]` (utvalgte felter), `alarmState`, `userRoleAtLocation`.

### Top-nivå (kastes)
`heatingRules`, `arcServiceStatus`, `deviceGroups`, `scenes`, `rules`, **`remainingPinAttempts`**, `independentLivingRules`, `independentLivingServiceStateLogs`, `hasAmsAvailableDevices`

- **`remainingPinAttempts`** ⭐ — antall PIN-forsøk igjen før lockout. Burde vært sensor + brukt i disarm-feilmelding (jf. disarm-saken: serveren returnerer `code 2023, "Remaining attempts: N"`).
- **`arcServiceStatus`** (`enabled`) — om profesjonell alarmrespons er aktiv.
- **`rules`** — speiler `/rule-engine/rules` (automasjoner inkl. tidsstyrt arming).

### Location-nivå (kastes)
`children` (rom/under-lokasjon-hierarki), `address` (gate, postnr, by, **lat/long**), `partnerId`, `partnerCompanyId`, `partnerCode`, `isCertifiedMode`, `locationType`

- **`children`** — hele rom-/sonehierarkiet (enheter har `locationId` som peker hit) → kunne gitt rom-tilordning/areas i HA.
- **`address.latitude/longitude`** — kunne satt HA-enhetens posisjon/sone.

### Device-nivå (kastes)
`manualName`, `createdAt`, `updatedAt`, `gatewayGeneratedId`, `configProgressPercentage`, `modelVendor`, **`isAlarmDevice`**, `amsService`, `alarmTypes`, `deviceType`, og hele **`settings`**-objektet:
`accessType`, `commonDoorActive`, `placement`, `independentLiving`, `keypad`, og
**`alarm.{alarmProfileNight, alarmProfileStay, alarmProfileAway, alarmReactionNight, alarmReactionStay, alarmReactionAway}`** (+ samme felter speilet på device-toppnivå)

- **`isAlarmDevice`** ⭐ — boolsk; ville gjort entitets-deteksjon robust i stedet for `modelName`-regex (`RE_MOTION_SENSOR`/`RE_ENTRY_SENSOR`).
- **`deviceType`** (`ZIGBEE`) — naturlig diagnostikk-attributt.
- **`alarmProfile*` / `alarmReaction*`** — per-enhet: hvilke profiler enheten inngår i, og reaksjonstype (`NORMAL` / `ENTRY_EXIT`). Forklarer inngangsforsinkelse.
- **`modelVendor`** (`frient A/S`, `Fireangel`) — burde vært `manufacturer` i `DeviceInfo` (nå hardkodet "Homely").

---

## 3. Device-features og state-nøkler som ikke håndteres

Integrasjonen håndterer: `alarm{alarm,tamper,flood,fire}`, `temperature`, `battery{low,defect,voltage}`, `diagnostic`, `metering`, `thermostat`, `siren{alarm}`.

Fanget i dumpen, men **ikke** håndtert:

| Feature | State-nøkler i dump | Mangler |
|---|---|---|
| **`armevent`** ⭐ | `code`, `emergencyevent` | **Panikk-/nødknapp på keypad** — sikkerhetshendelse, helt usurfacet |
| **`panel`** | `battery`, `tamper` | Keypad-panelets batteri + tamper |
| **`siren`** | `acmains`, `battery`, `conflevel`, `tamper` | Integrasjonen leser kun `siren.alarm` (som ikke fantes her); **`acmains`** = strømbrudd-deteksjon på sirene |
| **`setup`** | `appledenable`, `errledenable` | LED-konfig (lav verdi) |
| **`alarm`** (ekstra) | `low`, `batteryDefect`, `sensitivitylevel` | Røykvarsler-batteri via alarm-feature; `sensitivitylevel` |

Enhetstyper i dumpen: `Alarm Entry Sensor 2`, `Alarm Motion Sensor 2`, `Window Sensor`, `Alarm Keypad`, `Alarm Siren`, `Intelligent Smoke Alarm`, `Fireangel SD Device`. **Keypad og sirene** eksponeres i praksis ikke (ingen av deres unike features fanges).

---

## 4. Funksjonalitet (skriv/kommandoer) som ikke er implementert

Integrasjonen skriver kun: `/alarm/arm`, `/alarm/disarm`. Appen viser at API-et også støtter:
- **Regelmotor** (`/rule-engine/rules`) — opprette/endre tidsstyrt arming.
- **Scener** (`/device-groups/scenes`).
- **Gateway-historikk kvittering** (`PATCH /gateways/{id}/history-log`).

---

## 5. WebSocket — delvis utnyttet

Integrasjonen lytter på `device-state-changed` og `alarm-state-changed`. `alarm-state-changed` bærer `userId`, `userName`, `eventId`, `timestamp` — disse parses i modellen men **eksponeres ikke** (kunne blitt attributter: "sist endret av X"). `/alarm/state`-responsen har også et `timestamp` som ignoreres.

---

## 6. Anbefalte HA-tillegg (prioritert)

| # | Tillegg | Kilde | Innsats |
|---|---|---|---|
| 1 | **PIN-forsøk-sensor** + bedre disarm-feil | `remainingPinAttempts` (allerede i `/home`) | Lav — data finnes alt |
| 2 | **Panikk/nød-binærsensor** | `armevent.emergencyevent` (WS + `/home`) | Middels |
| 3 | **Sirene: strømbrudd + tamper** | `siren.acmains/tamper` | Lav |
| 4 | **`isAlarmDevice` → robust entitetsdeteksjon** | `/home` device-felt | Lav (erstatter regex) |
| 5 | **Gateway wifi/GSM-signal-sensorer** | `/gateways/{id}/networks` | Middels (nytt kall) |
| 6 | **ARC-abonnement-status** | `/arc/membership/{id}/status` el. `arcServiceStatus` | Lav |
| 7 | **`modelVendor` → riktig manufacturer** | `/home` device-felt | Triviell |
| 8 | **Alarm-hendelseslogg → HA logbook** | `/alarm/activities/{id}` + WS `userName` | Middels |
| 9 | **Rom-/sone-tilordning** | `location.children` + device `locationId` | Høy |

> Merk: alle data over er fanget fra OWNER-kontoens egen trafikk. Felter kan variere mellom Homely-abonnement (ARC/AMS/independent-living ser ut til å være betalte tillegg).
