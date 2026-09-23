#!/usr/bin/env python3
"""Fix the Workshop root surface after physical acceptance exposed a dead UI.

This layer is intentionally later than the post-capture visual hardening. It:
- wires Workshop to the authoritative Filament Inventory device-feed snapshot;
- presents a focused single-panel setup state until device-feed access exists;
- shows Refresh + Local Portal actions only when inventory access is configured;
- removes four stale hidden Workshop touch zones inherited from v11.25;
- preserves Unknown/stale/conflict states instead of deriving inventory from AMS telemetry.
"""
from __future__ import annotations

import argparse
from pathlib import Path


class PatchError(RuntimeError):
    pass


def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def braced_end(text: str, start: int, label: str) -> int:
    brace = text.find("{", start)
    if brace < 0:
        raise PatchError(f"{label}: opening brace missing")
    depth = 0
    string = None
    escape = False
    line = False
    block = False
    i = brace
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""
        if line:
            if c == "\n":
                line = False
        elif block:
            if c == "*" and n == "/":
                block = False
                i += 1
        elif string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == string:
                string = None
        elif c == "/" and n == "/":
            line = True
            i += 1
        elif c == "/" and n == "*":
            block = True
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
    raise PatchError(f"{label}: closing brace missing")


def replace_block(text: str, signature: str, replacement: str, label: str) -> str:
    start = text.find(signature)
    if start < 0 or text.find(signature, start + 1) >= 0:
        raise PatchError(f"{label}: signature missing/non-unique: {signature}")
    end = braced_end(text, start, label)
    return text[:start] + replacement.strip() + text[end:]


def insert_before_once(text: str, anchor: str, addition: str, label: str) -> str:
    if addition.strip() in text:
        return text
    count = text.count(anchor)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(anchor, addition.rstrip() + "\n\n" + anchor, 1)


WORKSHOP_HELPERS = r'''
static HubRect hubOs12WorkshopActionRect(uint8_t i) {
  const int16_t W=tft.width();
  const int16_t m=OS12V_INSET,g=8,y=220,h=44;
  const int16_t cw=(W-2*m-g)/2;
  if(i==0)return hr(m,y,cw,h);
  return hr(m+cw+g,y,W-m-(m+cw+g),h);
}

static HubRect hubOs12WorkshopSetupRect() {
  const int16_t W=tft.width();
  const int16_t x=56,y=166,h=46;
  return hr(x,y,W-x*2,h);
}

static const char* hubOs12WorkshopReadinessLabel(
    workshop::platform::InventoryReadinessState state) {
  using workshop::platform::InventoryReadinessState;
  switch(state){
    case InventoryReadinessState::Ready:return "Ready";
    case InventoryReadinessState::ReadyWithSubstitute:return "Ready + substitute";
    case InventoryReadinessState::NeedsLoad:return "Needs load";
    case InventoryReadinessState::NeedsDry:return "Needs dry";
    case InventoryReadinessState::InsufficientQuantity:return "Insufficient";
    case InventoryReadinessState::EvidenceStale:return "Evidence stale";
    case InventoryReadinessState::Undetermined:
    default:return "Undetermined";
  }
}

static uint16_t hubOs12WorkshopReadinessColor(
    workshop::platform::InventoryReadinessState state) {
  using workshop::platform::InventoryReadinessState;
  switch(state){
    case InventoryReadinessState::Ready:return C10_GREEN;
    case InventoryReadinessState::ReadyWithSubstitute:return C10_ACCENT;
    case InventoryReadinessState::NeedsLoad:
    case InventoryReadinessState::NeedsDry:
    case InventoryReadinessState::EvidenceStale:return C10_ORANGE;
    case InventoryReadinessState::InsufficientQuantity:return C10_RED;
    case InventoryReadinessState::Undetermined:
    default:return C10_MUTED;
  }
}

static const char* hubOs12WorkshopHeaderState(const WorkshopInventoryRuntimeSnapshot& snap) {
  using workshop::platform::Freshness;
  if(snap.busy)return "SYNCING";
  if(!snap.credentialConfigured)return "SETUP";
  if(!snap.state.available)return "UNKNOWN";
  switch(snap.state.freshness){
    case Freshness::Fresh:return "CURRENT";
    case Freshness::Stale:return "STALE";
    case Freshness::Conflicting:return "CONFLICT";
    case Freshness::Unknown:
    default:return "UNKNOWN";
  }
}
'''


