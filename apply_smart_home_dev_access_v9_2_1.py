#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


class PatchError(RuntimeError):
    pass


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly 1 match, found {count}")
    return text.replace(old, new, 1)


def patch_security(repo: Path) -> None:
    p = repo / "src" / "security_manager.cpp"
    text = p.read_text(encoding="utf-8")

    text = replace_once(
        text,
        'constexpr char kCookieName[] = "BHSESSION";\n',
        'constexpr char kCookieName[] = "BHSESSION";\n'
        '// DEVELOPMENT SAFETY MODE: keep the local portal open until the WS350\n'
        '// touchscreen/navigation/recovery experience is fully buttoned up.\n'
        '// Authentication machinery stays compiled so it can be re-enabled with\n'
        '// a one-line policy change after physical acceptance.\n'
        'constexpr bool kPortalAuthEnabled = false;\n',
        "portal auth policy",
    )

    old_init = '''void ensureInitialized() {
  if (g_initialized) return;
  generatePortalCode();
  ensureSessionToken();
  g_initialized = true;

  Serial.println();
  Serial.println("Smart Home v8.3 RC3 portal session security enabled");
  Serial.printf("Portal code: %s\\n", g_portalCode);
  Serial.println("The code changes after every reboot and is shown on the System screen.");
}
'''
    new_init = '''void ensureInitialized() {
  if (g_initialized) return;
  if (kPortalAuthEnabled) {
    generatePortalCode();
    ensureSessionToken();
  } else {
    strlcpy(g_portalCode, "OFF", sizeof(g_portalCode));
  }
  g_initialized = true;

  Serial.println();
  if (kPortalAuthEnabled) {
    Serial.println("Smart Home portal session security enabled");
    Serial.printf("Portal code: %s\\n", g_portalCode);
  } else {
    Serial.println("Smart Home development access: portal authentication OFF");
    Serial.println("Local portal remains open until physical UI/recovery acceptance is complete.");
  }
}
'''
    text = replace_once(text, old_init, new_init, "security initialization")

    old_session = '''bool securitySessionValid(WebServer& server) {
  if (isAPMode()) return true;
  ensureInitialized();
  return cookieMatches(server);
}
'''
    new_session = '''bool securitySessionValid(WebServer& server) {
  ensureInitialized();
  if (!kPortalAuthEnabled) return true;
  if (isAPMode()) return true;
  return cookieMatches(server);
}
'''
    text = replace_once(text, old_session, new_session, "session bypass")

    old_login = '''bool securityLogin(WebServer& server, const String& submittedCode) {
  ensureInitialized();

  String code = submittedCode;
  code.trim();
  code.toUpperCase();
  if (!constantTimeEqual(code.c_str(), g_portalCode)) return false;

  issueSessionCookie(server);
  return true;
}
'''
    new_login = '''bool securityLogin(WebServer& server, const String& submittedCode) {
  ensureInitialized();
  if (!kPortalAuthEnabled) return true;

  String code = submittedCode;
  code.trim();
  code.toUpperCase();
  if (!constantTimeEqual(code.c_str(), g_portalCode)) return false;

  issueSessionCookie(server);
  return true;
}
'''
    text = replace_once(text, old_login, new_login, "login bypass")

    old_auth = '''bool securityAuthorize(WebServer& server, bool mutating) {
  if (isAPMode()) return true;
  ensureInitialized();

  if (!cookieMatches(server)) {
    server.sendHeader("Cache-Control", "no-store");
    if (server.method() == HTTP_GET) {
      // No WWW-Authenticate header: Safari must never show a native repeating
      // credential dialog. Interactive requests land on our stable login page.
      server.sendHeader("Location", "/login");
      server.send(303, "text/plain", "Sign in required");
    } else {
      server.send(401, "application/json",
          "{\\"status\\":\\"error\\",\\"message\\":\\"Portal session expired. Reload and sign in again.\\"}");
    }
    return false;
  }

  if (mutating && !sameOrigin(server)) {
    server.send(403, "application/json",
        "{\\"status\\":\\"error\\",\\"message\\":\\"Rejected by Smart Home same-origin protection.\\"}");
    return false;
  }

  return true;
}
'''
    new_auth = '''bool securityAuthorize(WebServer& server, bool mutating) {
  if (isAPMode()) return true;
  ensureInitialized();

  // During development the portal deliberately has no login gate. Keep the
  // same-origin mutation guard, though, so another web page cannot silently
  // change settings or start an OTA merely because it can reach the LAN IP.
  if (!kPortalAuthEnabled) {
    if (mutating && !sameOrigin(server)) {
      server.send(403, "application/json",
          "{\\"status\\":\\"error\\",\\"message\\":\\"Rejected by Smart Home same-origin protection.\\"}");
      return false;
    }
    return true;
  }

  if (!cookieMatches(server)) {
    server.sendHeader("Cache-Control", "no-store");
    if (server.method() == HTTP_GET) {
      server.sendHeader("Location", "/login");
      server.send(303, "text/plain", "Sign in required");
    } else {
      server.send(401, "application/json",
          "{\\"status\\":\\"error\\",\\"message\\":\\"Portal session expired. Reload and sign in again.\\"}");
    }
    return false;
  }

  if (mutating && !sameOrigin(server)) {
    server.send(403, "application/json",
        "{\\"status\\":\\"error\\",\\"message\\":\\"Rejected by Smart Home same-origin protection.\\"}");
    return false;
  }

  return true;
}
'''
    text = replace_once(text, old_auth, new_auth, "authorization policy")

    p.write_text(text, encoding="utf-8")


