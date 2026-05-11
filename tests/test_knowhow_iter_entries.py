"""Tests for ``KnowHowInjector.iter_entries`` — KH bootstrap source.

Phase 1.2 of the KH-to-graph bootstrap. The ``init_db()`` hook iterates
this generator and seeds each ``(uri, content)`` pair into the
``__shared__`` namespace via ``MemoryEngine.seed_shared``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omicsclaw.knowledge.knowhow import KnowHowInjector


def _write_kh(dir_: Path, filename: str, body: str) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / filename).write_text(body, encoding="utf-8")


def test_iter_entries_yields_uri_and_full_content(tmp_path):
    kh_dir = tmp_path / "knowhows"
    _write_kh(
        kh_dir,
        "KH-test-safety.md",
        "---\ndoc_id: test-safety\nrelated_skills: [__all__]\n---\n\nBody text.\n",
    )

    injector = KnowHowInjector(knowhows_dir=kh_dir)
    entries = list(injector.iter_entries())

    assert len(entries) == 1
    uri, content = entries[0]
    assert uri == "core://kh/test-safety"
    assert "Body text." in content
    assert content.startswith("---")  # frontmatter retained — same shape read_knowhow returns


def test_iter_entries_uri_uses_doc_id_from_frontmatter(tmp_path):
    kh_dir = tmp_path / "knowhows"
    _write_kh(
        kh_dir,
        "KH-arbitrary-filename.md",
        "---\ndoc_id: canonical-id\nrelated_skills: [foo]\n---\n\nBody.\n",
    )

    injector = KnowHowInjector(knowhows_dir=kh_dir)
    uris = [uri for uri, _ in injector.iter_entries()]

    # doc_id wins over filename stem so renaming the file later does not
    # invalidate the URI key stored in the graph.
    assert uris == ["core://kh/canonical-id"]


def test_iter_entries_falls_back_to_filename_stem_without_doc_id(tmp_path):
    kh_dir = tmp_path / "knowhows"
    _write_kh(
        kh_dir,
        "KH-no-frontmatter.md",
        "Just plain markdown without frontmatter.\n",
    )

    injector = KnowHowInjector(knowhows_dir=kh_dir)
    uris = [uri for uri, _ in injector.iter_entries()]

    assert uris == ["core://kh/KH-no-frontmatter"]


def test_iter_entries_empty_when_dir_missing(tmp_path):
    injector = KnowHowInjector(knowhows_dir=tmp_path / "does_not_exist")
    assert list(injector.iter_entries()) == []


def test_iter_entries_content_matches_read_knowhow(tmp_path):
    """Bootstrap must seed the same body that ``read_knowhow`` would
    return, so a future swap from filesystem-read to graph-read is
    transparent to callers."""
    kh_dir = tmp_path / "knowhows"
    body = (
        "---\ndoc_id: parity-check\nrelated_skills: [foo]\n---\n\n"
        "# Heading\n\nFull body.\n"
    )
    _write_kh(kh_dir, "KH-parity.md", body)

    injector = KnowHowInjector(knowhows_dir=kh_dir)
    entries = dict(injector.iter_entries())
    via_read = injector.read_knowhow("KH-parity.md")

    assert entries["core://kh/parity-check"] == via_read


def test_iter_entries_skips_non_kh_files(tmp_path):
    """Loader globs ``KH-*.md`` — non-matching files must not appear in
    the bootstrap stream."""
    kh_dir = tmp_path / "knowhows"
    _write_kh(kh_dir, "KH-real.md", "---\ndoc_id: real\n---\n\nBody.\n")
    _write_kh(kh_dir, "README.md", "Not a KH document.\n")
    _write_kh(kh_dir, "notes.txt", "Even less a KH document.\n")

    injector = KnowHowInjector(knowhows_dir=kh_dir)
    uris = [uri for uri, _ in injector.iter_entries()]

    assert uris == ["core://kh/real"]
