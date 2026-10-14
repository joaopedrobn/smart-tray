# Setting up your own devices

## Terms

**Tuya** supplies a device platform used by many brands. **Smart Life** is one app
for Tuya-powered devices; brand apps can have a separate account ecosystem.
**LAN** means the local network between this Windows PC and your device.
The **Device ID** identifies a device. The **Local_Key** authenticates LAN traffic;
it is a secret, unlike a public product/model name. Treat IDs and MAC addresses as
private too, and keep both out of issues and pull requests.

## Start without any devices

```powershell
.\.venv\Scripts\pythonw.exe scripts/run_app.py --config-root .\private-config
```

The directory may be empty. Cards remain unconfigured/unavailable and controls
disabled. The application does not connect to example devices or simulate real
states. There is no integrated onboarding wizard in 2.3.1.

## Prepare private configuration

Copy the example tree into an ignored directory:

```powershell
Copy-Item -Recurse examples\config private-config
```

Edit `private-config/diagnostics/provisioned.json` and each role profile with
identifiers from **your own** app. Replace example addresses with verified private
IPv4 addresses. The example addresses are documentation-only and must not be used
to contact devices. Keep the same Device ID in the registry and corresponding
profile. Each role supports one device in this version.

The optional discovery file must match the same ID; it must not associate an IP
based on a guess. Confirm the address in the router's DHCP table and match the MAC
shown by the app. Devices behind a gateway might not expose direct Tuya TCP LAN.

If you need protocol discovery, the source helper supports an explicit local
address/subnet and bounded discovery. Run `python scripts/discover.py --help` to
see its exact arguments. Discovery does not prove that a matching key authenticates.
Direct adapters were developed for protocols 3.3, 3.4 and 3.5; do not guess the
version simply from a brand name.

## Obtain and protect your Local_Key

Use a manufacturer-authorized method. If the existing Cloud provisioner is used:

1. Log in to the [Tuya Developer Platform](https://platform.tuya.com/) in your browser.
2. Create/select your Cloud project in the data center corresponding to your app
   account. Check the services required for read-only device access and existing
   subscription validity. Do not subscribe to paid plans automatically.
3. Link your own app account using the official QR flow under the project's device
   account linkage. Confirm that your exact devices are visible.
4. Enter Access ID/Secret only in the local provisioning dialogs. If your brand
   app cannot be linked, its authorization is a separate problem; do not re-pair
   the device merely to obtain a key.

The source provisioner reads the devices you registered, requests their metadata
and keys, then stores keys in current-user DPAPI. It does not use the default
TinyTuya wizard or export plaintext keys:

```powershell
.\.venv\Scripts\pythonw.exe scripts/provision.py --config-root .\private-config --role led
```

If you already have an authorized Local_Key, import it through masked local fields:

```powershell
.\.venv\Scripts\pythonw.exe scripts/provision.py --manual --config-root .\private-config --role led
```

Substitute `elgin` or `novadigital` for the role. Never place a key in a command
argument, example JSON, chat, screenshot, Git commit or Cloud response attachment.
The secret stays outside the configuration tree in
`%LOCALAPPDATA%\SmartTray\credentials`, encrypted by DPAPI.

## Read state before enabling control

```powershell
.\.venv\Scripts\python.exe scripts/read_local.py --config-root .\private-config --role led
```

This is a state query only. Output reports counts; local files contain private
identifiers and sanitized state. Do not upload them. An authenticated read is not
physical validation of every control. Example profiles intentionally have empty
`confirmed_commands` and do not claim authenticated or physically verified controls.

## Profiles and schemas are an advanced setup step

The current application requires evidence-bound profiles: protocol authentication,
schema, units/ranges and confirmed command mappings. Read
[compatibility](compatibility.md) and inspect the adapter checks before adding a
mapping. For Elgin additional controls, the private schema must identify the own
device; fan evidence is distinct from ordinary standardized DP metadata.

There is no automatic process that validates another product's DPs. Do not copy
the test fixtures' `physical_confirmed` flags into a real profile. They are simulated
evidence for tests. Control stays disabled until the required evidence is supplied.
Hardware validation must be intentional, one function at a time, with an exact
payload and the owner's approval. Do not probe unknown DPs by writing.

Legacy device-specific research scripts remain for study and need explicit
adaptation to a new device; their example identifiers are not automatic targets.

## Public executable

The public build contains no configured devices. Run it with a private root:

```powershell
.\dist\public\SmartTray\SmartTray.exe --config-root .\private-config
```

Keep `_internal` beside the executable. DPAPI ciphertext from another Windows
user/machine is not portable; provision your own key under the current user.
The startup option registers the executable in HKCU and preserves an explicit
private configuration root. Automatic multi-profile onboarding is not implemented.
