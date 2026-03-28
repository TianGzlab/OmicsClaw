"""Focused tests for spatial communication demo data preparation."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_skill_module():
    skill_script = Path(__file__).resolve().parent.parent / "spatial_communication.py"
    spec = importlib.util.spec_from_file_location("spatial_communication", skill_script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_demo_data_renames_raw_var_names_for_liana():
    """Demo data should expose real-looking gene symbols in both X and raw."""
    module = _load_skill_module()

    adata, _ = module.get_demo_data()

    assert adata.raw is not None
    assert list(adata.var_names[:5]) == ["A1BG", "A2M", "AANAT", "ABCA1", "ACE"]
    assert list(adata.raw.var_names[:5]) == ["A1BG", "A2M", "AANAT", "ABCA1", "ACE"]
    assert all("_" not in gene for gene in adata.raw.var_names)
