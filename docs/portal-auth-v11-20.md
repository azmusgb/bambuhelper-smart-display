# Workshop OS v11.20 Portal Auth RC1

## Purpose

Restore normal WS350 portal-code/session authentication now that the accepted v11.19.1 physical UI/recovery baseline is proven, while keeping Recovery AP and touch safety independent from the browser login path.

## Security delta

- removes `SMART_HOME_DEV_UNLOCK` from the reconstructed WS350 build;
- removes the development authorization short-circuit from `security_manager.cpp`;
- requires the boot-scoped portal-code cookie for normal LAN routes;
- protects the Recovery page itself on normal LAN, not only its mutations;
- does not print the rotating portal credential to Serial/log output;
- retains same-origin checks for mutating browser requests;
- retains Recovery AP authorization bypass through `isAPMode()`;
- retains forced-safe WS350 touchscreen behavior;
- removes development-unlocked browser/recovery copy;
- keeps the current rotating portal code visible only where intentionally needed on the physical System screen.

## CI acceptance

- [ ] v11.19.1 accepted baseline reconstructs cleanly.
- [ ] v11.19.1 physical-fit/render contracts remain green before auth delta.
- [ ] v11.20 auth patch applies exactly once.
- [ ] `SMART_HOME_DEV_UNLOCK` is absent from the candidate build.
- [ ] development auth bypass code/copy is absent.
- [ ] portal credential is absent from Serial logging calls.
- [ ] login GET/POST routes remain present.
- [ ] normal root/status/control/capture routes remain secured.
- [ ] normal-LAN `/recovery` uses the secure GET wrapper.
- [ ] same-origin protection remains present for mutations.
- [ ] Recovery AP bypass and recovery mutation guard remain present.
- [ ] WS350 physical portal-code card remains present.
- [ ] forced-safe FT6336 touch contract remains present.
- [ ] browser JavaScript parses.
- [ ] native `ws_lcd_350` build passes.
- [ ] shared `jc3248w535` regression build passes.
- [ ] Full-image merge and OTA packaging pass.

## Physical acceptance on WS350

Use only the exact CI artifact for this candidate.

1. **Before OTA**
   - photograph/record current v11.19.1 System screen and portal access;
   - confirm printer settings, Wi-Fi, touch, Recovery and current known-good slot are healthy.
2. **OTA candidate**
   - install the v11.20 application/OTA image, not Full.bin;
   - verify device returns to Home and printer configuration persists.
3. **Login gate**
   - open the device LAN URL in a fresh/private browser session;
   - verify redirect to the custom `/login` page;
   - verify no browser-native HTTP-auth dialog appears;
   - enter a wrong code and confirm rejection;
   - enter the current code shown under **System → Portal Access** and confirm login.
4. **Session behavior**
   - navigate Home/Printer/Workshop/Tools/System browser surfaces after login;
   - verify Light and other authenticated controls remain callable;
   - use Logout and confirm access is gated again;
   - log in again, reboot the device, and confirm the old session no longer grants access and the displayed code changes.
5. **Credential/log handling**
   - inspect normal boot serial output and verify the portal code itself is not printed;
   - verify the physical System screen still shows the current code for the owner;
   - do not include the displayed code in shared screenshots, diagnostics or support artifacts.
6. **Mutation protection**
   - verify normal browser saves/controls work after login;
   - verify an unauthenticated control request fails rather than executing;
   - verify Same-Origin protection remains active for mutating requests.
7. **Recovery independence**
   - while on normal LAN and signed out, request `/recovery` and verify it redirects to `/login` rather than exposing the recovery page;
   - sign in and verify `/recovery` renders independently of the normal portal JavaScript;
   - on normal LAN, verify recovery mutations require the authenticated portal session;
   - enter Recovery Safe Mode/AP and verify `/recovery` remains directly accessible without the normal LAN session;
   - verify Recovery Safe Mode/AP still permits recovery actions without the normal LAN session;
   - verify Force Touchscreen, reset UI, reboot and rollback paths remain available as designed.
8. **OTA/recovery regression**
   - perform one authenticated manual OTA/reinstall or subsequent candidate update path;
   - verify Safari-compatible hashing/upload behavior and reboot return;
   - confirm known-good/rollback metadata remains healthy.
9. **Physical UI regression**
   - verify touch remains responsive after cold boot and OTA reboot;
   - verify the System portal-code card fits and is readable;
   - verify no v11.19.1 rendered-fit regression on the accepted 22-view set.

## Promotion gate

Do not merge/promote v11.20 solely because CI is green. Physical login, credential/log handling, reboot/session invalidation, normal-LAN Recovery gating, OTA and Recovery AP behavior must be demonstrated on the actual WS350 first.
