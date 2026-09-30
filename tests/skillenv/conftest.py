"""Shared fixtures for the skill environment tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from omicsclaw.entry import ensemble

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
FIXTURE_SKILLS = FIXTURES / "skills"
REAL_REGISTRY = REPO / "skills" / "_sdk" / "deps.py"


@pytest.fixture(autouse=True)
def fixed_host_memory(monkeypatch):
    """Size the ensemble pool from a 256 GiB host rather than this machine,
    whose memory may leave the pool nothing after the 64 GB reserve."""
    monkeypatch.setattr(ensemble, "mem_total_gib", lambda: 256.0)
