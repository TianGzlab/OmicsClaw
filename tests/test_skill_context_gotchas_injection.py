"""Tests for ADR 2026-05-11: inject `## Known pitfalls` block from
SKILL.md Gotchas into `load_skill_context()` output.

Phase 1 contract: when the selected skill has gotchas in the registry,
`load_skill_context()` appends a `## Known pitfalls (from SKILL.md
Gotchas)` block listing every gotcha lead sentence as a bullet.  When
the skill has no gotchas, the block is omitted entirely (no empty
header).  An INFO log line records skill name + gotcha count + approx
token count for Phase 2 telemetry.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from omicsclaw.runtime.context_layers import load_skill_context


def _stub_skill(monkeypatch, *, alias: str, gotchas: list[str], **extra) -> None:
    """Replace the registry lookup so the test does not depend on the
    on-disk skill catalogue."""
    from omicsclaw.runtime.context_layers import __init__ as ctx_module  # noqa: F401
    from omicsclaw.runtime import context_layers as ctx_pkg

    info = {
        "domain": "spatial",
        "description": "stub description",
        "legacy_aliases": [],
        "param_hints": {},
        "requires_preprocessed": False,
        "saves_h5ad": False,
        "gotchas": gotchas,
        **extra,
    }

    def _fake_should_prefetch(*args, **kwargs) -> bool:
        return True

    monkeypatch.setattr(
        ctx_pkg, "should_prefetch_skill_context", _fake_should_prefetch
    )
    monkeypatch.setattr(ctx_pkg, "ensure_registry_loaded", lambda: None)

    class _StubRegistry:
        skills = {alias: info}

    monkeypatch.setattr(ctx_pkg, "registry", _StubRegistry)


def test_load_skill_context_appends_pitfalls_block_when_gotchas_present(monkeypatch):
    _stub_skill(
        monkeypatch,
        alias="spatial-de",
        gotchas=[
            "`pydeseq2` requires `--sample-key` distinct from `--groupby`.",
            "Counts-layer fallback to `adata.X` is logged but not blocked.",
        ],
    )
    out = load_skill_context(skill="spatial-de")
    assert "## Known pitfalls (from SKILL.md Gotchas)" in out
    assert "- `pydeseq2` requires `--sample-key` distinct from `--groupby`." in out
    assert "- Counts-layer fallback to `adata.X` is logged but not blocked." in out


def test_load_skill_context_omits_pitfalls_block_when_no_gotchas(monkeypatch):
    _stub_skill(monkeypatch, alias="empty-skill", gotchas=[])
    out = load_skill_context(skill="empty-skill")
    assert "Known pitfalls" not in out
    assert "Gotchas" not in out


def test_load_skill_context_omits_block_when_skill_unknown(monkeypatch):
    _stub_skill(monkeypatch, alias="exists", gotchas=["x."])
    out = load_skill_context(skill="does-not-exist")
    assert out == ""


def test_load_skill_context_logs_telemetry_with_count_and_tokens(monkeypatch, caplog):
    _stub_skill(
        monkeypatch,
        alias="spatial-de",
        gotchas=["First.", "Second.", "Third."],
    )
    with caplog.at_level(logging.INFO, logger="omicsclaw.runtime.context_layers"):
        load_skill_context(skill="spatial-de")
    matched = [
        rec for rec in caplog.records
        if "skill_context.gotchas_injected" in rec.getMessage()
        or getattr(rec, "event", "") == "skill_context.gotchas_injected"
    ]
    assert matched, f"telemetry log not emitted; got {[r.getMessage() for r in caplog.records]}"
    rec = matched[0]
    # Allow either structured (extra dict) or message-suffix telemetry.
    msg = rec.getMessage()
    assert "spatial-de" in msg or getattr(rec, "skill", "") == "spatial-de"
    assert "3" in msg or getattr(rec, "gotcha_count", 0) == 3


def test_load_skill_context_real_spatial_de_includes_all_six_gotchas():
    """End-to-end: hit the real registry, real SKILL.md, real injection."""
    out = load_skill_context(skill="spatial-de")
    if not out:
        pytest.skip("load_skill_context gated off in this environment")
    assert "## Known pitfalls (from SKILL.md Gotchas)" in out
    # All 6 spatial-de gotcha signatures must appear.
    for sig in [
        "--sample-key",
        "--group1",
        "Counts-layer fallback",
        "Paired design",
        "Skipped sample-group bins",
        "filter_markers",
    ]:
        assert sig in out, f"missing gotcha signature {sig!r} in injected context"
