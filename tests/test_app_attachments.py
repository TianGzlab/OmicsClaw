"""Tests for desktop-app chat attachment handling.

Issue: dragging a PDF (or any binary) into the chat input previously
base64-decoded the bytes as UTF-8 and inlined the garbage into the user
message. The model couldn't read the file and would loop trying tool
calls to find it.

Fix mirrors the Telegram/Feishu pattern: save to disk, register the
absolute path so existing tools (parse_literature, omicsclaw skill
runner) can pick it up, and emit a structured `[Attached file: ...]`
reference in the user message instead of garbage text.
"""
from __future__ import annotations

import base64
from pathlib import Path

from omicsclaw.app._attachments import (
    build_chat_content,
    is_text_like_mime,
    safe_attachment_filename,
    save_attachment_to_disk,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestIsTextLikeMime:
    def test_text_prefix_is_text(self):
        assert is_text_like_mime("text/plain")
        assert is_text_like_mime("text/markdown")
        assert is_text_like_mime("text/csv")

    def test_known_application_text_types(self):
        assert is_text_like_mime("application/json")
        assert is_text_like_mime("application/xml")
        assert is_text_like_mime("application/x-yaml")

    def test_pdf_is_not_text(self):
        assert not is_text_like_mime("application/pdf")

    def test_binary_is_not_text(self):
        assert not is_text_like_mime("application/octet-stream")
        assert not is_text_like_mime("application/zip")
        assert not is_text_like_mime("image/png")


class TestSafeAttachmentFilename:
    def test_strips_path_traversal(self):
        assert safe_attachment_filename("../../etc/passwd") != "../../etc/passwd"
        assert "/" not in safe_attachment_filename("a/b/c.pdf")
        assert "\\" not in safe_attachment_filename("a\\b\\c.pdf")
        assert ".." not in safe_attachment_filename("..hidden.pdf")

    def test_keeps_safe_chars(self):
        assert safe_attachment_filename("My_Doc-1.PDF") == "My_Doc-1.PDF"

    def test_empty_falls_back(self):
        assert safe_attachment_filename("") != ""
        assert safe_attachment_filename("   ") != ""


# ---------------------------------------------------------------------------
# save_attachment_to_disk
# ---------------------------------------------------------------------------


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_save_attachment_writes_bytes_with_safe_name(tmp_path: Path):
    file_dict = {
        "name": "Garfield_BIB.pdf",
        "type": "application/pdf",
        "size": 123,
        "data": _b64(b"%PDF-1.4 binary..."),
    }
    saved = save_attachment_to_disk(file_dict, tmp_path)
    assert saved is not None
    assert saved.exists()
    assert saved.suffix == ".pdf"
    assert "Garfield_BIB" in saved.name
    assert saved.read_bytes() == b"%PDF-1.4 binary..."
    # Saved inside the requested target dir, not somewhere else.
    assert tmp_path in saved.parents


def test_save_attachment_returns_none_on_invalid_data(tmp_path: Path):
    file_dict = {"name": "broken.pdf", "type": "application/pdf", "data": "@@@not-base64"}
    saved = save_attachment_to_disk(file_dict, tmp_path)
    assert saved is None


# ---------------------------------------------------------------------------
# build_chat_content
# ---------------------------------------------------------------------------


def test_pdf_is_saved_and_path_is_referenced_not_inlined(tmp_path: Path):
    saved_calls: list[dict] = []

    def on_saved(meta: dict) -> None:
        saved_calls.append(meta)

    files = [
        {
            "name": "report.pdf",
            "type": "application/pdf",
            "size": 1024,
            "data": _b64(b"%PDF binary..."),
        }
    ]
    content = build_chat_content(
        "Parse this please",
        files,
        uploads_dir=tmp_path,
        on_file_saved=on_saved,
    )
    # Plain string content (no images), with a path reference embedded.
    assert isinstance(content, str)
    assert "[Attached file:" in content
    assert "report.pdf" in content
    assert "application/pdf" in content
    # Original user text preserved.
    assert "Parse this please" in content
    # Side effect: callback invoked with the saved metadata.
    assert len(saved_calls) == 1
    saved_path = Path(saved_calls[0]["path"])
    assert saved_path.exists()
    assert saved_calls[0]["filename"] == "report.pdf"
    assert saved_calls[0]["mime"] == "application/pdf"
    # And the absolute path appears in the prompt so the model can target it.
    assert str(saved_path) in content


def test_image_keeps_multimodal_block(tmp_path: Path):
    files = [
        {
            "name": "tissue.png",
            "type": "image/png",
            "size": 16,
            "data": _b64(b"\x89PNG\r\n\x1a\n_fake_png"),
        }
    ]
    content = build_chat_content(
        "Look at this tissue",
        files,
        uploads_dir=tmp_path,
    )
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert "Look at this tissue" in content[0]["text"]
    assert any(
        block.get("type") == "image_url"
        and "data:image/png;base64," in block["image_url"]["url"]
        for block in content
    )


def test_small_text_file_is_inlined(tmp_path: Path):
    files = [
        {
            "name": "config.json",
            "type": "application/json",
            "size": 24,
            "data": _b64(b'{"key": "value"}'),
        }
    ]
    content = build_chat_content("Read this config", files, uploads_dir=tmp_path)
    assert isinstance(content, str)
    # Inlined as fenced text — no path reference, since it's short and text.
    assert '{"key": "value"}' in content
    assert "[Attached file:" not in content


def test_oversize_text_file_falls_back_to_path_reference(tmp_path: Path):
    big_text = b"line\n" * 20_000  # ~100 KB
    files = [
        {
            "name": "huge.log",
            "type": "text/plain",
            "size": len(big_text),
            "data": _b64(big_text),
        }
    ]
    content = build_chat_content("Look at this log", files, uploads_dir=tmp_path)
    assert isinstance(content, str)
    assert "[Attached file:" in content
    # The full content is NOT inlined.
    assert content.count("line\n") < 5_000


def test_multiple_files_each_handled_correctly(tmp_path: Path):
    saved_calls: list[dict] = []

    def on_saved(meta: dict) -> None:
        saved_calls.append(meta)

    files = [
        {
            "name": "paper.pdf",
            "type": "application/pdf",
            "data": _b64(b"%PDF body"),
        },
        {
            "name": "notes.md",
            "type": "text/markdown",
            "data": _b64(b"# Notes\n- a\n- b"),
        },
        {
            "name": "fig.png",
            "type": "image/png",
            "data": _b64(b"\x89PNG_fake"),
        },
    ]
    content = build_chat_content("hi", files, uploads_dir=tmp_path, on_file_saved=on_saved)
    assert isinstance(content, list)  # because of the image
    text_block = content[0]["text"]
    # PDF: path-referenced
    assert "paper.pdf" in text_block
    assert "[Attached file:" in text_block
    # Markdown: inlined
    assert "# Notes" in text_block
    # Image: multimodal block emitted
    assert any(b.get("type") == "image_url" for b in content[1:])
    # Callback fires once for the PDF (non-image, saved).
    saved_names = [m["filename"] for m in saved_calls]
    assert "paper.pdf" in saved_names
    # Image is also saved (matches Telegram pattern: receivable by tools).
    assert "fig.png" in saved_names


def test_empty_text_with_only_files_still_emits_path_block(tmp_path: Path):
    files = [
        {
            "name": "data.bin",
            "type": "application/octet-stream",
            "data": _b64(b"\x00\x01\x02\x03"),
        }
    ]
    content = build_chat_content("", files, uploads_dir=tmp_path)
    assert isinstance(content, str)
    assert "[Attached file:" in content
    assert "data.bin" in content
