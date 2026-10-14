# Device compatibility

These mappings were developed using the listed devices. They are not a guarantee
that another device with the same brand or category uses the same DPs.

| Device | LAN protocol | Implemented controls | Important limitations |
|---|---|---|---|
| Elgin Eco Inverter III HJFC12C2WGCG | 3.5 | Temperature, power, operating mode, fan, Sleep, Display and Eco where the profile/schema permits | Temperature and fan target `mid` were physically validated; other choices have separate experimental gates. Swing, ionizer and Fungusproof are not implemented. |
| Outsmart RGBIC LED | 3.3 | Power, HSV fixed color, brightness, saved favorite colors | No scene editor or RGBIC preset activation. The Scenes tab was removed in 2.3.1. |
| NovaDigital smart switch | 3.4 | Two independent Boolean channels | Channel 1 was the touch output; channel 2 was the socket on the tested plate. Other variants need verification. |

## DP mapping

| Role | DP | Meaning | Representation |
|---|---:|---|---|
| Elgin | 1 | Power | Boolean |
| Elgin | 2 | Setpoint | Integer, scale 1: wire 240 means 24 Celsius; current whole-degree controls 16–32 |
| Elgin | 3 | Ambient temperature | Read only, scale 1 |
| Elgin | 4 | Operating mode | Confirmed own-device enum; no guessed values |
| Elgin | 5 | Fan | OEM-observed enum, separate evidence required |
| Elgin | 8 / 13 / 102 | Eco / display / sleep | Schema-supported Boolean controls with opt-in guards |
| LED | 20 | Power | Boolean |
| LED | 21 | Lighting mode | Fixed-color transition is used by color selection |
| LED | 24 | Fixed color | 12 hexadecimal characters: H/S/V uint16, H 0–360, S/V 0–1000 |
| LED | 26 / 46 / 47 / 53 | Timer and strip configuration | Not edited by the lighting controls |
| Switch | 1 / 2 | Touch output / socket | Boolean |

Brightness updates the V component of DP24; the application does not assume DP22
or DP23 exists. Favorite colors are stored locally and applied through the same
fixed-color path. A device reporting `scene` or `music` gets an informational
preview-unavailable message, not simulated colors or a false effect selector.

The public RGBIC codec is an offline research utility, not device compatibility or
a usable scene catalog. Nothing in the UI sends DP51 scene payloads.

## Extending compatibility

Use the schema of your exact device, an authenticated status read and explicit
physical validation before declaring a mapping usable. Do not copy another user's
Device ID, Local_Key, profile validation flags or network address. The synthetic
fixtures exist for tests and documentation, not for provisioning real devices.
