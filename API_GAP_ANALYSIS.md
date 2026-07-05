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
6. **`gateway.exitEntrySettings`** (også i `/home`, null nytt kall) gir nedtellings- og lydkonfig **per alarmmodus** (Away/Night/Stay) — helt udokumentert og ubrukt før nå. Se §2 og §5.

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
| `GET /locations/{id}/users` + `PUT /locations/{id}/users/{userId}` (body `{"role": "OWNER"\|"ADMIN"\|"USER"}`) | Full medlemsliste for lokasjonen (id/e-post/navn/rolle) + rolleendring | Vis hvem som har tilgang og med hvilken rolle; forklarer disarm-PIN-forskjeller mellom kontoer (jf. `remainingPinAttempts`-saken) |
| `GET /invitations/sent/{id}` | Utestående invitasjoner til lokasjonen | Diagnostikk (tomt array i fangsten — ingen ventende invitasjoner testet) |
| `GET /guest-users?locationId=` | Gjestebrukere for lokasjonen | Tomt i fangsten, men **antyder en fjerde rolletype `GUEST`** utover OWNER/ADMIN/USER — ubekreftet innhold |
| `POST /alarm/pin` (body `{"pin","locationId"}`) | Endre PIN-kode (separat fra `/alarm/disarm`) | Skriveoperasjon; broadcastes over WS som `alarm-pin-updated` med `userId` (PIN selv lekkes ikke over WS) |
| `PATCH /gateways/{id}/exit-entry` (body `{"exitEntrySettings": {"alarmProfileAway\|Night\|Stay": {"entryTime","entrySoundTime","exitTime","exitSoundTime","squawkLevel"}}, "sirenLevelEntryExit"?, "sirenLevelAlarm"?}`) | Nedtellings-/lydkonfig **per alarmmodus** | Se §2/§5 — full config allerede lesbar via `/home → gateway.exitEntrySettings`, dette er kun skrivesiden |
| `PATCH /devices/{id}/alarm-profile` (body `{"alarmProfileAway\|Night\|Stay": bool}`) | Enhets medlemskap i en alarmmodus | Speiler felt allerede lest fra `/home → devices[]` |
| `PATCH /devices/{id}/alarm-reaction` (body `{"alarmReactionAway\|Night\|Stay": "NORMAL"\|"ENTRY_EXIT"\|"FOLLOWER"}`) | Enhets reaksjonstype per modus | **`FOLLOWER`** er en tredje verdi oppdaget her, utover kjente `NORMAL`/`ENTRY_EXIT` (betydning ikke bekreftet — antatt: sensoren utløser ikke egen forsinkelse, men følger en annen sones) |

---

## 2. Felter i `/home`-responsen som integrasjonen ignorerer

Integrasjonen parser kun: `location.{id,name}`, `gateway.serialNumber`, `devices[]` (utvalgte felter), `alarmState`, `userRoleAtLocation`.

### Gateway-nivå (kastes) ⭐ nytt funn
**`gateway.exitEntrySettings`** — nedtellings- og lydkonfig **per alarmmodus**, verifisert juli 2026 (`~/source/sniffs/homely_alarm_modes_redacted.json`):

| Modus | `entryTime` | `entrySoundTime` | `exitTime` | `exitSoundTime` | `squawkLevel` (observert default) |
|---|---|---|---|---|---|
| `alarmProfileAway` (borte) | 30s | 25-30s | **60s** | 30s | `MediumLevelSound` |
| `alarmProfileNight` (natt) | **40s** | 30s | 20s | 0s | `LowLevelSound` |
| `alarmProfileStay` (delsikring) | 20s | 10-20s | 20s | 0-5s | `LowLevelSound` |

Pluss globale sirenenivåer på samme objekt: `sirenLevelStayDelay`, `sirenLevelEntryExit`, `sirenLevelNightDelay`, `sirenLevelAlarm` — alle enum `Off`/`LowLevelSound`/`MediumLevelSound`/`HighLevelSound`/`VeryHighLevelSound`.

Dette **er** de faktiske tidsverdiene bak nedtellingen dokumentert i §5 (STAY-testen traff nøyaktig `entryTime`/`exitTime`=20 for `alarmProfileStay`). Ingen nytt kall — allerede i `/home`-responsen integrasjonen henter.

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
- **`alarmProfile*` / `alarmReaction*`** — per-enhet: hvilke profiler enheten inngår i, og reaksjonstype (`NORMAL` / `ENTRY_EXIT` / **`FOLLOWER`** — sistnevnte nytt funn, se §1). Forklarer inngangsforsinkelse.
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
- **Gateway-historikk kvittering** (`PATCH /gateways/{id}/history-log`) — verifisert (juli 2026), to body-varianter:
  - `{"acknowledge": [eventId, ...]}` — kvitterer enkeltoppføringer, `200` med tom respons.
  - `{"acknowledgeAll": true}` — kvitterer alle utestående. Kan returnere `400` med `{"code": 2097, "message": "Some log updates failed while acknowledging", "details": {"updateLogResults": [{"id", "success", "error"?}, ...]}}` selv om de fleste lyktes — appen må lese `updateLogResults` per-id, ikke bare HTTP-status. Observert feil: `{"code": 2095, "message": "device in alarm"}` — en oppføring kan **ikke** kvitteres mens enheten den gjelder fortsatt står i aktiv alarmtilstand.
  - Loggoppføringer bærer `receipt`/`receipttime` som viser kvittering på to nivåer (`"Acknowledged by cloud; Acknowledged by ARC"`) — cloud- og ARC-kvittering er separate fra appens `acknowledge`-kall.
  - **Rolleendring** (`PUT /locations/{id}/users/{userId}`, body `{"role": "..."}`) hører også hjemme her — se tabell i del 1.
