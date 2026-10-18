from __future__ import annotations

def fail(message: str) -> None:
    raise SystemExit(message)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    # If the replacement embeds the original anchor (e.g., "foo" -> "foo bar"),
    # detect already-applied state by looking for the full replacement first.
    if old in new and new in text:
        print(f"{label}: already applied, skipping")
        return text
    count = text.count(old)
    if count == 0 and new in text:
        print(f"{label}: already applied, skipping")
        return text
    if count != 1:
        fail(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def replace_braced_block(text: str, start: str, replacement: str, label: str) -> str:
    pos = text.find(start)
    if pos < 0:
        fail(f"{label}: start anchor missing")
    brace = text.find("{", pos)
    if brace < 0:
        fail(f"{label}: opening brace missing")
    depth = 0
    in_string = False
    quote = ""
    escape = False
    for i in range(brace, len(text)):
        c = text[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == quote:
                in_string = False
            continue
        if c in ("'", '"'):
            in_string = True
            quote = c
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[:pos] + replacement + text[i + 1 :]
    fail(f"{label}: closing brace missing")


def get_braced_block(text: str, start: str, label: str) -> tuple[int, int, str]:
    pos = text.find(start)
    if pos < 0:
        fail(f"{label}: start anchor missing")
    brace = text.find("{", pos)
    if brace < 0:
        fail(f"{label}: opening brace missing")
    depth = 0
    in_string = False
    quote = ""
    escape = False
    for i in range(brace, len(text)):
        c = text[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == quote:
                in_string = False
            continue
        if c in ("'", '"'):
            in_string = True
            quote = c
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return pos, i + 1, text[pos:i + 1]
    fail(f"{label}: closing brace missing")


class PatchError(RuntimeError):
    """Raised when a patch anchor is missing or matches more than once."""
    pass


def _cpp_body_end(text: str, brace: int, label: str) -> int:
    """Return the index just past the brace matching text[brace].

    Skips braces inside string/char literals and // or /* */ comments.
    """
    depth = 0
    i = brace
    n = len(text)
    while i < n:
        c = text[i]
        if c in ("'", '"'):
            i += 1
            while i < n and text[i] != c:
                i += 2 if text[i] == "\\" else 1
        elif text.startswith("//", i):
            nl = text.find("\n", i)
            i = n if nl < 0 else nl
        elif text.startswith("/*", i):
            close = text.find("*/", i + 2)
            if close < 0:
                break
            i = close + 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise PatchError(f"{label}: closing brace missing")


def replace_cpp_function(text: str, signature: str, replacement: str, label: str) -> str:
    """Replace the whole C++ function starting at a unique signature.

    The trailing newline after the closing brace is consumed so a replacement
    ending in "}\\n" keeps the original spacing. Raises PatchError.
    """
    count = text.count(signature)
    if count != 1:
        raise PatchError(f"{label}: expected one function signature, found {count}")
    start = text.find(signature)
    brace = text.find("{", start + len(signature))
    if brace < 0:
        raise PatchError(f"{label}: opening brace missing")
    end = _cpp_body_end(text, brace, label)
    if text.startswith("\r\n", end):
        end += 2
    elif text.startswith("\n", end):
        end += 1
    return text[:start] + replacement + text[end:]
