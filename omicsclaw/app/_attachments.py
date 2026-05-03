"""Chat attachment handling for the desktop-app server.

The legacy ``_build_multimodal_content`` in ``server.py`` blindly UTF-8
decoded every non-image attachment and inlined it into the user message.
For PDFs and other binaries that produced replacement-character garbage
that the model could not interpret, leading to the "let me try another
way to find this file" failure loop.

This module replaces that flow with the same pattern the Telegram and
Feishu bot channels already use:

* save the file to disk under an ``.uploads`` directory,
* fire a caller-supplied callback with the saved metadata so the caller
  can register the file in ``bot.core.received_files`` (or its
  per-surface equivalent),
* inline only obviously text-like content (with a size cap),
* otherwise emit a structured ``[Attached file: <abs-path> (<mime>)]``
  reference in the user message so the model knows where the file lives
  and can use existing tools (``parse_literature``, ``omicsclaw`` skill
  runner, generic file readers) to open it.

Pure helpers — no fastapi or openai imports — so the unit tests can run
without the desktop-app stack.
"""

from __future__ import annotations

import base64
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# Inline cap for text-like attachments. Larger files become path references
# so the prompt size stays bounded.
INLINE_TEXT_MAX_BYTES = 50_000

# Known text-ish ``application/*`` MIMEs. Anything starting with ``text/``
# is also treated as text-like.
_TEXT_LIKE_APPLICATION_MIMES: frozenset[str] = frozenset(
    {
        "application/json",
        "application/xml",
        "application/yaml",
        "application/x-yaml",
        "application/toml",
        "application/x-toml",
        "application/javascript",
        "application/x-shellscript",
        "application/x-python",
    }
)


def is_text_like_mime(mime: str) -> bool:
    """Best-effort MIME → "is this safe to inline as text?" decision."""
    if not isinstance(mime, str):
        return False
    lowered = mime.strip().lower()
    if lowered.startswith("text/"):
        return True
    return lowered in _TEXT_LIKE_APPLICATION_MIMES


_UNSAFE_FILENAME_CHARS = re.compile(r"[^a-zA-Z0-9._-]")


def safe_attachment_filename(name: str) -> str:
    """Return ``name`` reduced to a safe basename component.

    Strips path separators, collapses unsafe chars to ``_``, and never
    returns an empty string. Mirrors ``bot.core.sanitize_filename`` but
    is duplicated here to keep this module dependency-free.
    """
    if not isinstance(name, str):
        name = ""
    base = Path(name).name.strip()
    base = base.replace("..", "")
    base = _UNSAFE_FILENAME_CHARS.sub("_", base)
    base = base.strip("._")
    return base or "unnamed_file"


def save_attachment_to_disk(file_dict: dict, target_dir: Path) -> Optional[Path]:
    """Decode ``file_dict["data"]`` (base64) and save under ``target_dir``.

    Returns the saved ``Path`` on success, ``None`` on any failure
    (invalid base64, IO error, missing data field). Never raises.
    """
    if not isinstance(file_dict, dict):
        return None
    raw_b64 = file_dict.get("data") or ""
    if not isinstance(raw_b64, str) or not raw_b64:
        return None
    try:
        payload = base64.b64decode(raw_b64, validate=True)
    except (ValueError, base64.binascii.Error):
        return None

    safe_name = safe_attachment_filename(str(file_dict.get("name", "") or ""))
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{int(time.time() * 1000)}-{safe_name}"
    try:
        path.write_bytes(payload)
    except OSError as exc:
        logger.warning("Failed to write attachment %s: %s", safe_name, exc)
        return None
    return path


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------


def _format_attached_block(*, abs_path: Path, name: str, mime: str, size: int) -> str:
    return (
        f"[Attached file: {abs_path} "
        f"(name=\"{name}\", type=\"{mime}\", size={size} bytes). "
        "Use your file-reading tools (e.g. `parse_literature` for PDFs, "
        "`inspect_file` for plain text, or `omicsclaw` skill mode='file') "
        "to access it.]"
    )


