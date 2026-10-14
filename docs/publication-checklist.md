# Publication gate for v2.3.1

Prepared on 2026-10-13 for `https://github.com/joaopedrobn/smart-tray`, branch `main`.
No push or release upload is authorized by completion of this checklist alone.

## Source snapshot

- English README with three real QML screenshots, clearly labeled synthetic states.
- Setup, architecture, compatibility, security, contributions and licensing docs.
- MIT project license; third-party notices and dependency inventory retained.
- Private configurations, captures, ciphertext, builds and cache paths ignored.
- Private IDs replaced by synthetic values or configuration-derived identity checks.
- Independent synthetic fixtures; examples do not claim authenticated control.
- Private configuration root, safe key import and empty startup supported.
- Windows CI runs mocked tests and compile checks, without secrets or build uploads.

Validation: **472 tests passed** in the development environment and an isolated copy
of the staged public tree. Imports compiled and dependency check passed. Public
frozen mock validation passed **19 interactions**, with no QML warnings or real
writes. Empty-configuration startup produced only unavailable device states.

## Security findings and limitations

The audit checked project files including ignored files, the staged snapshot and
Git blob history against local private identifiers and known Local_Keys without
printing values. **No known plaintext Local_Key was found in project files or Git
blobs.** This does not prove that arbitrary unknown secrets could never exist.

The current public snapshot had no matches for known private identifiers or absolute
user paths. Existing history contains **25 older blobs with private identifier data**.
Those commits must not be pushed. Earlier commit author metadata also used a
personal email; the preparation commit uses a public GitHub noreply identity.

Private local history and metadata were backed up outside the repository first.
No history rewrite, force push or remote replacement was performed. Origin matches
the requested URL; remote inspection returned no branch refs during preparation.

## Proposed clean history

After explicit owner approval, create an initial public commit from this audited
snapshot on local `main`, preserving the private backup. Audit that new root and
all reachable commits again. Recheck the remote; review any branch that has appeared.
A clean initial push to an empty remote does not require force push. Ask for final
push authorization before sending.

Until approved, the preparation commit is reviewable locally but its ancestry is
**unsafe to publish**. Do not push tags exposing private ancestors either.

## Binary release

The configuration-free public build is under `dist/public/SmartTray`; it does not
replace the personal app. No release is created. Qt's QML collection can include
unused GPL-only addons, including Quick 3D: complete the exact bundled module license
review before uploading binaries. Previous personal ZIPs must not be uploaded.
See [redistribution](redistribution.md).

Images and README references were locally validated. GitHub rendering and Actions
cannot be asserted until an approved push happens.
