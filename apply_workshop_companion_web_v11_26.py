#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARKER = "Workshop OS v11.26 Companion Web RC1"


class PatchError(RuntimeError):
    pass


def load(root: Path, rel: str) -> str:
    path = root / rel
    if not path.exists():
        raise PatchError(f"missing reconstructed source: {rel}")
    return path.read_text(encoding="utf-8")


def save(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def companion_html() -> str:
    path = HERE / "assets" / "v11_26_companion_web.html"
    if not path.exists():
        raise PatchError("missing assets/v11_26_companion_web.html")
    value = path.read_text(encoding="utf-8")
    if ')COMPANION"' in value:
        raise PatchError("companion HTML collides with C++ raw-string delimiter")
    return value


HEADER = r'''#pragma once

#include <Arduino.h>

void registerCompanionWebRoutes();
bool companionWebPhoneConnected();
uint32_t companionWebLastSeenMs();
'''


def source(html: str) -> str:
    return r'''#include "companion_web.h"

#include "security_manager.h"
#include <WebServer.h>

extern WebServer server;

namespace {
constexpr uint32_t kPhoneOnlineMs = 15000;
uint32_t g_lastPhoneSeenMs = 0;
uint8_t g_lastPhoneSlot = 0;

const char kCompanionHtml[] PROGMEM = R"COMPANION(''' + html + r''')COMPANION";

const char kCompanionManifest[] PROGMEM = R"JSON({
  "name":"Workshop Companion",
  "short_name":"Workshop",
  "start_url":"/companion",
  "scope":"/",
  "display":"standalone",
  "background_color":"#0d1117",
  "theme_color":"#0d1117"
})JSON";

void redirectToCompanionLogin() {
  server.sendHeader("Cache-Control", "no-store");
  server.sendHeader("Location", "/login?next=/companion");
  server.send(303, "text/plain", "Sign in required");
}

void handleCompanionPage() {
  if (!securitySessionValid(server)) {
    redirectToCompanionLogin();
    return;
  }
  server.sendHeader("Cache-Control", "no-store");
  server.send_P(200, "text/html; charset=utf-8", kCompanionHtml);
}

void handleCompanionManifest() {
  if (!securityAuthorize(server, false)) return;
  server.sendHeader("Cache-Control", "no-cache");
  server.send_P(200, "application/manifest+json", kCompanionManifest);
}

void handleCompanionHeartbeat() {
  if (!securityAuthorize(server, true)) return;
  if (server.hasArg("slot")) {
    int value = server.arg("slot").toInt();
    if (value >= 0 && value < 4) g_lastPhoneSlot = static_cast<uint8_t>(value);
  }
  g_lastPhoneSeenMs = millis();
  String json = String("{\"status\":\"ok\",\"transport\":\"wifi-web\",\"slot\":") +
      String(g_lastPhoneSlot) + "}";
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", json);
}

void handleCompanionConnection() {
  if (!securityAuthorize(server, false)) return;
  const bool connected = companionWebPhoneConnected();
  String json = String("{\"connected\":") + (connected ? "true" : "false") +
      ",\"transport\":\"wifi-web\",\"slot\":" + String(g_lastPhoneSlot) +
      ",\"ageMs\":" + String(g_lastPhoneSeenMs ? millis() - g_lastPhoneSeenMs : 0) + "}";
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", json);
}
}  // namespace

void registerCompanionWebRoutes() {
  server.on("/companion", HTTP_GET, handleCompanionPage);
  server.on("/companion/manifest.webmanifest", HTTP_GET, handleCompanionManifest);
  server.on("/companion/heartbeat", HTTP_POST, handleCompanionHeartbeat);
  server.on("/companion/connection", HTTP_GET, handleCompanionConnection);
}

bool companionWebPhoneConnected() {
  return g_lastPhoneSeenMs != 0 && static_cast<uint32_t>(millis() - g_lastPhoneSeenMs) < kPhoneOnlineMs;
}

uint32_t companionWebLastSeenMs() {
  return g_lastPhoneSeenMs;
}
'''


def patch_build(root: Path) -> None:
    rel = "include/smart_home_build.h"
    text = load(root, rel)
    if MARKER in text:
        return
    text = replace_once(text, '#define SMART_HOME_VERSION "v11.25"', '#define SMART_HOME_VERSION "v11.26"', "version")
    text = replace_once(text, '#define SMART_HOME_PROFILE "workshop-companion"', '#define SMART_HOME_PROFILE "companion-web"', "profile")
    text = replace_once(
        text,
        "Smart Home v11.25 Workshop Companion BLE RC1",
        "Smart Home v11.26 Companion Web RC1",
        "build label",
    )
    text += f"\n// {MARKER}\n"
    save(root, rel, text)


def patch_web_server(root: Path) -> None:
    rel = "src/web_server.cpp"
    text = load(root, rel)
    if '#include "companion_web.h"' not in text:
        text = replace_once(
            text,
            '#include "web_server.h"\n',
            '#include "web_server.h"\n#include "companion_web.h"\n',
            "companion web include",
        )

    route_anchor = '  SECURE_POST("/logout", handlePortalLogout);\n'
    if "registerCompanionWebRoutes();" not in text:
        text = replace_once(
            text,
            route_anchor,
            route_anchor + "  registerCompanionWebRoutes();\n",
            "companion route registration",
        )

    # Preserve the requested destination only for our fixed local Companion path;
    # never accept an arbitrary redirect target from the browser.
    form_anchor = '''  html += F("<form method='post' action='/login'><label for='code'>Portal code</label>"\n'''
    form_replacement = '''  html += F("<form method='post' action='/login'>");\n  if (server.hasArg("next") && server.arg("next") == "/companion")\n    html += F("<input type='hidden' name='next' value='/companion'>");\n  html += F("<label for='code'>Portal code</label>"\n'''
    if "name='next' value='/companion'" not in text:
        text = replace_once(text, form_anchor, form_replacement, "companion login continuation field")

    page_anchor = '''static void handlePortalLoginPage() {\n  if (securitySessionValid(server)) {\n    server.sendHeader("Location", "/");\n    server.send(303, "text/plain", "Already signed in");\n    return;\n  }\n  sendPortalLoginPage(false);\n}\n'''
    page_replacement = '''static void handlePortalLoginPage() {\n  if (securitySessionValid(server)) {\n    const String next = (server.hasArg("next") && server.arg("next") == "/companion") ? "/companion" : "/";\n    server.sendHeader("Location", next);\n    server.send(303, "text/plain", "Already signed in");\n    return;\n  }\n  sendPortalLoginPage(false);\n}\n'''
    if "const String next = (server.hasArg(\"next\")" not in text:
        text = replace_once(text, page_anchor, page_replacement, "companion authenticated login continuation")

    submit_anchor = '''static void handlePortalLoginSubmit() {\n  if (!server.hasArg("code") || !securityLogin(server, server.arg("code"))) {\n    sendPortalLoginPage(true);\n    return;\n  }\n  server.sendHeader("Location", "/");\n  server.send(303, "text/plain", "Signed in");\n}\n'''
    submit_replacement = '''static void handlePortalLoginSubmit() {\n  if (!server.hasArg("code") || !securityLogin(server, server.arg("code"))) {\n    sendPortalLoginPage(true);\n    return;\n  }\n  const String next = (server.hasArg("next") && server.arg("next") == "/companion") ? "/companion" : "/";\n  server.sendHeader("Location", next);\n  server.send(303, "text/plain", "Signed in");\n}\n'''
    if "const String next = (server.hasArg(\"next\")" not in text[text.find("static void handlePortalLoginSubmit"):]:
        text = replace_once(text, submit_anchor, submit_replacement, "companion post-login continuation")

    save(root, rel, text)


def patch_ble_presence(root: Path) -> None:
    rel = "src/workshop_companion_ble.cpp"
    text = load(root, rel)
    if '#include "companion_web.h"' not in text:
        text = replace_once(
            text,
            '#include "workshop_companion_ble.h"\n',
            '#include "workshop_companion_ble.h"\n#include "companion_web.h"\n',
            "BLE web-presence include",
        )
    old = '  out += g_phoneConnected ? "true" : "false";\n'
    new = '  out += (g_phoneConnected || companionWebPhoneConnected()) ? "true" : "false";\n'
    if new not in text:
        text = replace_once(text, old, new, "unified phone-presence state")
    save(root, rel, text)


def apply(root: Path) -> None:
    if not root.exists():
        raise PatchError(f"repository path not found: {root}")
    build = load(root, "include/smart_home_build.h")
    if MARKER in build:
        print(f"{MARKER} already applied")
        return
    if 'SMART_HOME_VERSION "v11.25"' not in build:
        raise PatchError("v11.25 Workshop Companion BLE base is required")

    html = companion_html()
    save(root, "src/companion_web.h", HEADER)
    save(root, "src/companion_web.cpp", source(html))
    patch_web_server(root)
    patch_ble_presence(root)
    patch_build(root)

    checks = {
        "src/companion_web.cpp": [
            'server.on("/companion", HTTP_GET',
            'server.on("/companion/heartbeat", HTTP_POST',
            'securitySessionValid(server)',
            'securityAuthorize(server, true)',
            '/login?next=/companion',
            'kPhoneOnlineMs = 15000',
            'wifi-web',
            '/printer/control',
            '/light/set',
            '/printer/power/status',
            '/printer/power',
        ],
        "src/web_server.cpp": [
            '#include "companion_web.h"',
            'registerCompanionWebRoutes();',
            "name='next' value='/companion'",
            'server.arg("next") == "/companion"',
        ],
        "src/workshop_companion_ble.cpp": [
            '#include "companion_web.h"',
            'g_phoneConnected || companionWebPhoneConnected()',
        ],
        "include/smart_home_build.h": [
            'SMART_HOME_VERSION "v11.26"',
            'SMART_HOME_PROFILE "companion-web"',
            'Smart Home v11.26 Companion Web RC1',
            MARKER,
        ],
    }
    for rel, needles in checks.items():
        body = load(root, rel)
        for needle in needles:
            if needle not in body:
                raise PatchError(f"{rel}: missing {needle}")

    print(f"{MARKER} applied")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to mutate without --apply")
    apply(Path(args.repo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
