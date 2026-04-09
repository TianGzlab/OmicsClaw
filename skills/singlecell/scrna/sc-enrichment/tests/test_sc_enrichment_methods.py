"""Static method-contract tests for sc-enrichment."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "sc_enrichment.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("sc_enrichment", SKILL_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_methods_are_registered():
    module = _load_module()
    assert set(module.METHOD_REGISTRY) == {"ora", "gsea"}
