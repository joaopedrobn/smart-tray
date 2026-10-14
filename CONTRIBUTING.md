# Contributing to Smart Tray

Smart Tray 2.3.1 is a Windows desktop application. Contributions should preserve
its asynchronous LAN communication, explicit user actions and credential protection.

## Development setup

Use Windows 11 x64, Python 3.14, Git and a local virtual environment. Follow
[Getting started](README.en.md#getting-started). Install `requirements.txt` for the
application and tests, and `requirements-build.txt` for packaging. Node is optional:
one offline MiniApp helper test is skipped when Node is unavailable.

Run `python -m pytest -q` and `python -m compileall -q src scripts` before submitting.
Tests use synthetic fixtures in `tests/fixtures/config`; they must never require
your home devices, Cloud account or Local_Keys. Screenshots are reproducible with
`python scripts/capture_docs.py`, using mocked device states and isolated settings.

## Where code belongs

| Area | Location |
|---|---|
| QML pages and visual components | `src/smart_tray/qml/` |
| Device adapters | `adapters.py`, `interactive_adapters.py`, `beta.py` |
| Async controller and command policy | `controller.py`, `beta_controller.py`, `direct_controller.py` |
| QML bridge and window | `quick_bridge.py`, `quick_panel.py` |
| Credential protection | `security.py` |
| Windows integration | `windows.py`, `window_placement.py`, `desktop_state.py` |
| Packaging and developer utilities | `scripts/` |

Historical names such as `beta.py` remain to avoid disruptive module renames; the
application version is stable 2.3.1. Investigation utilities are source tools,
not features in the production interface.

## Adding a device adapter

1. Supply a sanitized schema and synthetic profile. Explain its source and license.
2. Check Device ID/profile identity, protocol and types before any operation.
3. Expose only verified DP mappings. A similar product is not sufficient evidence.
4. Keep credentials in `CredentialStore`; do not add keys to JSON or examples.
5. Run communication outside the GUI thread, with bounded timeouts.
6. Read before and after a write, write one intent at a time, and never retry an
   uncertain write automatically.
7. Cover offline, unknown state, invalid values and mismatched profiles with mocks.
8. Separate schema-supported, observed and physically validated capabilities.

Do not use real device actions in CI. Manual hardware validation belongs in a
separately reviewed, explicitly approved procedure.

## Issues and pull requests

Use [Issues](https://github.com/joaopedrobn/smart-tray/issues) for reproducible bugs
and proposals. Include the version, Windows/Python versions, steps, expected result
and sanitized evidence. Never attach provisioned data, tokens, `.dpapi`, raw Cloud
responses or a whole local diagnostics folder.

Fork the repository, create a focused branch, add relevant tests and open a pull
request against `main`. Describe behavior and validation, including limitations.
Check [SECURITY.md](SECURITY.md) before reporting a security problem publicly.
