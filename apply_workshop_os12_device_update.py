#!/usr/bin/env python3
"""Install the Workshop OS 12 device-native GitHub OTA service into UI13.

This is intentionally applied after the portal-auth hardening slice. It makes
UpdateService the sole device-initiated online-update authority on WS350 while
preserving the manual local OTA upload as a maintenance fallback and keeping
Full/0x0 recovery outside the normal OTA path.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


class PatchError(RuntimeError):
    pass


def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def copy_exact(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise PatchError(f"missing source asset: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def insert_after_once(text: str, anchor: str, addition: str, label: str) -> str:
    if addition.strip() in text:
        return text
    count = text.count(anchor)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(anchor, anchor + addition, 1)


def block_end(text: str, start: int) -> int:
    brace = text.find("{", start)
    if brace < 0:
        raise PatchError("opening brace missing")
    depth = 0
    string: str | None = None
    escape = False
    line_comment = False
    block_comment = False
    i = brace
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""
        if line_comment:
            if c == "\n":
                line_comment = False
        elif block_comment:
            if c == "*" and n == "/":
                block_comment = False
                i += 1
        elif string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == string:
                string = None
        elif c == "/" and n == "/":
            line_comment = True
            i += 1
        elif c == "/" and n == "*":
            block_comment = True
            i += 1
        elif c in ('"', "'"):
            string = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise PatchError("unterminated braced block")


def replace_block(text: str, signature: str, replacement: str, label: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise PatchError(f"{label}: signature missing: {signature}")
    if text.find(signature, start + 1) >= 0:
        raise PatchError(f"{label}: signature not unique: {signature}")
    return text[:start] + replacement.rstrip() + text[block_end(text, start):]


def patch_service(repo: Path, source_root: Path) -> None:
    source_dir = source_root / "firmware" / "platform" / "update"
    copy_exact(source_dir / "workshop_update_service.h", repo / "include" / "workshop_update_service.h")
    copy_exact(source_dir / "workshop_update_service.cpp", repo / "src" / "workshop_update_service.cpp")

    cpp = repo / "src" / "workshop_update_service.cpp"
    text = load(cpp)

    old_guard = '''bool printerUpdateGuardSatisfied(char* reason, std::size_t reasonLen) {
    const workshop::platform::WorkshopState& state = workshopPlatformState();
    for (std::size_t slot = 0; slot < workshop::platform::kMaxPrinterSlots; ++slot) {
        const auto& printer = state.printers[slot];
        if (!printer.configured) continue;
        if (workshop::platform::printerActivityIsActive(printer.activity)) {
            copyText(reason, reasonLen, "Finish or stop the active print before updating Workshop OS.");
            return false;
        }
    }
    return true;
}'''
    new_guard = '''bool printerUpdateGuardSatisfied(char* reason, std::size_t reasonLen) {
    const workshop::platform::WorkshopState& state = workshopPlatformState();
    for (std::size_t slot = 0; slot < workshop::platform::kMaxPrinterSlots; ++slot) {
        const auto& printer = state.printers[slot];
        if (!printer.configured) continue;
        if (printer.telemetryFreshness != Freshness::Fresh ||
            printer.activity == PrinterActivity::Unknown) {
            copyText(reason, reasonLen, "Printer state is stale or unknown. Reconnect and verify the printer is idle before updating.");
            return false;
        }
        if (workshop::platform::printerActivityIsActive(printer.activity)) {
            copyText(reason, reasonLen, "Finish or stop the active print before updating Workshop OS.");
            return false;
        }
    }
    return true;
}'''
    text = replace_once(text, old_guard, new_guard, "fail-closed printer update guard")

    old_publish = '''void publishRuntimeToPlatform(const WorkshopUpdateRuntimeSnapshot& snap) {
    UpdateState state;
    state.channel = snap.channel;
    state.phase = snap.phase;
    state.manifestFreshness = snap.manifestFreshness;
    copyText(state.runningVersion, sizeof(state.runningVersion), snap.runningVersion);
    copyText(state.availableVersion, sizeof(state.availableVersion), snap.availableVersion);
    state.otaSupported = kOtaSupported;
    state.recoveryFullImageSupported = false;
    state.artifactIdentityVerified = snap.artifactIdentityVerified;
    state.rollbackAvailable = false;
    workshopPlatformPublishUpdateState(state);
}'''
    new_publish = '''void publishRuntimeToPlatform(const WorkshopUpdateRuntimeSnapshot& snap) {
    UpdateState state;
    state.channel = snap.channel;
    state.phase = snap.phase;
    state.manifestFreshness = snap.manifestFreshness;
    copyText(state.runningVersion, sizeof(state.runningVersion), snap.runningVersion);
    copyText(state.availableVersion, sizeof(state.availableVersion), snap.availableVersion);
    copyText(state.availableLabel, sizeof(state.availableLabel), snap.availableLabel);
    copyText(state.statusMessage, sizeof(state.statusMessage), snap.statusMessage);
    copyText(state.sourceCommit, sizeof(state.sourceCommit), snap.sourceCommit);
    copyText(state.artifactSha256, sizeof(state.artifactSha256), snap.artifactSha256);
    state.artifactSize = snap.artifactSize;
    state.progressPercent = snap.progressPercent;
    state.otaSupported = kOtaSupported;
    state.busy = snap.busy;
    state.updateAvailable = snap.updateAvailable;
    state.recoveryFullImageSupported = false;
    state.artifactIdentityVerified = snap.artifactIdentityVerified;
    state.rollbackAvailable = false;
    workshopPlatformPublishUpdateState(state);
}'''
    text = replace_once(text, old_publish, new_publish, "normalized update-state publication")

    text = text.replace(
        '''    if (!parseVersionCore(version, (std::uint32_t[3]){0, 0, 0})) {
        // C++ does not permit retaining the temporary array beyond this call;
        // this branch exists only to keep the validation expression explicit.
    }

''',
        "",
        1,
    )
    text = text.replace("signed manifest size", "authoritative manifest size")
    if "signed manifest" in text.lower():
        raise PatchError("update service must not describe the HTTPS manifest as cryptographically signed")

    required = (
        "raw.githubusercontent.com/azmusgb/bambuhelper-smart-display/main/releases/device-update.json",
        'constexpr char kBoard[] = "ws_lcd_350";',
        "setCACertBundle(rootca_crt_bundle_start)",
        "HTTPC_DISABLE_FOLLOW_REDIRECTS",
        "safeArtifactPath",
        "esp_ota_get_next_update_partition",
        "esp_ota_write",
        "mbedtls_sha256_update_ret",
        "std::memcmp(actualSha, expectedSha",
        "esp_ota_set_boot_partition",
        "printer.telemetryFreshness != Freshness::Fresh",
        "state.progressPercent = snap.progressPercent",
        "state.updateAvailable = snap.updateAvailable",
    )
    for needle in required:
        if needle not in text:
            raise PatchError(f"required UpdateService marker missing: {needle}")
    cpp.write_text(text, encoding="utf-8")


def patch_ws350_build(repo: Path) -> None:
    board = repo / "boards" / "ws_lcd_350.ini"
    text = load(board)
    old = '''    ; Smart Home v8: upstream device-initiated OTA is disabled on WS350.
    ; Updates use the externally verified Smart Home release + manual OTA path.
'''
    new = '''    ; Workshop OS 12 re-enables the TLS OTA plumbing on WS350, but retires
    ; the legacy URL-driven /ota/auto route. Device-native online updates are
    ; bound to the authoritative Workshop OS manifest, board, size and SHA-256.
    -D ENABLE_OTA_AUTO=1
'''
    text = replace_once(text, old, new, "WS350 OS12 TLS update plumbing")
    board.write_text(text, encoding="utf-8")


def patch_main(repo: Path) -> None:
    path = repo / "src" / "main.cpp"
    text = load(path)
    text = insert_after_once(
        text,
        '#include "workshop_platform_bridge.h"\n',
        '#include "workshop_update_service.h"\n',
        "UpdateService include",
    )
    text = insert_after_once(
        text,
        "    workshopPlatformBegin();\n",
        "    workshopUpdateServiceBegin();\n",
        "UpdateService begin",
    )
    text = insert_after_once(
        text,
        "  workshopPlatformPoll();\n",
        "  workshopUpdateServiceLoop();\n",
        "UpdateService loop",
    )
    path.write_text(text, encoding="utf-8")


def patch_web_server(repo: Path) -> None:
    path = repo / "src" / "web_server.cpp"
    text = load(path)
    if '#include "workshop_update_service.h"' not in text:
        include_anchor = '#include "hms_lookup.h"\n'
        if include_anchor not in text:
            raise PatchError("web server include anchor missing")
        text = text.replace(include_anchor, include_anchor + '#include "workshop_update_service.h"\n', 1)

    handlers = r'''
// ---------------------------------------------------------------------------
// Workshop OS 12 authoritative GitHub update service API
// ---------------------------------------------------------------------------
static void sendWorkshopUpdateStatus(int httpCode = 200) {
  const WorkshopUpdateRuntimeSnapshot snap = workshopUpdateSnapshot();
  JsonDocument doc;
  doc["channel"] = workshopUpdateChannelName(snap.channel);
  doc["phase"] = workshopUpdatePhaseName(snap.phase);
  doc["progress"] = snap.progressPercent;
  doc["busy"] = snap.busy;
  doc["updateAvailable"] = snap.updateAvailable;
  doc["artifactIdentityVerified"] = snap.artifactIdentityVerified;
  doc["runningVersion"] = snap.runningVersion;
  doc["availableVersion"] = snap.availableVersion;
  doc["availableLabel"] = snap.availableLabel;
  doc["status"] = snap.statusMessage;
  doc["sourceCommit"] = snap.sourceCommit;
  doc["artifactSize"] = snap.artifactSize;
  doc["artifactSha256"] = snap.artifactSha256;
  String json;
  serializeJson(doc, json);
  server.sendHeader("Cache-Control", "no-store");
  server.send(httpCode, "application/json", json);
}

static void handleWorkshopUpdateStatus() {
  sendWorkshopUpdateStatus();
}

static void handleWorkshopUpdateCheck() {
  const bool started = workshopUpdateRequestCheck();
  sendWorkshopUpdateStatus(started ? 202 : 409);
}

static void handleWorkshopUpdateChannel() {
  if (!server.hasArg("channel")) {
    server.send(400, "application/json", "{\"error\":\"channel is required\"}");
    return;
  }
  String channel = server.arg("channel");
  channel.toLowerCase();
  const bool accepted = channel == "stable"
      ? workshopUpdateSetChannel(workshop::platform::UpdateChannel::Stable)
      : channel == "candidate"
          ? workshopUpdateSetChannel(workshop::platform::UpdateChannel::Candidate)
          : false;
  if (!accepted && channel != "stable" && channel != "candidate") {
    server.send(400, "application/json", "{\"error\":\"channel must be stable or candidate\"}");
    return;
  }
  sendWorkshopUpdateStatus(accepted ? 200 : 409);
}

static void handleWorkshopUpdateInstall() {
  const bool started = workshopUpdateRequestInstall();
  sendWorkshopUpdateStatus(started ? 202 : 409);
}
'''
    if "sendWorkshopUpdateStatus" not in text:
        marker = "void initWebServer() {\n"
        if text.count(marker) != 1:
            raise PatchError("web server init anchor missing/non-unique")
        text = text.replace(marker, handlers + "\n" + marker, 1)

    legacy_secure = '''#ifdef ENABLE_OTA_AUTO
  SECURE_POST("/ota/auto", handleOtaAuto);
  SECURE_GET("/ota/status", handleOtaStatus);
#endif
'''
    legacy_raw = '''#ifdef ENABLE_OTA_AUTO
  server.on("/ota/auto",   HTTP_POST, handleOtaAuto);
  server.on("/ota/status", HTTP_GET,  handleOtaStatus);
#endif
'''
    replacement = '''#ifdef ENABLE_OTA_AUTO
  // Legacy URL-driven auto OTA is deliberately not registered in OS12.
  // The compiled transport remains only to avoid destabilizing the frozen
  // baseline; all active device-initiated online update requests go through
  // the manifest-bound UpdateService below.
#endif
  SECURE_GET("/os12/update/status", handleWorkshopUpdateStatus);
  SECURE_POST("/os12/update/check", handleWorkshopUpdateCheck);
  SECURE_POST("/os12/update/channel", handleWorkshopUpdateChannel);
  SECURE_POST("/os12/update/install", handleWorkshopUpdateInstall);
'''
    if replacement not in text:
        if legacy_secure in text:
            text = text.replace(legacy_secure, replacement, 1)
        elif legacy_raw in text:
            text = text.replace(legacy_raw, replacement, 1)
        else:
            raise PatchError("legacy auto-OTA route block not found")

    if '"/ota/auto"' in text[text.find("void initWebServer() {"):text.find("\nvoid handleWebServer()")]:
        raise PatchError("legacy /ota/auto route remains registered")
    for route in (
        '/os12/update/status',
        '/os12/update/check',
        '/os12/update/channel',
        '/os12/update/install',
    ):
        if route not in text:
            raise PatchError(f"missing OS12 update route: {route}")
    path.write_text(text, encoding="utf-8")


def patch_smart_hub(repo: Path) -> None:
    path = repo / "src" / "smart_hub.cpp"
    text = load(path)
    if '#include "workshop_update_service.h"' not in text:
        anchor = '#include "workshop_platform_bridge.h"\n'
        if anchor not in text:
            raise PatchError("smart_hub platform include missing")
        text = text.replace(anchor, anchor + '#include "workshop_update_service.h"\n', 1)

    draw_update = r'''static void drawUi13SoftwareUpdate() {
  const workshop::platform::UpdateState& update=workshopPlatformUpdateState();
  const bool candidate=update.channel==workshop::platform::UpdateChannel::Candidate;
  const bool failed=update.phase==workshop::platform::UpdatePhase::Failed;
  const bool available=update.phase==workshop::platform::UpdatePhase::Available&&update.updateAvailable;
  tft.fillScreen(C10_BG);drawHeader("Software Update",workshopUpdatePhaseName(update.phase),3);uiBottomNav(3,nullptr);
  char running[56];snprintf(running,sizeof(running),"Running %s",update.runningVersion[0]?update.runningVersion:"Unknown");
  hubUi13StepperRow(hubUi13RowRect(0),"Update Channel",candidate?"Candidate":"Stable",running,candidate?C10_ORANGE:C10_ACCENT);
  const char* availableVersion=available&&update.availableVersion[0]?update.availableVersion:(update.manifestFreshness==workshop::platform::Freshness::Fresh?"Up to date":"Not checked");
  const char* availableDetail=available&&update.availableLabel[0]?update.availableLabel:(update.manifestFreshness==workshop::platform::Freshness::Fresh?"Authoritative manifest checked":"Check GitHub when online");
  hubUi13InfoRow(hubUi13RowRect(1),"Available Update",availableVersion,availableDetail,available?C10_GREEN:C10_MUTED);
  char progress[32];if(update.busy)snprintf(progress,sizeof(progress),"%s %u%%",workshopUpdatePhaseName(update.phase),(unsigned)update.progressPercent);else strlcpy(progress,workshopUpdatePhaseName(update.phase),sizeof(progress));
  const char* integrity=update.artifactIdentityVerified?"SHA-256 verified":(failed?"See status in Local Portal":(update.busy?"Do not power off":"Size + SHA-256 required"));
  hubUi13InfoRow(hubUi13RowRect(2),"Update Status",progress,integrity,failed?C10_ORANGE:(update.artifactIdentityVerified?C10_GREEN:C10_ACCENT));
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);
  const char* action=update.busy?"Working...":(available?"Review & Install":"Check Now");
  hubV1125Action(hubUi13ActionRect(),action,C10_ACCENT,!update.busy,false);hubMarkFrameDirty();g_dirty=false;
}

static void drawUi13UpdateConfirm() {
  const workshop::platform::UpdateState& update=workshopPlatformUpdateState();const int16_t W=tft.width();
  tft.fillScreen(C10_BG);drawHeader("Install Workshop OS?",nullptr,3);uiBottomNav(3,nullptr);
  HubRect card=hubLandscape()?hr(8,52,W-16,146):hr(8,62,W-16,250);hubV1125Card(card,C10_ORANGE,true);
  char title[96];snprintf(title,sizeof(title),"Install %s",update.availableVersion[0]?update.availableVersion:"selected update");
  uiDrawFit(title,card.x+16,card.y+16,card.w-32,FONT_LARGE,TL_DATUM,C10_TEXT,C10_SURFACE_2);
  uiDrawFit("Workshop OS will download the exact GitHub OTA image, verify its declared size and SHA-256, write only the inactive application partition, then restart.",card.x+16,card.y+58,card.w-32,FONT_BODY,TL_DATUM,C10_MUTED,C10_SURFACE_2);
  uiDrawFit("Do not power off the WS350 during the update.",card.x+16,card.y+116,card.w-32,FONT_SMALL,TL_DATUM,C10_ORANGE,C10_SURFACE_2);
  hubV1125Action(hubUi13BackRect(),"Cancel",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Install",C10_ORANGE,true,false);hubMarkFrameDirty();g_dirty=false;
}'''
    text = replace_block(text, "static void drawUi13SoftwareUpdate()", draw_update, "Software Update screen")

    old_draw_dispatch = '''if(g_audioSettingsView){drawAudioSettings(full);return;}if(g_networkSettingsView){drawNetworkEssentials(full);return;}if(g_ui12SystemView==1){drawUi12PortalAccess();return;}if(g_ui12SystemView==2){drawUi13DateTime();return;}if(g_ui12SystemView==3){drawUi13SoftwareUpdate();return;}if(g_ui12SystemView==4){drawUi13Diagnostics();return;}'''
    new_draw_dispatch = '''if(g_audioSettingsView){drawAudioSettings(full);return;}if(g_networkSettingsView){drawNetworkEssentials(full);return;}if(g_ui12SystemView==1){drawUi12PortalAccess();return;}if(g_ui12SystemView==2){drawUi13DateTime();return;}if(g_ui12SystemView==3){drawUi13SoftwareUpdate();return;}if(g_ui12SystemView==4){drawUi13Diagnostics();return;}if(g_ui12SystemView==5){drawUi13UpdateConfirm();return;}'''
    text = replace_once(text, old_draw_dispatch, new_draw_dispatch, "System update-confirm dispatch")

    old_touch = r'''      if(g_ui12SystemView==3||g_ui12SystemView==4){
        if(hubUi13BackRect().contains(x,y)){g_ui12SystemView=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ActionRect().contains(x,y)){g_ui12SystemView=1;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}return true;
      }'''
    new_touch = r'''      if(g_ui12SystemView==3){
        const workshop::platform::UpdateState& update=workshopPlatformUpdateState();
        if(!update.busy&&(hubUi13MinusRect(0).contains(x,y)||hubUi13PlusRect(0).contains(x,y))){const workshop::platform::UpdateChannel next=update.channel==workshop::platform::UpdateChannel::Candidate?workshop::platform::UpdateChannel::Stable:workshop::platform::UpdateChannel::Candidate;workshopUpdateSetChannel(next);buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13BackRect().contains(x,y)){g_ui12SystemView=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ActionRect().contains(x,y)&&!update.busy){if(update.phase==workshop::platform::UpdatePhase::Available&&update.updateAvailable)g_ui12SystemView=5;else workshopUpdateRequestCheck();buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}return true;
      }
      if(g_ui12SystemView==5){
        if(hubUi13BackRect().contains(x,y)){g_ui12SystemView=3;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ActionRect().contains(x,y)){workshopUpdateRequestInstall();g_ui12SystemView=3;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}return true;
      }
      if(g_ui12SystemView==4){
        if(hubUi13BackRect().contains(x,y)){g_ui12SystemView=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ActionRect().contains(x,y)){g_ui12SystemView=1;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}return true;
      }'''
    text = replace_once(text, old_touch, new_touch, "Software Update touch actions")

    required = (
        "workshopPlatformUpdateState()",
        "workshopUpdateRequestCheck()",
        "workshopUpdateRequestInstall()",
        "workshopUpdateSetChannel(next)",
        "drawUi13UpdateConfirm",
        "Size + SHA-256 required",
        "Do not power off the WS350 during the update.",
    )
    for needle in required:
        if needle not in text:
            raise PatchError(f"Software Update UI marker missing: {needle}")
    path.write_text(text, encoding="utf-8")


def patch_build_identity(repo: Path) -> None:
    path = repo / "include" / "smart_home_build.h"
    text = load(path)
    marker = "#define WORKSHOP_OS12_DEVICE_UPDATE 1"
    if marker not in text:
        text += '''\n// Workshop OS 12 device-native update slice. Release workflows may override
// WORKSHOP_OS_RELEASE_VERSION at compile time for an exact published artifact.
#define WORKSHOP_OS12_DEVICE_UPDATE 1
#ifndef WORKSHOP_OS_RELEASE_VERSION
#define WORKSHOP_OS_RELEASE_VERSION SMART_HOME_VERSION
#endif
'''
    path.write_text(text, encoding="utf-8")


def apply(repo: Path, source_root: Path) -> None:
    build = repo / "include" / "smart_home_build.h"
    if not build.is_file() or "WORKSHOP_OS_V11_28_UI13" not in load(build):
        raise PatchError("OS12 device update requires reconstructed UI13 source")
    if not (repo / "include" / "workshop_platform_bridge.h").is_file():
        raise PatchError("OS12 platform bridge must be installed first")
    if "PortalLoginPageState" not in load(repo / "src" / "web_server.cpp"):
        raise PatchError("OS12 portal hardening must be applied before device update routes")

    patch_service(repo, source_root)
    patch_ws350_build(repo)
    patch_main(repo)
    patch_web_server(repo)
    patch_smart_hub(repo)
    patch_build_identity(repo)
    print("Workshop OS 12 device-native GitHub update service installed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="reconstructed UI13 BambuHelper root")
    parser.add_argument("--source-root", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve(), Path(args.source_root).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