- **Alarmmodus-konfig** (`PATCH /gateways/{id}/exit-entry`, `PATCH /devices/{id}/alarm-profile`, `PATCH /devices/{id}/alarm-reaction`) — verifisert juli 2026, alle returnerer `200 null` uten valideringsfeil for noen av de testede kombinasjonene. Se tabell i del 1 og full nedtellingskonfig i §2.
- **PIN-endring** (`POST /alarm/pin`) — separat fra disarm, se del 1.

---

## 5. WebSocket — delvis utnyttet

Integrasjonen lytter på `device-state-changed` og `alarm-state-changed`. `alarm-state-changed` bærer `userId`, `userName`, `eventId`, `timestamp` — disse parses i modellen men **eksponeres ikke** (kunne blitt attributter: "sist endret av X"). `/alarm/state`-responsen har også et `timestamp` som ignoreres.

**Inngangsforsinkelse og `BREACHED` — nå verifisert (ny sniff juli 2026, se `~/source/sniffs/homely_alarm_roles_redacted.json`).** Full sekvens observert ved arm→trigger→disarm (`ARMED_STAY`-profil):

| Tid (relativt) | WS-event | `state`/felter |
|---|---|---|
| T+0.0s | `alarm-state-changed` (×5, samme payload resendt hvert ~5s) | `ARM_STAY_PENDING` |
| T+19.9s | `alarm-state-changed` | `ARMED_STAY`, `userId`/`userName` |
| — | `device-state-changed` (feature `alarm`, `value: true`) | sensor detekterer inntrenging |
| **+20.0s etter deteksjon** | `alarm-state-changed` | **`BREACHED`**, `eventId`, `userName: ""` |
| samtidig | **`device-alarm-triggered`** | `{"type": "BURGLARY", "deviceId", "locationId", "eventTime"}` — `eventTime` peker tilbake til faktisk deteksjonstidspunkt, ikke broadcast-tidspunktet |
| ved disarm | `alarm-state-changed` | `DISARMED`, `userId`/`userName`, `deviceId` |
| samtidig | **`device-alarm-restore`** | `{"type": "BURGLARY", "deviceId", "locationId"}` — nullstiller enhetens alarmtilstand |

Konklusjoner for implementasjon:
- **Ingen gjenstående-sekunder-felt finnes noe sted** — verken i `PENDING`-eventene eller REST (`/alarm/state`). Både exit-delay (arm→armed) og entry-delay (deteksjon→`BREACHED`) målt til **konsistent ~20 sekunder** i denne fangsten; en nedtellings-sensor i HA må beregnes klient-side (`now - arm_request_time` / `now - first_alarm_true_detection`) mot en antatt/konfigurert forsinkelse, ikke leses fra APIet.
- `device-alarm-triggered`/`device-alarm-restore` er **separate, enhetsspesifikke** events (type `BURGLARY` sett her — andre `alarmTypes` fra enhetslisten, f.eks. brann/vann, gir trolig samme eventtype med annen `type`-verdi) — disse bør trolig drive en egen `event`-entitet eller attributt på enhetens alarm-`binary_sensor`, atskilt fra det location-brede `alarm-state-changed`.
- `models.AlarmState`s regex-basert `_missing_`-fallback (`ALARM.*PENDING`) er nå bekreftet korrekt for `ARM_STAY_PENDING`; `BREACHED` bør legges til som eksplisitt enum-medlem siden payload-strukturen er verifisert.

**Tre nye WS-eventtyper oppdaget** (juli 2026, ved endring av alarmmodus-config i appen — se `homely_alarm_modes_redacted.json`), ingen av dem lyttet på i dag:

| Event | `eventData` | Notat |
|---|---|---|
| `exit-entry-settings-changed` | full `exitEntrySettings`-objekt (alle tre profiler + sirenenivåer, ikke bare det som endret seg) | Live-sync ved endring — kunne holdt en HA-konfig-sensor oppdatert uten polling |
| `device-info-changed` | full snapshot av ett device sine `alarmProfile*`/`alarmReaction*`-flagg | Tilsvarende live-sync per enhet |
| `alarm-pin-updated` | `{gatewayId, locationId, userId, userLocationId}` | Bekrefter hvem som endret PIN — bærer ikke selve PIN-en |

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
| 10 | **Alarmmodus-nedtelling som diagnostikk-attributter** (entry/exit-tid + lydnivå per Away/Night/Stay) | `gateway.exitEntrySettings` (allerede i `/home`) | Lav — data finnes alt |

> Merk: alle data over er fanget fra OWNER-kontoens egen trafikk. Felter kan variere mellom Homely-abonnement (ARC/AMS/independent-living ser ut til å være betalte tillegg).
