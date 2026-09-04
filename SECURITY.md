# Security Policy

Workshop OS is local-first firmware that can observe and issue commands to physical printers and mapped smart plugs. Security reports are treated as hardware-control issues, not ordinary UI bugs.

## Supported lines

| Surface | Status | Security handling |
| --- | --- | --- |
| Workshop OS v11.19.1 accepted source | Supported | Current source/security fixes target this line first. |
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
- cross-printer command routing or incorrect printer-to-plug mapping;
- memory corruption reachable through network/touch input;
- supply-chain changes that alter the pinned upstream or build inputs without review.

## Control-safety expectations

Security fixes must preserve the fail-closed control model documented in `docs/CONTROL_SAFETY.md`:

- commands are revalidated at execution time;
- stale/offline commands are discarded rather than delayed;
- destructive actions remain guarded;
- printer/plug identity is resolved explicitly;
- speculative command payloads are not introduced without a proven backend contract.

## Sensitive test data

Use synthetic values in fixtures, docs, screenshots and bug reports. Never commit a real household SSID/password, printer access code, device portal code, cloud token, private key, or personally identifying device inventory.

If a secret is committed accidentally, deleting it in a later commit is not sufficient. Rotate/revoke the credential first, then remove it from the active repository and evaluate whether history rewriting is warranted.
