# Security Policy

Workshop OS is local-first firmware that can observe and issue commands to physical printers and mapped smart plugs. Security reports are treated as hardware-control issues, not ordinary UI bugs.

## Supported lines

| Surface | Status | Security handling |
| --- | --- | --- |
| Workshop OS v11.19.1 accepted source | Supported | Current accepted source baseline. |
| Workshop OS v11.20 Portal Auth RC1 | Active security candidate | Portal/session hardening is validated here and still requires physical WS350 acceptance before promotion. |
| Static installer v7.2 | Supported for the published download channel | Security-relevant installer/recovery defects should be assessed independently from source-line fixes. |
| Static rollback v7.1 | Recovery-only | Retained only as the immediate rollback image. |
| Historical RCs / archived manifests | Unsupported | Kept for provenance only. |

## Report privately when possible

Do **not** publish working credentials, device access codes, Wi-Fi passphrases, printer serials, private IP inventories, API tokens, exploit payloads, or other sensitive reproduction data in a public issue.

Use GitHub's private vulnerability reporting / Security Advisory flow if it is enabled for this repository. If a private reporting option is not available, open a minimal public issue stating that you have a security concern and need a private contact path; do not include exploit details or secrets.

## High-priority security classes

Please treat these as security-sensitive even when they look like functional bugs:

- authentication or session bypass in the local portal;
- unauthorized printer control or smart-plug power control;
- command replay after disconnect/reconnect;
- a destructive command that bypasses state validation or confirmation;
- exposure of Wi-Fi credentials, Bambu access codes, portal codes, tokens, backups, or settings secrets;
- unsafe OTA/recovery behavior or rollback bypass;
- unauthenticated framebuffer/capture endpoints;
- credential-bearing screenshots, framebuffer bundles, diagnostics, logs, process arguments, or configuration exports;
- cross-printer command routing or incorrect printer-to-plug mapping;
- memory corruption reachable through network/touch input;
- supply-chain changes that alter the pinned upstream or build inputs without review.

## Portal/session expectations

For an authenticated Workshop OS source line:

- normal LAN management routes require the boot-scoped portal-code session;
- mutating requests retain same-origin protection in addition to authentication;
- logout and reboot invalidate prior portal sessions;
- the rotating portal code is intentionally shown on the physical System screen for the owner but must not be printed to Serial/log output;
- normal-LAN Recovery access is authenticated while Recovery AP remains independently usable as a rescue path;
- the portal credential must not be embedded in command-line arguments, shared captures, diagnostics, or support artifacts.

## Control-safety expectations

Security fixes must preserve the fail-closed control model documented in `docs/CONTROL_SAFETY.md`:

- commands are revalidated at execution time;
- stale/offline commands are discarded rather than delayed;
- destructive actions remain guarded;
- printer/plug identity is resolved explicitly;
- speculative command payloads are not introduced without a proven backend contract.

## Sensitive test data and captures

Use synthetic values in fixtures, docs, screenshots and bug reports. Never commit a real household SSID/password, printer access code, device portal code, cloud token, private key, or personally identifying device inventory.

The supported `scripts/capture-ws350-views.zsh` workflow must remain credential-safe: portal-code input is not echoed or passed in process arguments, the retained System framebuffer has the live code region redacted in both PPM and PNG form, and printer configuration/settings exports are excluded because those models can contain access codes or other secrets.

If a secret is committed accidentally, deleting it in a later commit is not sufficient. Rotate/revoke the credential first, then remove it from the active repository and evaluate whether history rewriting is warranted.
