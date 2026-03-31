from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from omicsclaw.interactive import interactive as interactive_mod


def _make_fake_registry() -> SimpleNamespace:
    ready_script = Path(__file__)

    spatial = {
        "alias": "spatial-preprocess",
        "domain": "spatial",
        "description": "Spatial preprocessing",
        "script": ready_script,
    }
    sc_qc = {
        "alias": "sc-qc",
        "domain": "singlecell",
        "description": "Single-cell quality control",
        "script": ready_script,
    }
    sc_markers = {
        "alias": "sc-markers",
        "domain": "singlecell",
        "description": "Marker detection",
        "script": ready_script,
    }

    return SimpleNamespace(
        domains={
            "spatial": {"name": "Spatial"},
            "singlecell": {"name": "Single-Cell"},
        },
        skills={
            "spatial-preprocess": spatial,
            "spatial-qc": spatial,
            "sc-qc": sc_qc,
            "sc-markers": sc_markers,
        },
    )


def test_collect_skill_sections_filters_and_deduplicates(monkeypatch):
    monkeypatch.setattr(interactive_mod, "_get_skill_registry", _make_fake_registry)

    sections = interactive_mod._collect_skill_sections("single cell")

    assert [domain for domain, _, _ in sections] == ["singlecell"]
    aliases = [alias for _, _, items in sections for alias, _ in items]
    assert aliases == ["sc-markers", "sc-qc"]


def test_handle_skills_returns_prefill_after_selection(monkeypatch):
    monkeypatch.setattr(interactive_mod, "_resolve_domain_filter", lambda value: value)
    
    async def _fake_picker(value=None):
        return "sc-qc"

    monkeypatch.setattr(interactive_mod, "_pick_skill_interactive", _fake_picker)

    assert asyncio.run(interactive_mod._handle_skills("")) == "/run sc-qc "


def test_handle_skills_list_mode_keeps_plain_listing(monkeypatch):
    printed: list[str | None] = []

    monkeypatch.setattr(interactive_mod, "_resolve_domain_filter", lambda value: value)
    monkeypatch.setattr(interactive_mod, "_print_skills_list", lambda value=None: printed.append(value))
    async def _unexpected_picker(value=None):
        raise AssertionError("picker should not be called")

    monkeypatch.setattr(interactive_mod, "_pick_skill_interactive", _unexpected_picker)

    result = asyncio.run(interactive_mod._handle_skills("singlecell --list"))

    assert result is None
    assert printed == ["singlecell"]
