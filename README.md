# Xiaomi S400 for Home Assistant

Custom integration for the **Xiaomi Body Composition Scale S400** (MJTZC01YM). It shows your **live weight** while you stand on the scale, and records every weigh-in for the right person, with the **body composition the scale works out itself**.

It talks to the scale over a logged-in Bluetooth connection instead of only listening to its broadcasts, so it works with a local Bluetooth adapter or an **ESPHome Bluetooth proxy**.

> ⚠️ **Experimental.** The protocol is reverse-engineered and has only been tested on scale firmware `2.1.1_0006`. A firmware update may break it.

## Features

- **Two modes**: *live* (weight on screen while you stand on the scale) or *after weigh-in* (the scale's own full evaluation, including heart rate). See [Modes](#modes).
- **Live weight** while you stand on the scale (about every 0.3 s), plus *On scale* and *Stable* sensors for automations (live mode).
- **One device per person.** Each weigh-in goes to the person whose scale profile it was, with no mixing between people.
- **Body composition from the scale itself** (after-weigh-in mode): fat, muscle, water, protein, bone, visceral fat, BMR, metabolic age, body type, body score and fat mass. These are the values the Xiaomi app shows.
- **Missed weigh-ins are backfilled.** The scale keeps its weigh-ins in memory, so ones taken while Home Assistant was offline or out of range are picked up later.
- **Heart rate** (after-weigh-in mode, needs the BLE key).
- **No command line needed.** Log in with the Xiaomi Home app by scanning a QR code during setup, and the scale's keys are fetched automatically.
- **Link people to Home Assistant users**, so automations know whom to notify.
- An event on every weigh-in, for automations.
- English and Polish translations.

| | built-in `xiaomi_ble` | this integration |
|---|---|---|
| Live weight while standing | no | yes |
| Per-person entities | needs extra integrations and templates | built in |
| Body composition | weight and impedance only | the scale's own values (after-weigh-in mode) or a formula estimate (live mode) |
| Weigh-ins while HA was offline | lost | backfilled from the scale's memory |
| Heart rate | yes | yes, in after-weigh-in mode with the BLE key |
| Keys needed | BLE key | login token, plus the BLE key for heart rate |

## Requirements

1. **Home Assistant 2025.7** or newer.
2. The scale added to the **Xiaomi Home** app, with at least one weigh-in done there.
3. A Bluetooth adapter in range of the scale, or an **ESP32 running an ESPHome Bluetooth proxy in active mode**:
   ```yaml
   esp32:
     board: esp32dev
     framework:
       type: esp-idf
   esp32_ble_tracker:
     scan_parameters:
       active: true
   bluetooth_proxy:
     active: true
   ```
   Active mode is required because the integration opens a connection to the scale. It keeps one of the proxy's connection slots (usually 3) busy most of the time.

## Installation

### HACS

1. HACS → ⋮ → **Custom repositories**. Add `https://github.com/snelstim/ha-xiaomi-s400` with type **Integration**.
2. Install **Xiaomi S400** and restart Home Assistant.

### Manual

Copy `custom_components/xiaomi_s400` into your Home Assistant `config/custom_components/` folder and restart.

## Setup

1. **Settings → Devices & services → Add integration → Xiaomi S400**, or accept the discovered scale.
2. Pick the scale, or enter its Bluetooth MAC address.
3. Choose how to provide the scale's keys:
   - **Log in with Xiaomi Home (QR code)** (recommended): open the Xiaomi Home app, tap its scan icon, scan the code Home Assistant shows and approve the login. Use the account the scale is added to. The integration searches the Xiaomi server regions for your scale by MAC address, fetches its **token** and **BLE key**, and fills in the form for you. It only reads from your account; nothing is changed.
   - **Enter keys manually**: paste the 24-character **token**, and optionally the 32-character **BLE key**, from [Xiaomi-cloud-tokens-extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor). The scale is listed there as `yunmai.scales.ms104`.
4. On the integration page, choose **Add person** for each user:
   - **Home Assistant person** (optional): fills in the name and links the scale profile to that person.
   - **Name**: leave it empty to use the linked person's name.
   - **Scale profile ID**: see below.
   - **Sex**, **date of birth** and **height**: used for BMI and the fallback body composition estimate.

## Modes

The scale only stores its own evaluation of a weigh-in (body composition, body score) and only broadcasts the heart rate when **no app is connected** while you weigh in. A connected client receives just weight and impedance. So the integration has two modes. Change it from the integration's **Configure** button:

| | **Live** (default) | **After weigh-in** |
|---|---|---|
| Live weight while standing | ✅ | only with a BLE key, from the broadcast |
| Result appears | as soon as the weight is stable | about 12 s after the scale finishes |
| Body composition | formula estimate from weight, impedance and profile | **the scale's own values**, the same as the Xiaomi app |
| Body score, fat mass | ❌ | ✅ |
| Heart rate | ❌ in practice | ✅ (needs the BLE key) |
| Bluetooth connection slot | busy all the time | a few seconds per weigh-in |

**After weigh-in** mode stays disconnected. It watches the scale's broadcasts, and when their frame counter changes (someone is weighing in), it connects about 12 s after the last change, reads the stored weigh-in and disconnects again.

The Xiaomi Home app on a phone nearby can sync and delete the stored weigh-in first. If that happens, the weigh-in is lost to Home Assistant in this mode. Keep the phone's Bluetooth off, or the app closed, while weighing, and open the app afterwards; it still gets the weigh-in, because Home Assistant never deletes it.

### Finding your profile ID

Weigh yourself alone, then read the **Profile ID** sensor on the scale device. That number is your profile on the scale.

### When the token changes

The token changes when the scale is reset or removed and re-added in Xiaomi Home. Home Assistant then asks you to re-authenticate, where you can log in by QR code again or paste the new token. You can also refresh the keys at any time from the integration's ⋮ menu → **Reconfigure**.

## Entities

**Scale device**

| Entity | Notes |
|---|---|
| Live weight | updates while you stand on the scale |
| On scale, Stable | binary sensors |
| Weight, Impedance, Impedance low, Heart rate, Profile ID, Last measurement | the last weigh-in from anyone |
| Connected, Last error | diagnostic |
| Raw final frame | diagnostic, disabled by default |

**One device per person**

Weight, impedance, impedance low, heart rate, BMI, body fat, water, protein, muscle mass, bone mass, visceral fat, basal metabolism, metabolic age, ideal weight, body type, body score, fat mass and last measurement.

These update **only** when that person's profile is measured, and keep their values across restarts. Body score and fat mass come only from the scale's stored weigh-ins.

## Event

`xiaomi_s400_measurement` fires once per weigh-in. It includes:

| Field | Meaning |
|---|---|
| `person`, `person_entity` | the configured person and their linked `person.*` entity, if any |
| `profile_id`, `weight`, `impedance`, `impedance_low`, `heart_rate`, `measured_at` | the measurement |
| `bmi`, `fat_percent`, `muscle_mass_kg`, `water_percent`, … | body composition |
| `source` | `scale` when the values came from the scale's stored weigh-in |
| `stored` | `true` for a weigh-in backfilled from the scale's memory |

The event waits for the scale's stored weigh-in, and for the heart rate when a BLE key is set, but never longer than 20 s.

Example: notify the right person.

```yaml
triggers:
  - trigger: event
    event_type: xiaomi_s400_measurement
    event_data:
      person_entity: person.tim
actions:
  - action: notify.mobile_app_tims_phone
    data:
      message: "{{ trigger.event.data.weight }} kg, {{ trigger.event.data.fat_percent }} % fat"
```

## How it works

This describes live mode; after-weigh-in mode is described [above](#modes).

1. Whenever the scale is reachable, the integration connects and logs in: a random key exchange, keys derived from the token, and an HMAC check that both sides hold the same token.
2. It **keeps the connection open**, because the scale only streams weight to a client that is already logged in when someone steps on. If the scale drops an idle link, the integration reconnects within a few seconds.
3. It decrypts the scale's `live` frames (weight, stable flag) and its `final` frame (profile, weight, timestamp, two impedances).
4. About 8 s after the final frame, and at every login, it asks the scale for the weigh-ins it has stored. A weigh-in received live is normally *not* stored (the scale counts it as delivered), so live mode keeps the formula estimate. But weigh-ins taken while Home Assistant was disconnected are backfilled from there, with the scale's own body composition. The integration never acknowledges the records, so the scale keeps them and the Xiaomi app still syncs them.
5. It then disconnects for 15 s, so the scale can send its heart-rate broadcast (decrypted with the BLE key).

If reading the stored weigh-ins fails, you still get the weigh-in, with body composition estimated from weight, impedance and the person's profile using formulas ported from the Mi Fit app. Neither the scale's values nor the estimate are medical-grade.

## Troubleshooting

Enable debug logging:

```yaml
logger:
  logs:
    custom_components.xiaomi_s400: debug
```

The log shows every frame sent and received. Lines to look for after a weigh-in:

| Log line | Meaning |
|---|---|
| `Stored records: expected=… parsed=…` | the scale's stored weigh-ins were read; `expected=0` in live mode is normal for a weigh-in seen live (see [Modes](#modes)), and in after-weigh-in mode usually means the Xiaomi app synced it first |
| `Adv …: counter X -> Y` | a broadcast with a new frame; in after-weigh-in mode this schedules the read |
| `expected RCV_RDY on 0x1A` or `Reading stored weigh-ins … failed` | the stored-records request isn't accepted by your firmware; the formula estimate is used instead |
| `Xiaomi cloud login failed` / `not in this Xiaomi account` | QR login problem; check you used the account the scale is in, or enter the keys manually |
| `rejected the login token` | the token changed; re-authenticate |

Please attach a debug log when reporting issues.

**Known gaps**

- Only the S400 (`yunmai.scales.ms104`) on firmware `2.1.1_0006` has been tested.
- After-weigh-in mode follows the method described in the community thread; it is new here and not yet confirmed across firmware versions.
- The body-type names for the scale's own body-type values are assumed to follow the Mi Fit order. This is unverified.
- The QR login is the only in-app login. Xiaomi's password login can require captchas and email codes, so use the extractor if QR login isn't possible.

## Credits

This is a fork of [nanocortex/ha-xiaomi-s400-live](https://github.com/nanocortex/ha-xiaomi-s400-live). It adds stored weigh-ins with the scale's own body composition, QR-code login, Home Assistant person linking and a typed date-of-birth field, and renames the integration to `xiaomi_s400`.

- Live protocol and decoders: [nokistin/xiaomi-s400-live](https://github.com/nokistin/xiaomi-s400-live) (Apache-2.0), vendored and adapted in `custom_components/xiaomi_s400/s400/`
- Mi Home v2 login: [dnandha/miauth](https://github.com/dnandha/miauth) (Apache-2.0)
- Stored weigh-in protocol and field map: a [Home Assistant community thread](https://community.home-assistant.io/t/how-to-add-xiaomi-mijia-scale-s400-model-mjtzc01ym-into-home-assisstant/662778)
- Xiaomi cloud QR login: [PiotrMachowski/Xiaomi-cloud-tokens-extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor) (MIT), ported to async in `cloud.py`
- Fallback body composition formulas: [mnm-matin/miscale](https://github.com/mnm-matin/miscale) (MIT)

Not affiliated with Xiaomi. License: Apache-2.0.
