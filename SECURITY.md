# Security Policy

Workshop OS is local-first firmware that can observe and issue commands to physical printers and mapped smart plugs. Security reports are treated as hardware-control issues, not ordinary UI bugs.

## Supported lines

| Surface | Status | Security handling |
| --- | --- | --- |
| Workshop OS v11.22 accepted source | Supported | Current physically accepted source baseline. |
| Workshop OS v11.23 Network Locale Layout RC2 | Hardware candidate | Touch-UX candidate with an explicitly temporary trusted-LAN portal-code bypass; physical acceptance still required. |
| Workshop OS v11.20 Portal Auth RC1 | Preserved security baseline | Auth/session/AP-boundary implementation remains in the deterministic reconstruction stack and is validated before the RC2 bypass delta is applied. |
| Static installer v11.19.1 | Supported for the published download channel | Conservative published installer. |
| Static rollback v7.2 | Recovery-only | Immediate static-channel rollback. |
| Historical RCs / archived manifests | Unsupported | Kept for provenance only. |

## Temporary trusted-LAN policy in v11.23 RC2

The user-requested RC2 development policy temporarily removes the **normal Wi-Fi portal-code challenge** to reduce friction while the WS350 touch interface is being iterated on real hardware.

This is not implemented by deleting the security subsystem. The RC2 delta is intentionally centralized and reversible:

- `SECURE_GET` / `SECURE_POST` route wrappers remain intact;
- `securitySessionValid()` accepts normal station-mode requests without a cookie only when `WORKSHOP_OS_TEMP_LAN_OPEN` is enabled;
- `securityAuthorize()` still enforces same-origin protection for every mutating normal-LAN request;
- ordinary AP mode does **not** become a blanket authorization bypass;
- first-boot/fallback AP exposure remains limited to the existing onboarding essentials;
- deliberate Recovery Safe Mode retains its scoped independent recovery exceptions;
- the boot-scoped portal session implementation remains present and is still validated as the inherited v11.20 baseline before RC2 is applied;
- the browser must visibly disclose **TEMPORARY TRUSTED-LAN MODE**;
- this bypass must be removed or explicitly re-approved before a security-hardened production promotion.

Because normal-LAN authentication is temporarily bypassed, **any device on the same trusted network that can reach the display may be able to access management surfaces**. Same-origin browser protections reduce cross-site mutation risk but are not a substitute for authentication. RC2 should therefore remain on a trusted/private LAN while this mode is enabled.

## Report privately when possible

Do **not** publish working credentials, device access codes, Wi-Fi passphrases, printer serials, private IP inventories, API tokens, exploit payloads, or other sensitive reproduction data in a public issue.

Use GitHub's private vulnerability reporting / Security Advisory flow if it is enabled for this repository. If a private reporting option is not available, open a minimal public issue stating that you have a security concern and need a private contact path; do not include exploit details or secrets.

## High-priority security classes

Please treat these as security-sensitive even when they look like functional bugs:

- unexpected authentication/session bypass outside the explicitly documented RC2 normal-LAN exception;
- an AP/setup/recovery mode that unintentionally grants broader admin authority;
- unauthorized printer control or smart-plug power control;
- command replay after disconnect/reconnect;
- a destructive command that bypasses state validation or confirmation;
- exposure of Wi-Fi credentials, printer access codes, portal codes, tokens, backups, or settings secrets;
- unsafe OTA/recovery behavior or rollback bypass;
- credential-bearing screenshots, framebuffer bundles, diagnostics, logs, process arguments, or configuration exports;
- cross-printer command routing or incorrect printer-to-plug mapping;
- memory corruption reachable through network/touch input;
- supply-chain changes that alter the pinned upstream or build inputs without review.

## Authenticated-source expectations

When the temporary RC2 bypass is not enabled, the authenticated Workshop OS policy remains:

- normal LAN management routes require the boot-scoped portal-code session;
- mutating requests retain same-origin protection in addition to authentication;
- logout and reboot invalidate prior portal sessions;
- the rotating portal code may be shown on the physical System screen for the owner but must not be printed to Serial/log output;
- normal-LAN Recovery access is authenticated;
- **AP mode is not itself an authorization credential**;
- ordinary first-boot/fallback AP access is limited to captive Wi-Fi onboarding essentials unless the owner establishes a portal-code session;
- independent unauthenticated rescue access exists only in deliberate Recovery Safe Mode and is scoped to dedicated recovery/status/actions plus application OTA/factory-reset;
- printer control, mapped printer power, settings export, debug, and unrelated privileged surfaces must not become anonymously accessible merely because the device entered AP mode.

The pinned upstream setup/fallback AP currently uses a known default Wi-Fi password. That is an onboarding transport control, **not** a substitute for Workshop OS authorization. Changes that reintroduce blanket `isAPMode()` authorization are security regressions.

## Control-safety expectations

Security changes must preserve the fail-closed control model documented in `docs/CONTROL_SAFETY.md`:

- commands are revalidated at execution time;
- stale/offline commands are discarded rather than delayed;
- destructive actions remain guarded;
- printer/plug identity is resolved explicitly;
- speculative command payloads are not introduced without a proven backend contract.

## Sensitive test data and captures

Use synthetic values in fixtures, docs, screenshots and bug reports. Never commit a real household SSID/password, printer access code, device portal code, cloud token, private key, or personally identifying device inventory.

The supported `scripts/capture-ws350-views.zsh` workflow must remain credential-safe even while RC2 is LAN-open:

- RC2 should first attempt the no-login trusted-LAN capture path;
- authenticated fallback, when needed on older builds, must not echo or expose the portal code in process arguments;
- cookie/login/raw-frame temporary files use restrictive permissions and are removed on normal exit and interruption;
- raw framebuffer bytes are kept only in a private temporary file outside the retained capture directory;
- the live System credential region remains redacted **before** retained PPM or PNG output is written;
- printer configuration/settings exports remain excluded because those models can contain access codes or other secrets;
- Release Gate must fail if these capture-safety invariants are weakened.

If a secret is committed accidentally, deleting it in a later commit is not sufficient. Rotate/revoke the credential first, then remove it from the active repository and evaluate whether history rewriting is warranted.