WORKSHOP_DRAW = r'''
static void drawWorkshop(bool full) {
  (void)full;
  const int16_t W=tft.width();
  const WorkshopInventoryRuntimeSnapshot inv=workshopInventorySnapshot();
  const auto& state=inv.state;
  using workshop::platform::Freshness;
  using workshop::platform::InventoryPlacementState;
  using workshop::platform::InventoryReadinessState;

  tft.fillScreen(OS12V_BG);
  drawHeader("Workshop",inv.credentialConfigured?hubOs12WorkshopHeaderState(inv):nullptr,2);
  uiBottomNav(2,nullptr);

  if(!inv.credentialConfigured){
    const HubRect panel=hr(OS12V_INSET,52,W-OS12V_INSET*2,164);
    tft.fillRoundRect(panel.x,panel.y,panel.w,panel.h,OS12V_RADIUS,OS12V_SURFACE2);
    tft.drawRoundRect(panel.x,panel.y,panel.w,panel.h,OS12V_RADIUS,OS12V_LINE);

    uiDrawFit("FILAMENT INVENTORY",W/2,68,panel.w-36,FONT_SMALL,MC_DATUM,OS12V_MUTED,OS12V_SURFACE2);
    uiDrawFit("Inventory not connected",W/2,96,panel.w-36,FONT_LARGE,MC_DATUM,OS12V_TEXT,OS12V_SURFACE2);
    uiDrawFit("Connect this display in Local Portal",W/2,126,panel.w-44,FONT_BODY,MC_DATUM,OS12V_TEXT,OS12V_SURFACE2);
    uiDrawFit("for readiness, loaded spools, and alerts.",W/2,148,panel.w-44,FONT_SMALL,MC_DATUM,OS12V_MUTED,OS12V_SURFACE2);

    hubV1125Action(
        hubOs12WorkshopSetupRect(),
        "Set Up Inventory",
        C10_ACCENT,
        workshopPlatformWifiOnline(),
        false);

    hubMarkFrameDirty();
    g_dirty=false;
    return;
  }

  HubRect readiness=hr(OS12V_INSET,48,W-OS12V_INSET*2,50);
  HubRect loaded=hr(OS12V_INSET,104,W-OS12V_INSET*2,50);
  HubRect attention=hr(OS12V_INSET,160,W-OS12V_INSET*2,54);

  const bool fresh=state.available&&state.freshness==Freshness::Fresh;
  const char* readinessValue="Undetermined";
  const char* readinessDetail="No authoritative inventory evidence";
  uint16_t readinessColor=C10_MUTED;

  if(inv.busy){
    readinessValue="Refreshing";
    readinessDetail="Waiting for profile-scoped Filament Inventory evidence";
    readinessColor=C10_ACCENT;
  }else if(!state.available){
    readinessValue="Undetermined";
    readinessDetail=inv.statusMessage[0]?inv.statusMessage:"Filament Inventory unavailable";
  }else if(!fresh){
    readinessValue=state.freshness==Freshness::Conflicting?"Evidence conflict":"Evidence stale";
    readinessDetail="Refresh or resolve evidence before relying on readiness";
    readinessColor=state.freshness==Freshness::Conflicting?C10_RED:C10_ORANGE;
  }else{
    readinessValue=hubOs12WorkshopReadinessLabel(state.readiness);
    readinessDetail="Authoritative profile-scoped readiness";
    readinessColor=hubOs12WorkshopReadinessColor(state.readiness);
  }
  hubOs12EvidenceRow(readiness,"PRINT READINESS",readinessValue,readinessDetail,readinessColor);

  char loadedValue[28];
  char loadedDetail[72];
  uint16_t loadedColor=C10_MUTED;
  if(!state.available){
    strlcpy(loadedValue,"Unknown",sizeof(loadedValue));
    strlcpy(loadedDetail,inv.statusMessage[0]?inv.statusMessage:"Placement evidence unavailable",sizeof(loadedDetail));
  }else if(state.placementState==InventoryPlacementState::Current&&!state.placementVerificationRequired){
    snprintf(loadedValue,sizeof(loadedValue),"%u loaded",(unsigned)state.loadedCount);
    snprintf(loadedDetail,sizeof(loadedDetail),"%u spools · canonical placement current",(unsigned)state.spoolCount);
    loadedColor=C10_GREEN;
  }else if(state.placementState==InventoryPlacementState::Stale){
    strlcpy(loadedValue,"Placement stale",sizeof(loadedValue));
    snprintf(loadedDetail,sizeof(loadedDetail),"%u stale · verify in Filament Inventory",(unsigned)state.stalePlacementCount);
    loadedColor=C10_ORANGE;
  }else if(state.placementState==InventoryPlacementState::Conflict){
    strlcpy(loadedValue,"Placement conflict",sizeof(loadedValue));
    snprintf(loadedDetail,sizeof(loadedDetail),"%u conflicts · resolve in Filament Inventory",(unsigned)state.placementConflictCount);
    loadedColor=C10_RED;
  }else{
    strlcpy(loadedValue,"Unknown",sizeof(loadedValue));
    snprintf(loadedDetail,sizeof(loadedDetail),"%u unknown · verify canonical placement",(unsigned)state.unknownPlacementCount);
  }
  hubOs12EvidenceRow(loaded,"LOADED SPOOLS",loadedValue,loadedDetail,loadedColor);

  const uint16_t quantityReview=
      state.unknownQuantityCount+state.staleQuantityCount+state.conflictCount+state.invalidLineageCount;
  const uint16_t placementReview=
      state.unknownPlacementCount+state.stalePlacementCount+state.placementConflictCount;
  const bool quantityNeedsVerification=state.quantityVerificationRequired||quantityReview>0;
  const bool placementNeedsVerification=state.placementVerificationRequired||placementReview>0;
  const bool readinessNeedsAction=
      fresh&&(state.readiness==InventoryReadinessState::NeedsLoad||
             state.readiness==InventoryReadinessState::NeedsDry||
             state.readiness==InventoryReadinessState::InsufficientQuantity||
             state.readiness==InventoryReadinessState::EvidenceStale);
  const uint16_t reviewCount=
      state.lowCount+quantityReview+placementReview+(readinessNeedsAction?1U:0U)+
      ((quantityNeedsVerification&&quantityReview==0)?1U:0U)+
      ((placementNeedsVerification&&placementReview==0)?1U:0U);
  char attentionValue[28];
  char attentionDetail[72];
  uint16_t attentionColor=C10_MUTED;

  if(!state.available){
    strlcpy(attentionValue,"Unknown",sizeof(attentionValue));
    strlcpy(attentionDetail,inv.statusMessage[0]?inv.statusMessage:"No authoritative attention evidence",sizeof(attentionDetail));
  }else if(reviewCount==0&&fresh){
    strlcpy(attentionValue,"No issues",sizeof(attentionValue));
    strlcpy(attentionDetail,"No inventory evidence currently requires review",sizeof(attentionDetail));
    attentionColor=C10_GREEN;
  }else{
    strlcpy(attentionValue,"Needs review",sizeof(attentionValue));
    snprintf(attentionDetail,sizeof(attentionDetail),"Low %u · Qty %u · Place %u",
        (unsigned)state.lowCount,(unsigned)quantityReview,(unsigned)placementReview);
    attentionColor=(state.conflictCount||state.invalidLineageCount||state.placementConflictCount)?C10_RED:C10_ORANGE;
  }
  hubOs12EvidenceRow(attention,"ATTENTION",attentionValue,attentionDetail,attentionColor);

  hubV1125Action(
      hubOs12WorkshopActionRect(0),
      inv.busy?"Refreshing":"Refresh",
      C10_ACCENT,
      !inv.busy,
      false);
  hubV1125Action(
      hubOs12WorkshopActionRect(1),
      "Local Portal",
      C10_ACCENT,
      workshopPlatformWifiOnline(),
      false);

  hubMarkFrameDirty();
  g_dirty=false;
}
'''


