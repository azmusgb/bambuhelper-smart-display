#!/usr/bin/env python3
from pathlib import Path
import argparse

from apply_smart_home_secret_safe_backups_v8_2 import apply as apply_secret_safe_backups


class PatchError(RuntimeError):
    pass


def replace_once(text: str, old: str, new: str, name: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{name}: expected exactly 1 match, found {count}")
    return text.replace(old, new, 1)


def apply(repo: Path) -> None:
    p = repo / "src" / "web_server.cpp"
    text = p.read_text(encoding="utf-8")

    replacements = [
        (
            '  server.on("/power/stats",  HTTP_GET, handleGetPowerStats);\n',
            '  SECURE_GET("/power/stats", handleGetPowerStats);\n',
            "power stats route",
        ),
        (
            '  server.on("/led/test",    HTTP_POST, handleLedTest);\n',
            '  SECURE_POST("/led/test", handleLedTest);\n',
            "LED test route",
        ),
        (
            '  server.on("/ota/slots",    HTTP_GET,  handleOtaSlots);\n',
            '  SECURE_GET("/ota/slots", handleOtaSlots);\n',
            "OTA slots route",
        ),
        (
            '  server.on("/ota/auto",   HTTP_POST, handleOtaAuto);\n',
            '  SECURE_POST("/ota/auto", handleOtaAuto);\n',
            "OTA auto route",
        ),
        (
            '  server.on("/ota/status", HTTP_GET,  handleOtaStatus);\n',
            '  SECURE_GET("/ota/status", handleOtaStatus);\n',
            "OTA status route",
        ),
    ]

    for old, new, name in replacements:
        if old in text:
            text = replace_once(text, old, new, name)
        elif new not in text:
            raise PatchError(f"{name}: neither insecure nor secured form found")

    p.write_text(text, encoding="utf-8")

    # v8.2 stays composed after the route-coverage fix so the existing CI entry
    # point validates the whole hardened stack without duplicating the pipeline.
    apply_secret_safe_backups(repo)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("Pass --apply")
    apply(Path(args.repo))
    print("Smart Home v8.1 route coverage + v8.2 secret-safe backups applied")
