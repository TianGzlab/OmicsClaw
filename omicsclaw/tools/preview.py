"""Tool arguments as a person may be shown them: bounded, deterministic, inert.

:func:`preview_arguments` turns a raw JSON argument payload into one line
of text for an approval prompt. It is built from two rules that a display
layer reuses: :func:`escape_unsafe`, which writes every character that
could act on a terminal or a chat as an escape, and
:func:`redact_credentials`, which hides the values under credential-named
keys. :func:`is_credential_key` is the key-name rule behind the second,
shared with the Desktop wire projection.

Standard library only.
"""

from __future__ import annotations

import json
import unicodedata
from typing import Any

__all__ = [
    "CREDENTIAL_KEY_FAMILIES",
    "MAX_PREVIEW_CHARS",
    "REDACTED",
    "escape_unsafe",
    "is_credential_key",
    "preview_arguments",
    "redact_credentials",
]

MAX_PREVIEW_CHARS = 1000
"""Characters of preview kept before :func:`preview_arguments` cuts it."""

REDACTED = "[redacted]"
"""What the value under a credential-named key is replaced by."""

CREDENTIAL_KEY_FAMILIES: frozenset[str] = frozenset(
    {
        "accesskey",
        "accesskeyid",
        "accesstoken",
        "apikey",
        "authorization",
        "clientsecret",
        "cookie",
        "credential",
        "credentials",
        "password",
        "passwd",
        "privatekey",
        "refreshtoken",
        "secret",
        "secretaccesskey",
        "secretkey",
        "setcookie",
        "token",
    }
)
"""Normalised key names whose values are credentials.

Normalised means lower-cased with everything but letters and digits
removed; see :func:`is_credential_key` for how a key is compared."""

_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Zl", "Zp"})
"""Unicode categories written as escapes: controls (ESC, CR, LF, NEL, DEL),
format characters (bidi overrides, zero-width), lone surrogates, and the
line and paragraph separators."""


def is_credential_key(name: str) -> bool:
    """Whether a mapping key names a credential.

    Case and non-alphanumeric characters are ignored, so ``API_KEY``,
    ``x-api-key`` and ``apiKey`` all read as ``apikey``. The key matches when
    that normalised form ends with one of :data:`CREDENTIAL_KEY_FAMILIES`:
    ``github_token`` and ``Proxy-Authorization`` match, ``max_tokens`` does
    not.
    """
    normalized = "".join(char for char in name.lower() if char.isalnum())
    return any(normalized.endswith(family) for family in CREDENTIAL_KEY_FAMILIES)


def preview_arguments(arguments: str, *, limit: int = MAX_PREVIEW_CHARS) -> str:
    """One line showing what a tool call's arguments are.

    The payload is decoded and re-encoded as JSON with sorted keys, so two
    payloads that decode alike preview alike. At any depth, the value under a
    key :func:`is_credential_key` accepts becomes :data:`REDACTED`. Control
    and format characters, lone surrogates and the Unicode line and paragraph
    separators are written as ``\\uXXXX`` escapes, so the result holds no
    line break and no terminal escape sequence. A preview over *limit*
    characters keeps its first *limit* and ends with a note giving its full
    length.

    Args:
        arguments: The raw payload, as :attr:`~omicsclaw.schema.ToolCall.
            arguments` carries it.
        limit: Characters of preview kept before the truncation note.

    Returns:
        ``""`` for a blank payload or an empty JSON object; a note giving the
        payload's length, and none of its content, when it cannot be read as
        JSON; the preview otherwise.

    Raises:
        ValueError: *limit* is not a positive integer.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError(f"limit must be a positive integer, not {limit!r}")
    if not arguments.strip():
        return ""
    try:
        decoded = json.loads(arguments)
        if decoded == {}:
            return ""
        text = json.dumps(
            redact_credentials(decoded), sort_keys=True, ensure_ascii=False
        )
    except (ValueError, RecursionError):
        return (
            f"(not shown: {len(arguments)} characters that could not be read "
            "as JSON)"
        )
    return _bounded(escape_unsafe(text), limit)


def redact_credentials(value: Any) -> Any:
    """*value* with every credential-named key's value replaced.

    Walks decoded JSON: at any depth, the value under a mapping key
    :func:`is_credential_key` accepts becomes :data:`REDACTED`. Lists are
    walked, and every other value is returned as it is.

    Args:
        value: A decoded JSON value.

    Returns:
        A copy of *value* with those values replaced; *value* is not
        changed.
    """
    if isinstance(value, dict):
        return {
            key: REDACTED if is_credential_key(key) else redact_credentials(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [redact_credentials(child) for child in value]
    return value


def escape_unsafe(text: str, *, keep: str = "") -> str:
    """*text* with every unsafe character written as a ``\\uXXXX`` escape.

    Unsafe means a control or format character, a lone surrogate, or a
    Unicode line or paragraph separator. Written out, none can move a
    cursor, change a colour, reorder the text around it or end a line, and
    none makes a strict UTF-8 encoder raise. A character above the BMP is
    written as its surrogate pair, as JSON writes it.

    Args:
        text: The text to make inert.
        keep: Characters left as they are even when unsafe, for a display
            that shows them itself (``"\\n"`` for one that keeps line
            breaks).

    Returns:
        *text*, unchanged when it holds nothing unsafe outside *keep*.
    """
    if text.isprintable():
        return text
    return "".join(
        _escape(char)
        if not char.isprintable()
        and char not in keep
        and unicodedata.category(char) in _UNSAFE_CATEGORIES
        else char
        for char in text
    )


def _escape(char: str) -> str:
    """``\\uXXXX`` for *char*, as a surrogate pair above the BMP."""
    point = ord(char)
    if point <= 0xFFFF:
        return f"\\u{point:04x}"
    point -= 0x10000
    return f"\\u{0xD800 + (point >> 10):04x}\\u{0xDC00 + (point & 0x3FF):04x}"


def _bounded(text: str, limit: int) -> str:
    """*text*, or its first *limit* characters and a note of its length."""
    if len(text) <= limit:
        return text
    return (
        f"{text[:limit]} … [truncated: showing the first {limit} of "
        f"{len(text)} characters]"
    )