WORKSHOP_TOUCH = r'''
if(cur==SCREEN_HUB_WORKSHOP){
    const WorkshopInventoryRuntimeSnapshot inv=workshopInventorySnapshot();

    if(!inv.credentialConfigured){
      if(hubOs12WorkshopSetupRect().contains(x,y)&&workshopPlatformWifiOnline()){
        g_ui12SettingsView=0;
        g_ui12SystemView=1;
        g_networkSettingsView=false;
        g_audioSettingsView=false;
        setPage(SCREEN_HUB_SYSTEM);
        buzzerPlay(BUZZ_CLICK);
        g_dirty=true;
      }
      return true;
    }

    if(hubOs12WorkshopActionRect(0).contains(x,y)){
      if(!inv.busy){
        if(workshopInventoryRequestRefresh())buzzerPlay(BUZZ_CLICK);
        g_dirty=true;
      }
      return true;
    }
    if(hubOs12WorkshopActionRect(1).contains(x,y)){
      if(workshopPlatformWifiOnline()){
        g_ui12SettingsView=0;
        g_ui12SystemView=1;
        g_networkSettingsView=false;
        g_audioSettingsView=false;
        setPage(SCREEN_HUB_SYSTEM);
        buzzerPlay(BUZZ_CLICK);
        g_dirty=true;
      }
      return true;
    }
    return true;
  }
'''


def apply(repo: Path) -> None:
    path = repo / "src" / "smart_hub.cpp"
    text = load(path)

    include = '#include "workshop_inventory_service.h"\n'
    if include not in text:
        anchor = '#include "workshop_platform_bridge.h"\n'
        if text.count(anchor) != 1:
            raise PatchError("inventory include anchor missing/non-unique")
        text = text.replace(anchor, anchor + include, 1)

    if "static HubRect hubOs12WorkshopActionRect(" not in text:
        text = insert_before_once(
            text,
            "static void drawWorkshop(bool full)",
            WORKSHOP_HELPERS,
            "Workshop helper insertion",
        )

    text = replace_block(
        text,
        "static void drawWorkshop(bool full)",
        WORKSHOP_DRAW,
        "Workshop renderer",
    )
    text = replace_block(
        text,
        "if(cur==SCREEN_HUB_WORKSHOP){",
        WORKSHOP_TOUCH,
        "Workshop touch dispatch",
    )

    path.write_text(text, encoding="utf-8")
    print("Workshop OS 12 Workshop surface runtime fix applied")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