def patch_touch_policy(repo: Path) -> None:
    p = repo / "src" / "settings.cpp"
    text = p.read_text(encoding="utf-8")
    anchor = '''#if defined(USE_CST816) || defined(USE_CST328) || defined(USE_XPT2046) || defined(USE_FT5X06) || defined(USE_FT6336) || defined(USE_AXS_TOUCH) || defined(TOUCH_CS)
  buttonType = (ButtonType)prefs.getUChar("btn_type", BTN_TOUCHSCREEN);
#else
  buttonType = (ButtonType)prefs.getUChar("btn_type", BTN_DISABLED);
#endif
  buttonPin = prefs.getUChar("btn_pin", BUTTON_DEFAULT_PIN);
'''
    replacement = '''#if defined(USE_CST816) || defined(USE_CST328) || defined(USE_XPT2046) || defined(USE_FT5X06) || defined(USE_FT6336) || defined(USE_AXS_TOUCH) || defined(TOUCH_CS)
  buttonType = (ButtonType)prefs.getUChar("btn_type", BTN_TOUCHSCREEN);
#else
  buttonType = (ButtonType)prefs.getUChar("btn_type", BTN_DISABLED);
#endif
#if defined(BOARD_IS_WS350)
  // Development safety rail: the WS350 is physically a touchscreen appliance.
  // Ignore any stale NVS value that disabled touch in an older build. A portal
  // setting must never be able to strand this device while the UI is evolving.
  buttonType = BTN_TOUCHSCREEN;
#endif
  buttonPin = prefs.getUChar("btn_pin", BUTTON_DEFAULT_PIN);
'''
    text = replace_once(text, anchor, replacement, "WS350 touchscreen safety rail")
    p.write_text(text, encoding="utf-8")


def patch_hub(repo: Path) -> None:
    p = repo / "src" / "smart_hub.cpp"
    text = p.read_text(encoding="utf-8")

    old_card = '''  // Portal code card - deliberately large and unambiguous.
  uiCard(8, 143, W - 16, 72, UI_PURPLE, false);
  uiShield(29, 178, UI_PURPLE);
  setFont(tft, FONT_SMALL);
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(UI_DIM, UI_PANEL);
  tft.drawString("PORTAL CODE", 52, 153);
  setFont(tft, FONT_LARGE);
  tft.setTextColor(UI_PURPLE, UI_PANEL);
  tft.drawString(securityPortalCode(), 52, 174);
  setFont(tft, FONT_SMALL);
  tft.setTextColor(UI_GREEN, UI_PANEL);
  tft.drawString("RAM session • rotates on reboot", 52, 198);
'''
    new_card = '''  // Development access card. No portal code is required until the physical
  // navigation/recovery experience passes acceptance without lockout paths.
  uiCard(8, 143, W - 16, 72, UI_GREEN, false);
  uiShield(29, 178, UI_GREEN);
  setFont(tft, FONT_SMALL);
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(UI_DIM, UI_PANEL);
  tft.drawString("PORTAL ACCESS", 52, 153);
  setFont(tft, FONT_LARGE);
  tft.setTextColor(UI_GREEN, UI_PANEL);
  tft.drawString("OPEN", 52, 174);
  setFont(tft, FONT_SMALL);
  tft.setTextColor(UI_AMBER, UI_PANEL);
  tft.drawString("Development mode • code disabled", 52, 198);
'''
    text = replace_once(text, old_card, new_card, "open portal system card")
    text = text.replace('drawHeader("HOME", "v9.2", 0);', 'drawHeader("HOME", "v9.2.1", 0);')
    text = text.replace('drawHeader("SYSTEM", "v9.2", 3);', 'drawHeader("SYSTEM", "v9.2.1", 3);')
    p.write_text(text, encoding="utf-8")


def patch_app(repo: Path) -> None:
    p = repo / "web" / "app.js"
    text = p.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "    pill.textContent = 'Smart Home v9.2';\n",
        "    pill.textContent = 'Smart Home v9.2.1 • OPEN';\n",
        "portal build pill",
    )
    p.write_text(text, encoding="utf-8")


def patch_build(repo: Path) -> None:
    p = repo / "include" / "smart_home_build.h"
    text = p.read_text(encoding="utf-8")
    text = replace_once(text, '#define SMART_HOME_VERSION "v9.2"\n',
                        '#define SMART_HOME_VERSION "v9.2.1"\n', "version")
    text = replace_once(text, '#define SMART_HOME_PROFILE "smart-printer-control-plane"\n',
                        '#define SMART_HOME_PROFILE "open-development-control-plane"\n', "profile")
    text = replace_once(text, '#define SMART_HOME_BUILD_LABEL "Smart Home v9.2 Smart Printer RC1"\n',
                        '#define SMART_HOME_BUILD_LABEL "Smart Home v9.2.1 Open Portal RC1"\n', "build label")
    p.write_text(text, encoding="utf-8")


def apply(repo: Path) -> None:
    patch_security(repo)
    patch_touch_policy(repo)
    patch_hub(repo)
    patch_app(repo)
    patch_build(repo)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    if not args.apply:
        print("Smart Home v9.2.1 development-access patch ready. Use --apply.")
        return 0
    apply(repo)
    print("Smart Home v9.2.1 open-portal development mode applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
