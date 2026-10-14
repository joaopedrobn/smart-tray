# Security policy

## Reporting a vulnerability

Do not publish credentials or sensitive device information in an issue. Use
[GitHub private vulnerability reporting](https://github.com/joaopedrobn/smart-tray/security/advisories/new)
if the repository owner has enabled it. If unavailable, open an issue containing
only a request for a private reporting channel, without exploit data or secrets.
No dedicated security mailbox or response deadline is currently promised.

## What is protected

Local_Keys are encrypted with Windows DPAPI for the current Windows user, outside
the repository. The app does not embed them in its executable. API credentials
entered in the provisioning form remain transient; no password belongs in JSON.
Source research tools are not a universal device setup wizard.

DPAPI does not protect against malicious code already running as the same Windows
user. It also does not make ciphertext safe to publish. Never commit `.dpapi`,
access keys, Cloud tokens, cookies, session exports, private identifiers or dumps.

## Safe operation

- Keep the app and devices on a trusted local network; do not forward Tuya ports.
- Device mapping is explicit and specific. Unknown DPs must not be probed by writing.
- Workers use timeouts. Writes are user initiated and are not retried automatically.
- An uncertain result must be treated as unknown, not as a successful physical action.
- Do not run unreviewed plugins or tools with access to your credential store.
- Review every file and the Git history before publishing. `.gitignore` does not
  remove values already present in a commit.

If a real key or token has been exposed, revoke/rotate it using the issuer's
authorized procedures. Do not reset a device or change its pairing casually.

## Public artifacts

Public builds must use an empty device configuration. Private profiles, configured
portable builds and prior local ZIPs must not be uploaded as release assets. See
[redistribution](docs/redistribution.md) for dependency and Qt license requirements.
