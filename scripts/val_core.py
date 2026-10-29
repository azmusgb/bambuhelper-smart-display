#!/usr/bin/env python3
"""Core Validation Engine for Workshop OS.
Centralizes the 'need', 'forbid', and 'block' logic to prevent script drift.
"""
from __future__ import annotations
from pathlib import Path
import re

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

def ordered(text: str, needles: list[str], label: str) -> None:
    last = -1
    for needle in needles:
        at = text.find(needle)
        if at < 0:
            raise ValidationError(f"missing {label}: {needle}")
        if at < last:
            raise ValidationError(f"{label}: {needle!r} is out of order")
        last = at
