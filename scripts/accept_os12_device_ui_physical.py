#!/usr/bin/env python3
"""Whole-device 480x320 physical UI acceptance for Workshop OS 12.

Navigates the canonical /hub/views + /hub/show contract, proves the exact
framebuffer geometry, and records operator evidence for hierarchy, clipping,
touch targets, state clarity, and navigation. Sensitive views are never saved
or hashed into the evidence bundle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urljoin
import urllib.request

from accept_os12_media_physical import (
    AcceptanceError,
    Client,
    check,
    login,
    protected_root_is_open,
    read_code,
    update_identity,
)

REQUIRED_VIEWS = (
    "home",
    "printer",
    "workshop",
    "more",
    "settings-display",
    "settings-sounds",
    "settings-network",
    "settings-printer-power",
    "system",
    "system-date-time",
    "system-update",
    "system-diagnostics",
    "media",
    "media-lab",
    "media-video",
)

def observation(prompt: str) -> bool | None:
    while True:
        answer=input(f"{prompt} [y/n/u]: ").strip().lower()
        if answer in ("y","yes"): return True
        if answer in ("n","no"): return False
        if answer in ("u","unknown","unsure","?"): return None
        print("Please answer y, n, or u.")

def catalog(client: Client)->list[dict]:
    r=client.request("/hub/views",headers={"X-BambuHelper-Client":"1","Accept":"application/json"},timeout=10.0)
    check(r.status==200,f"GET /hub/views returned HTTP {r.status}")
    try: payload=json.loads(r.body)
    except json.JSONDecodeError as exc: raise AcceptanceError("native view catalog did not return JSON") from exc
    views=payload.get("views")
    check(isinstance(views,list) and views,"native view catalog contains no views")
    return views

def show(client: Client, view_id: str)->None:
    r=client.request("/hub/show",method="POST",form={"page":view_id},headers={"X-BambuHelper-Client":"1","Accept":"application/json,text/plain,*/*"},timeout=10.0)
    check(r.status==200,f"/hub/show refused {view_id}: HTTP {r.status}")
    time.sleep(0.30)

def frame_probe(client: Client)->dict:
    url=urljoin(client.base_url+"/","hub/frame.ppm")
    req=urllib.request.Request(url,method="GET",headers={
        "User-Agent":"WorkshopOS-Device-UI-Acceptance/1",
        "X-BambuHelper-Client":"1",
        "Accept":"image/x-portable-pixmap",
    })
    try:
        with client.opener.open(req,timeout=12.0) as resp:
            status=resp.status
            body=resp.read()
    except Exception as exc:
        raise AcceptanceError(f"framebuffer capture request failed: {exc}") from exc
    check(status==200,f"GET /hub/frame.ppm returned HTTP {status}")
    check(body.startswith(b"P6\n"),"framebuffer capture is not binary PPM")
    parts=body.split(b"\n",3)
    check(len(parts)==4,"PPM header is incomplete")
    dims=parts[1].split()
    check(len(dims)==2,"PPM dimensions are malformed")
    width,height=int(dims[0]),int(dims[1])
    check(parts[2].strip()==b"255","PPM max value is not 255")
    expected=width*height*3
    check(len(parts[3])==expected,f"PPM payload size mismatch: expected {expected}, got {len(parts[3])}")
    return {
        "width":width,
        "height":height,
        "sha256":hashlib.sha256(body).hexdigest(),
        "bytes":len(body),
    }

def output_path(arg: str|None, stamp: str)->Path:
    if arg: return Path(arg).expanduser().resolve()
    return Path.home()/ "Downloads" / f"workshop-os12-device-ui-physical-{stamp}.json"

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--base-url",default=os.environ.get("WORKSHOP_OS_URL","http://10.0.0.124"))
    ap.add_argument("--output")
    args=ap.parse_args()
    base=args.base_url.rstrip("/")
    check(base.startswith(("http://","https://")),"--base-url must start with http:// or https://")
    now=datetime.now(timezone.utc);stamp=now.strftime("%Y%m%d-%H%M%S");dest=output_path(args.output,stamp)
    evidence={
        "schemaVersion":1,
        "kind":"workshop-os12-whole-device-ui-physical-acceptance",
        "recordedAt":now.isoformat(),
        "targetHost":urlparse(base).hostname,
        "runtimeIdentity":None,
        "portalMode":"unknown",
        "requiredViews":list(REQUIRED_VIEWS),
        "views":{},
        "rootNavigation":None,
        "childNavigation":None,
        "touchResponsiveness":None,
        "noUnexpectedReboot":None,
        "passed":False,
        "completed":False,
        "failure":None,
        "scope":"whole-device 480x320 UI acceptance; does not itself promote accepted/stable release state",
    }
    client=Client(base)
    try:
        if protected_root_is_open(client):
            evidence["portalMode"]="temporary-open-lan"
            print("DEV OPEN  temporary physical-test portal mode detected")
        else:
            evidence["portalMode"]="portal-code"
            code=read_code();login(client,code,"whole-device UI acceptance");code=""

        identity=update_identity(client);evidence["runtimeIdentity"]=identity
        views=catalog(client);by_id={str(v.get("id","")):v for v in views}
        missing=[v for v in REQUIRED_VIEWS if v not in by_id]
        check(not missing,"required native views missing: "+", ".join(missing))
        print(f"Running: {identity['runningVersion']} @ {identity['runningSourceCommit']}")
        print("Acceptance target: exact 480x320 physical framebuffer\n")

        for view_id in REQUIRED_VIEWS:
            item=by_id[view_id]
            label=str(item.get("label") or view_id)
            sensitive=bool(item.get("sensitive"))
            print(f"VIEW {label} ({view_id})")
            show(client,view_id)
            record={"label":label,"group":item.get("group"),"sensitive":sensitive,"frame":None,"visible":None,"noClipping":None,"hierarchyClear":None,"controlsComfortable":None}
            if sensitive:
                print("  Sensitive view: framebuffer hash/capture evidence intentionally skipped.")
            else:
                probe=frame_probe(client)
                check(probe["width"]==480 and probe["height"]==320,f"{view_id}: expected 480x320, got {probe['width']}x{probe['height']}")
                record["frame"]=probe
                print(f"  FRAME {probe['width']}x{probe['height']} sha256={probe['sha256'][:16]}…")
            record["visible"]=observation(f"Is {label} visibly rendered on the WS350?")
            record["noClipping"]=observation(f"Does {label} have no obvious clipping, overlap, or off-screen content?")
            record["hierarchyClear"]=observation(f"Is the information hierarchy/state on {label} immediately understandable?")
            record["controlsComfortable"]=observation(f"Are visible controls on {label} comfortably finger-sized and clearly enabled/disabled?")
            evidence["views"][view_id]=record

        print("\nGLOBAL NAVIGATION / RESPONSIVENESS")
        evidence["rootNavigation"]=observation("Do Home / Printer / Workshop / More root destinations behave consistently?")
        evidence["childNavigation"]=observation("Do Back/Done actions return to the expected parent without hidden or surprising navigation?")
        evidence["touchResponsiveness"]=observation("Did touch remain responsive across the full walk with no perceptible interaction starvation?")
        evidence["noUnexpectedReboot"]=observation("Did the WS350 stay running continuously with no unexpected reboot, watchdog, or recovery entry?")

        evidence["completed"]=True
        required_bool=[]
        for rec in evidence["views"].values():
            required_bool.extend([rec["visible"],rec["noClipping"],rec["hierarchyClear"],rec["controlsComfortable"]])
        required_bool.extend([evidence["rootNavigation"],evidence["childNavigation"],evidence["touchResponsiveness"],evidence["noUnexpectedReboot"]])
        evidence["passed"]=all(v is True for v in required_bool)
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps(evidence,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print(f"\nEvidence: {dest}")
        if evidence["passed"]:
            print("WHOLE-DEVICE 480x320 UI PHYSICAL ACCEPTANCE: PASS")
            print("This establishes the UI physical gate only; accepted/stable promotion remains a separate release decision.")
            return 0
        failed=[]
        unknown=[]
        for vid,rec in evidence["views"].items():
            for key in ("visible","noClipping","hierarchyClear","controlsComfortable"):
                if rec[key] is False: failed.append(f"{vid}.{key}")
                elif rec[key] is None: unknown.append(f"{vid}.{key}")
        for key in ("rootNavigation","childNavigation","touchResponsiveness","noUnexpectedReboot"):
            if evidence[key] is False: failed.append(key)
            elif evidence[key] is None: unknown.append(key)
        print("WHOLE-DEVICE 480x320 UI PHYSICAL ACCEPTANCE: FAIL / PENDING")
        if failed: print("Failed: "+", ".join(failed))
        if unknown: print("Unknown: "+", ".join(unknown))
        return 1
    except (AcceptanceError,KeyboardInterrupt,EOFError) as exc:
        evidence["failure"]="operator_aborted" if isinstance(exc,(KeyboardInterrupt,EOFError)) else str(exc)
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps(evidence,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print(f"\nEvidence: {dest}")
        print(f"FAIL: {evidence['failure']}")
        return 130 if evidence["failure"]=="operator_aborted" else 1

if __name__=="__main__": raise SystemExit(main())
