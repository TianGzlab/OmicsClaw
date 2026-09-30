"""Shared fixtures for the skill environment tests."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
FIXTURE_SKILLS = FIXTURES / "skills"
REAL_REGISTRY = REPO / "skills" / "_sdk" / "deps.py"
