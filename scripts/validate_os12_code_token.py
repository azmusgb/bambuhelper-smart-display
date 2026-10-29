#!/usr/bin/env python3
"""Validate the sign-in code key using the core validation engine."""
from __future__ import annotations
import argparse
import re
from pathlib import Path
from val_core import read, need, forbid, block, ordered, ValidationError

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--source-root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--final", action="store_true", help="finished tree (after the More overhaul)")
    args = ap.parse_args()
    root = Path(args.repo).resolve()
    source_root = Path(args.source_root).resolve()

    build = read(root / "include/smart_home_build.h")
    web = read(root / "src/web_server.cpp")
    sec = read(root / "src/security_manager.cpp")
    sec_h = read(root / "include/security_manager.h")
    hub = read(root / "src/smart_hub.cpp")
    html = read(root / "include/web_pages.h")
    app_js = read(root / "web/app.js")
    glue = read(root / "src/workshop_code_token.cpp")
    glue_h = read(root / "include/workshop_code_token.h")
    core = read(root / "include/workshop_platform/code_token_core.hpp")
    lite_core = read(root / "include/workshop_platform/status_lite_core.hpp")
    lite_glue = read(root / "src/workshop_status_lite.cpp")
    recipe = read(source_root / "scripts/run_os12_ux_local.sh")

    for installed, source in (
        (core, "firmware/platform/code_token_core.hpp"),
        (glue, "firmware/platform/code_token/workshop_code_token.cpp"),
        (glue_h, "firmware/platform/code_token/workshop_code_token.h"),
        (lite_core, "firmware/platform/status_lite_core.hpp"),
    ):
        if installed != read(source_root / source):
            raise ValidationError(f"installed copy differs from {source}")

    need(build, "#define WORKSHOP_OS_CODE_TOKEN 1", "sign-in code key build identity")
    need(build, "#define WORKSHOP_OS_STATUS_LITE_TOKEN 1", "status token prerequisite")
    ordered(recipe, ["apply_workshop_os12_status_lite.py", "apply_workshop_os12_code_token.py",
                     "apply_workshop_os12_more_overhaul.py"], "recipe order")
    need(recipe, '--extra-public-route "HTTP_GET:/api/portal-code"', "public-route review of the code route")

    routes = re.findall(r'server\.on\(\s*"/api/portal-code"\s*,\s*(HTTP_[A-Z]+)', web)
    if routes != ["HTTP_GET"]:
        raise ValidationError(f"/api/portal-code must be registered exactly once, GET only: {routes}")
    need(web, 'server.on("/api/portal-code", HTTP_GET, []() { workshopPortalCodeHandleRead(server); });',
         "key-checked code route")
    for wrapped in re.findall(r'SECURE_\w+\(\s*"/api/portal-code', web):
        raise ValidationError(f"session-wrapped or mutating code route: {wrapped}")
    if web.count("workshopPortalCodeHandleRead") != 1:
        raise ValidationError("the code read handler must be reachable from exactly one route")
    for marker in (
        'SECURE_GET("/api/code-token", handleCodeTokenState);',
        'SECURE_POST("/api/code-token/create", handleCodeTokenCreate);',
        'SECURE_POST("/api/code-token/claim", handleCodeTokenClaim);',
        'SECURE_POST("/api/code-token/revoke", handleCodeTokenRevoke);',
    ):
        need(web, marker, "session-protected key management")
    for path in re.findall(r'server\.on\(\s*"(/api/code-token[^"]*)"', web):
        raise ValidationError(f"key management route registered without session wrapper: {path}")
    need(block(web, "static void handleReset()"), "workshopCodeTokenFactoryReset();", "factory reset clears the key")

    forbid(sec, "Authorization", "bearer key in portal authorization")
    for name in ("workshopCodeToken", "workshopPortalCode", "code_sha", "wsc_"):
        forbid(sec, name, "sign-in code key in portal authorization")
    for _ in re.findall(r'header\("Authorization"\)', web):
        raise ValidationError("web_server.cpp reads Authorization itself")
    
    lite_rest = lite_glue.replace('#if __has_include("workshop_code_token.h")\n#include "workshop_code_token.h"\n', "", 1)
    lite_rest = lite_rest.replace("if (workshopCodeTokenPromptVisible()) {", "", 1)
    if "workshopCodeTokenPromptVisible()" in block(lite_glue, "void workshopStatusLiteHandleRead(WebServer& server)"):
        raise ValidationError("status read route consults the code key module")
    for name in ("CodeToken", "code_sha", "wsc_", "kCodeTokenPrefix"):
        forbid(lite_rest, name, "sign-in code key accepted by the status route")
    need(block(lite_glue, "void workshopStatusLiteHandleRead(WebServer& server)"),
         "parseBearer(header.c_str(), presented)", "status route parses only wsl_ keys")
    need(lite_core, 'constexpr char kTokenPrefix[] = "wsl_";', "status token prefix")
    need(core, 'constexpr char kCodeTokenPrefix[] = "wsc_";', "sign-in code key prefix")
    need(block(core, "inline bool parseCodeBearer("), "statuslite::parseBearer(header, out, kCodeTokenPrefix)",
         "code route parses only wsc_ keys")
    need(block(core, "inline void encodeCodeToken("), "kCodeTokenPrefix", "minted keys carry wsc_")
    need(core, "CodeApprovalFlow() : statuslite::ApprovalFlow(kCodeTokenPrefix) {}", "hand-over only accepts wsc_ keys")

    read_handler = block(glue, "void workshopPortalCodeHandleRead(WebServer& server)")
    for leak in ("securityAuthorize", "securitySessionValid", "Cookie", "BHSESSION", "X-BambuHelper-Client"):
        forbid(read_handler, leak, "portal session in the code route")
    for ctl in ("dispatch", "PrinterCommand", "publish", "tasmota", "mqtt", "Mqtt", "securitySetPortalCodeRequired"):
        forbid(glue, ctl, "control path in the code key module")
    need(read_handler, "if (isAPMode())", "station-only code route")
    ordered(read_handler, [
        "if (isAPMode())",
        "g_limiter.admit(client, now)",
        'server.header("Authorization")',
        "presentedCodeKey(header.c_str(), presented)",
        "digestEqual(digest, g_digest)",
        "if (keyFailureCounts(kind, valid)) g_limiter.noteFailure(client, now);",
        "sendJson(server, 401,",
        "g_limiter.noteSuccess(client, now);",
        "serializePortalCode(securityPortalCode(), bootId(), body, sizeof(body))",
        "sendJson(server, 200, body);",
    ], "code route order (own rate limit, key check, only a wrong wsc_ key counted, answer)")
    failure = read_handler.split("if (!valid) {", 1)[1].split("return;", 1)[0]
    need(failure, "WWW-Authenticate", "401 names the Bearer scheme")
    for shared in ("securityLoginRetryAfter", "securityNoteLoginFailure"):
        forbid(glue, shared, "code route sharing the portal sign-in lock-out")
    need(read_handler, "sendRetry(server, gate.retryAfterSeconds);", "own lock-out answers 429")
    need(block(core, "inline bool keyFailureCounts("), "presented == PresentedKey::WellFormed && !matched",
         "only a well-formed wsc_ key that does not match counts")
    forbid(read_handler, "server.arg(", "key accepted from query or form")
    need(block(glue, "void sendJson(WebServer& server, int code, const char* body)"),
         'server.sendHeader("Cache-Control", "no-store");', "no-store responses")
    need(block(glue, "void sendRetry(WebServer& server, uint32_t seconds)"), "Retry-After", "Retry-After on 429")

    need(glue, 'constexpr char kDigestKey[] = "code_sha";', "own digest key")
    forbid(glue, "lite_sha", "status token digest key reused")
    need(glue, "prefs.putBytes(kDigestKey, digest, kDigestBytes)", "digest persisted")
    for put in re.findall(r"prefs\.put\w+\(([^;]+)\);", glue):
        if "digest" not in put:
            raise ValidationError(f"code key module persists something other than the digest: {put}")
    allow = block(glue, "bool workshopCodeTokenAllow()")
    need(allow, "g_flow.promptVisible(now)", "Allow only while the prompt is visible")
    need(allow, "encodeCodeToken(random, key)", "Allow mints a wsc_ key")
    need(allow, "storeDigest(digest)", "Allow stores the new digest (revokes the old key)")
    create = block(glue, "void workshopCodeTokenHandleCreate(WebServer& server)")
    need(create, "g_flow.start(", "pending approval")
    forbid(create, "encode", "key minted without Allow")
    need(create, "workshopStatusTokenPromptVisible()", "one consent question at a time")
    need(block(glue, "void workshopCodeTokenHandleRevoke(WebServer& server)"), "clearDigest();", "revocation")
    need(block(glue, "void workshopCodeTokenFactoryReset()"), "clearDigest();", "factory reset")
    need(lite_core, "diff = static_cast<std::uint8_t>(diff | (a[i] ^ b[i]));", "constant-time compare")

    for line in glue.splitlines():
        if "Serial." in line and not re.fullmatch(r'\s*(if \(.*\) )?Serial\.println\("Code key: [^"%]*"\);', line):
            raise ValidationError(f"code key module writes something other than a fixed message to Serial: {line.strip()}")
    for name, text in (("web_server.cpp", web), ("security_manager.cpp", sec), ("smart_hub.cpp", hub)):
        for line in text.splitlines():
            if "Serial." in line and ("securityPortalCode" in line or "g_portalCode" in line):
                raise ValidationError(f"sign-in code reaches Serial in {name}: {line.strip()}")
    for handler in ("static void handleSettingsExport()", "static void handleDebug()"):
        body = block(web, handler)
        for leak in ("code_sha", "CodeToken", "securityPortalCode", "portal-code"):
            forbid(body, leak, "sign-in code or key in export/diagnostics")

    serializer = block(core, "inline std::size_t serializePortalCode(")
    keys = set(re.findall(r'\\"([a-zA-Z]+)\\":', serializer))
    if keys != {"code", "bootId"}:
        raise ValidationError(f"/api/portal-code fields differ from code+bootId: {sorted(keys)}")
    need(serializer, "portalCodeWellFormed(code)", "malformed code never served")

    prompt = block(hub, "static bool hubCodeTokenPromptDraw(bool force)")
    need(prompt, '"Allow Local AI to show the sign-in code?"', "prompt question")
    need(prompt, "wsm::dialogCard(s)", "prompt card on the More dialog geometry")
    need(hub, "static HubRect hubCodeTokenCancelRect() { return wsHub(wsm::dialogCancelRect(wsScreen())); }",
         "Cancel on the More dialog geometry")
    need(hub, "static HubRect hubCodeTokenAllowRect() { return wsHub(wsm::dialogConfirmRect(wsScreen())); }",
         "Allow on the More dialog geometry")
    need(prompt, 'hubV1125Action(hubCodeTokenCancelRect(),"Cancel"', "Cancel button")
    need(prompt, 'hubV1125Action(hubCodeTokenAllowRect(),"Allow"', "Allow button")
    for leak in ("uiBottomNav(", "securityPortalCode", "claim", "g_flow"):
        forbid(prompt, leak, "tab bar, code or key drawn on the modal prompt")
    touch_fn = block(hub, "static bool hubCodeTokenPromptTouch(int16_t x,int16_t y)")
    need(touch_fn, "workshopCodeTokenAllow();", "Allow calls the device glue")
    need(touch_fn, "workshopCodeTokenDeny();", "Cancel calls the device glue")
    touch = block(hub, "bool smartHubHandleTouch(uint16_t rawX, uint16_t rawY, bool longPress)")
    ordered(touch, ["if(hubStatusTokenPromptTouch(x,y))return true;", "if(hubCodeTokenPromptTouch(x,y))return true;",
                    "hubNavRect(i).contains(x,y)"], "prompt touch before the tab bar")
    draw = block(hub, "void smartHubDraw(ScreenState screen, bool forceRedraw)")
    ordered(draw, ["hubStatusTokenPromptDraw(effectiveForce)", "hubCodeTokenPromptDraw(effectiveForce)",
                   "case SCREEN_HUB_HOME:"], "prompts own the frame before any page")
    need(block(hub, "void smartHubUpdateHoldProgress(uint16_t rawX, uint16_t rawY, uint32_t holdMs)"),
         "if(workshopCodeTokenPromptVisible())return;", "prompt suppresses hold progress")
    need(block(hub, "void smartHubService()"), "hubCodeTokenPromptService();", "prompt countdown")

    need(html, 'id="codeTokenTitle">Sign-in code access</h3>', "portal panel")
    need(html, 'onclick="createCodeToken()">Create</button>', "Create button")
    need(html, 'onclick="revokeCodeToken()">Revoke</button>', "Revoke button")
    need(html, "Anyone who has this key can read the code and sign in", "portal states the trade-off")
    need(html, "Copy this key now. It will not be shown again.", "one-time reveal copy")
    need(html, '<div id="codeTokenReveal" hidden><label class="os12-feed-token">', "reveal hidden on a plain wrapper")
    status_at, code_at = html.find('id="statusTokenTitle"'), html.find('id="codeTokenTitle"')
    between = html[status_at:code_at]
    if status_at < 0 or code_at < status_at or between.count("<section") != 1:
        raise ValidationError("sign-in code panel must sit directly after the status token panel")
    need(app_js, "/api/code-token/claim", "one-time claim")
    forbid(app_js, "localStorage.setItem('codeToken", "key persisted in the browser")
    forbid(app_js, "/api/portal-code", "portal page reading the code with the key")

    if args.final:
        layout = read(root / "include/workshop_more_layout.hpp")
        need(layout, '{RowId::PortalCodeKey, RowKind::Info, "Local AI code access", PageId::Root},',
             "Local Portal row")
        view = hub.split("case R::PortalCodeKey: {", 1)
        if len(view) != 2:
            raise ValidationError("Local Portal code key row has no view")
        row = view[1].split("break;", 1)[0]
        need(row, "workshopCodeTokenConfigured()", "row shows whether the key is set up")
        forbid(row, "securityPortalCode", "row shows the code")
        need(block(hub, "static bool wsVideoDirect()"), "!workshopCodeTokenPromptVisible()",
             "video frames never draw over the prompt")
        need(block(hub, "static void wsVideoGuard(ScreenState screen)"), "workshopCodeTokenPromptVisible()",
             "video test stops for the prompt")

    print("PASS: sign-in code key validated via core engine" + (" (finished tree)" if args.final else ""))
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        raise SystemExit(f"FAIL: {exc}")