def _try_inline_text(file_dict: dict, *, payload: bytes) -> Optional[str]:
    name = file_dict.get("name", "file")
    if len(payload) > INLINE_TEXT_MAX_BYTES:
        return None
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return f"### File: {name}\n```\n{text}\n```"


def build_chat_content(
    text: str,
    files: list[dict],
    *,
    uploads_dir: Path,
    on_file_saved: Optional[Callable[[dict], None]] = None,
) -> Any:
    """Build the OpenAI-compatible user-message content for a chat turn.

    Returns either a plain ``str`` (when no images are attached) or a
    ``list[dict]`` of OpenAI multimodal blocks (when one or more images
    are attached).

    For each attached file:

    * ``image/*`` → emitted as an ``image_url`` data-URI block, AND
      saved to disk (mirrors the Telegram path so vision tools can also
      see the local copy).
    * Text-like MIME with payload ≤ ``INLINE_TEXT_MAX_BYTES`` → inlined
      into the text body inside a fenced block.
    * Anything else (PDF, archive, oversize text, unknown binary) →
      saved to disk and referenced by absolute path in the text body.

    For every file that lands on disk, ``on_file_saved`` (if provided)
    is invoked once with ``{"path": str, "filename": str, "mime": str,
    "size": int, "is_image": bool}``.
    """
    image_parts: list[dict] = []
    text_addendum: list[str] = []

    files = list(files or [])
    for f in files:
        if not isinstance(f, dict):
            continue

        name = str(f.get("name", "") or "file")
        mime = str(f.get("type", "") or "application/octet-stream")
        raw_b64 = f.get("data") or ""
        if not isinstance(raw_b64, str):
            raw_b64 = ""

        # Decode once for size/text checks; keep the original base64 for
        # multimodal data URIs so we don't recompute.
        try:
            payload = base64.b64decode(raw_b64, validate=True) if raw_b64 else b""
        except (ValueError, base64.binascii.Error):
            payload = b""

        size = int(f.get("size", 0) or len(payload) or 0)

        if mime.startswith("image/"):
            saved = save_attachment_to_disk(f, uploads_dir)
            image_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{raw_b64}"},
                }
            )
            if saved is not None and on_file_saved is not None:
                on_file_saved(
                    {
                        "path": str(saved),
                        "filename": name,
                        "mime": mime,
                        "size": size,
                        "is_image": True,
                    }
                )
            continue

        # Try inlining text-like content first.
        if is_text_like_mime(mime) and payload:
            inlined = _try_inline_text(f, payload=payload)
            if inlined is not None:
                text_addendum.append(inlined)
                continue

        # Anything else (binary, oversize, undecodable) → save + reference.
        saved = save_attachment_to_disk(f, uploads_dir)
        if saved is None:
            text_addendum.append(
                f"[Attached file: {name} (type={mime}, {size} bytes) — "
                "could not be saved on the server. Ask the user to retry.]"
            )
            continue
        text_addendum.append(
            _format_attached_block(
                abs_path=saved,
                name=name,
                mime=mime,
                size=size,
            )
        )
        if on_file_saved is not None:
            on_file_saved(
                {
                    "path": str(saved),
                    "filename": name,
                    "mime": mime,
                    "size": size,
                    "is_image": False,
                }
            )

    full_text = text or ""
    if text_addendum:
        joined_addendum = "\n\n".join(text_addendum)
        full_text = f"{full_text}\n\n{joined_addendum}" if full_text else joined_addendum

    if image_parts:
        return [{"type": "text", "text": full_text}] + image_parts
    return full_text


__all__ = [
    "INLINE_TEXT_MAX_BYTES",
    "build_chat_content",
    "is_text_like_mime",
    "safe_attachment_filename",
    "save_attachment_to_disk",
]
