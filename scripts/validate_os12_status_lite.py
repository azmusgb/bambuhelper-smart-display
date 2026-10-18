#!/usr/bin/env python3
"""Validate the read-only status token (reconstructed source, need/forbid).

The host smoke test (tests/workshop_os12_status_lite_smoke.cpp) proves the
serializer field rules, bearer parsing, limiter and approval flow. This
validator proves how the device wires them:

* exactly one token route, GET /api/status/lite, registered with plain
  server.on (not SECURE_GET) and no other method;
* management routes only behind SECURE_GET/SECURE_POST;
* the portal policy never reads Authorization, and the lite handler never reads
  the portal session;
* only a SHA-256 digest is stored; comparison is constant-time; nothing token
  related reaches Serial, settings export, diagnostics or the touchscreen;
* no job name, IP, MAC, serial or other identifying field is serialized;
* creation requires the touchscreen Allow tap; factory reset clears the digest.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


class ValidationError(RuntimeError):
    pass


def read(path: Path) -> str:
    if not path.is_file():
        raise ValidationError(f"missing file: {path}")
    return path.read_text(encoding="utf-8")


def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise ValidationError(f"missing {label}: {needle}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise ValidationError(f"forbidden {label}: {needle}")


def block(text: str, signature: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise ValidationError(f"missing function: {signature}")
    brace = text.find("{", start)
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValidationError(f"unterminated function: {signature}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--source-root", default=str(Path(__file__).resolve().parents[1]))
    args = ap.parse_args()
    root = Path(args.repo).resolve()
    source_root = Path(args.source_root).resolve()

    build = read(root / "include/smart_home_build.h")
    web = read(root / "src/web_server.cpp")
    sec = read(root / "src/security_manager.cpp")
    hub = read(root / "src/smart_hub.cpp")
    html = read(root / "include/web_pages.h")
    app_js = read(root / "web/app.js")
    glue = read(root / "src/workshop_status_lite.cpp")
    glue_h = read(root / "include/workshop_status_lite.h")
    core = read(root / "include/workshop_platform/status_lite_core.hpp")
    recipe = read(source_root / "scripts/run_os12_ux_local.sh")

    for installed, source in (
        (core, "firmware/platform/status_lite_core.hpp"),
        (glue, "firmware/platform/status_lite/workshop_status_lite.cpp"),
        (glue_h, "firmware/platform/status_lite/workshop_status_lite.h"),
    ):
        if installed != read(source_root / source):
            raise ValidationError(f"installed copy differs from {source}")

    need(build, "#define WORKSHOP_OS_STATUS_LITE_TOKEN 1", "status token build identity")
    need(build, "#define WORKSHOP_OS_PORTAL_SIGNIN_RESTORED 1", "portal sign-in prerequisite")
    need(recipe, "apply_workshop_os12_status_lite.py", "status token overlay in recipe")

    # Exactly one token route; GET only; not session-wrapped.
    lite_routes = re.findall(r'server\.on\(\s*"/api/status/lite"\s*,\s*(HTTP_[A-Z]+)', web)
    if lite_routes != ["HTTP_GET"]:
        raise ValidationError(f"/api/status/lite must be registered exactly once, GET only: {lite_routes}")
    need(web, 'server.on("/api/status/lite", HTTP_GET, []() { workshopStatusLiteHandleRead(server); });',
         "token-checked lite route")
    forbid(web, 'SECURE_GET("/api/status/lite"', "session-wrapped lite route")
    forbid(web, 'SECURE_POST("/api/status/lite"', "mutating lite route")
    for marker in (
        'SECURE_GET("/api/status-token", handleStatusTokenState);',
        'SECURE_POST("/api/status-token/create", handleStatusTokenCreate);',
        'SECURE_POST("/api/status-token/claim", handleStatusTokenClaim);',
        'SECURE_POST("/api/status-token/revoke", handleStatusTokenRevoke);',
    ):
        need(web, marker, "session-protected token management")
    for path in re.findall(r'server\.on\(\s*"(/api/status-token[^"]*)"', web):
        raise ValidationError(f"token management route registered without session wrapper: {path}")
    need(web, '"Authorization"', "Authorization header collection")
    need(block(web, "static void handleReset()"), "workshopStatusTokenFactoryReset();", "factory reset clears token")

    # The token opens nothing else.
    forbid(sec, "Authorization", "bearer token in portal authorization")
    forbid(sec, "workshopStatusLite", "status token in portal authorization")
    for other in re.findall(r'header\("Authorization"\)', web):
        raise ValidationError("web_server.cpp reads Authorization outside the status lite module")
    read_handler = block(glue, "void workshopStatusLiteHandleRead(WebServer& server)")
    for leak in ("securityAuthorize", "securitySessionValid", "Cookie", "BHSESSION", "X-BambuHelper-Client"):
        forbid(read_handler, leak, "portal session in lite route")
    for ctl in ("dispatch", "PrinterCommand", "publish", "tasmota", "mqtt", "Mqtt"):
        forbid(glue, ctl, "control path in status token module")
    need(read_handler, "if (isAPMode())", "station-only lite route")
    need(read_handler, "g_limiter.admit(client, now)", "per-client rate limit")
    need(read_handler, "Retry-After", "rate-limit Retry-After")
    need(read_handler, "g_limiter.noteFailure(client, now);", "bad-token backoff")
    need(read_handler, "parseBearer(header.c_str(), presented)", "strict Authorization: Bearer parsing")
    need(read_handler, "digestEqual(digest, g_digest)", "constant-time digest comparison")
    need(read_handler, 'server.header("Authorization")', "token read from Authorization header")
    forbid(read_handler, "server.arg(", "token accepted from query or form")
    need(glue, "sendHeader(\"Cache-Control\", \"no-store\")", "no-store responses")

    # Storage: digest only.
    need(glue, 'constexpr char kDigestKey[] = "lite_sha";', "digest key")
    need(glue, "prefs.putBytes(kDigestKey, digest, kDigestBytes)", "digest persisted")
    for put in re.findall(r"prefs\.put\w+\(([^;]+)\);", glue):
        if "digest" not in put:
            raise ValidationError(f"status token module persists something other than the digest: {put}")
    need(block(glue, "bool workshopStatusTokenAllow()"), "storeDigest(digest)", "Allow stores the new digest (revokes old)")
    need(block(glue, "void workshopStatusTokenHandleRevoke(WebServer& server)"), "clearDigest();", "revocation")
    need(core, "diff = static_cast<std::uint8_t>(diff | (a[i] ^ b[i]));", "constant-time compare")

    # Creation needs the touchscreen.
    need(block(glue, "void workshopStatusTokenHandleCreate(WebServer& server)"), "g_flow.start(", "pending approval")
    forbid(block(glue, "void workshopStatusTokenHandleCreate(WebServer& server)"), "encodeToken", "token minted without Allow")
    need(block(glue, "bool workshopStatusTokenAllow()"), "g_flow.promptVisible(now)", "Allow only while the prompt is visible")
    need(hub, "if(hubStatusTokenPromptTouch(x,y))return true;", "touch routed to the consent prompt")
    # The prompt's buttons sit where the tab bar is in landscape. The prompt is
    # modal and draws no tab bar, so its hit test must run before the tab bar's.
    touch = block(hub, "bool smartHubHandleTouch(uint16_t rawX, uint16_t rawY, bool longPress)")
    prompt_at = touch.find("if(hubStatusTokenPromptTouch(x,y))return true;")
    tabs_at = touch.find("hubNavRect(i).contains(x,y)")
    if tabs_at < 0 or prompt_at > tabs_at:
        raise ValidationError("consent prompt touch must be checked before the tab bar")
    forbid(block(hub, "static bool hubStatusTokenPromptDraw(bool force)"), "uiBottomNav(", "tab bar drawn under the modal prompt")
    need(hub, 'hubV1125Action(hubStatusTokenAllowRect(),"Allow"', "Allow button")
    need(hub, "workshopStatusTokenAllow();", "Allow calls the device glue")
    prompt = block(hub, "static bool hubStatusTokenPromptDraw(bool force)")
    forbid(prompt, "token", "token text drawn on the touchscreen")

    # Secrets never reach logs, exports or diagnostics.
    for line in glue.splitlines():
        if "Serial." in line and any(s in line for s in ("token", "digest", "presented", "%s")):
            if "Status token:" not in line or "%s" in line or "token)" in line:
                raise ValidationError(f"token material may reach Serial: {line.strip()}")
    for handler in ("static void handleSettingsExport()", "static void handleDebug()"):
        body = block(web, handler)
        forbid(body, "lite_sha", "token digest in export/diagnostics")
        forbid(body, "StatusToken", "token state in export/diagnostics")

    # Field allowlist: the serializer only knows these keys.
    serializer = block(core, "inline std::size_t serializeStatusLite(")
    keys = set(re.findall(r'\\"([a-zA-Z]+)\\":', serializer))
    allowed = {"schema", "firmware", "version", "sourceCommit", "printers", "slot", "connection", "activity",
               "freshness", "ageSeconds", "progressPercent", "remainingMinutes", "error", "code", "text", "canceled"}
    if keys != allowed:
        raise ValidationError(f"status lite fields differ from the allowlist: extra={sorted(keys - allowed)} "
                              f"missing={sorted(allowed - keys)}")
    summary = core.split("struct PrinterSummary {", 1)[1].split("};", 1)[0]
    for field in ("subtaskName", "name", "localIp", "ip", "mac", "serial", "wifiSignal", "rssi", "ams", "nozzle", "bed"):
        if re.search(r"\b" + field + r"\b", summary):
            raise ValidationError(f"identifying or unrelated field in PrinterSummary: {field}")
    for field in ("subtaskName", "localIp", "config.name", "config.serial", "WiFi.macAddress", "wifiSignal", ".ams"):
        forbid(glue, field, "identifying printer/device field in status token module")

    # Portal UX.
    need(html, 'id="statusTokenTitle">Read-only status access</h3>', "portal panel")
    need(html, "tap Allow on the display", "portal explains the Allow tap")
    need(html, "Copy this token now. It will not be shown again.", "one-time reveal copy")
    need(app_js, "/api/status-token/claim", "one-time claim")
    forbid(app_js, "localStorage.setItem('statusToken", "token persisted in the browser")

    print("PASS: read-only status token is one GET route with its own bearer check, digest-only storage, "
          "touchscreen approval, rate limiting and a fixed field allowlist; it opens no other route")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        raise SystemExit(f"FAIL: {exc}")
