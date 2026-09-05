# v11.23 RC2 security hardening

The mergeable v11.23 candidate preserves the accepted v11.20 portal/session boundary.

The early RC2 touch delta historically introduced a temporary station-mode trusted-LAN bypass for hardware iteration. That state is now treated only as an intermediate reconstruction condition and is explicitly removed before settings parity, JavaScript validation, native builds, artifact packaging, or promotion.

Final v11.23 candidate requirements:

- normal station-mode management requires the boot-scoped portal-code session;
- mutating requests also require the existing same-origin check;
- AP/setup/recovery authorization remains route-scoped;
- `WORKSHOP_OS_TEMP_LAN_OPEN` must be absent from final reconstructed source;
- `if (!isAPMode()) return true;` must be absent from final security policy;
- the browser must not display a trusted-LAN bypass banner;
- framebuffer capture uses an authenticated cookie established through `/login`;
- capture credentials are entered without echo and sent to curl over stdin;
- the obsolete no-code physical-acceptance helper is not tracked or packaged;
- the native WS350 and shared-display builds run only after the authenticated boundary has been restored and validated.

This document records the boundary explicitly so a development-only authentication relaxation cannot become a production promotion by accident.
