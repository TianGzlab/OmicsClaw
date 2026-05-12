from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "generate_orchestrator_counts.py"


def _load_generator_module():
    spec = importlib.util.spec_from_file_location("generate_orchestrator_counts_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_orchestrator_count_generator_includes_literature_domain():
    generator = _load_generator_module()

    blocks = generator.render_blocks()

    assert "89 skills in 8 domains" in blocks["intro"]
    assert "89 skills across 8 domains" in blocks["domains"]
    assert "**Literature** (1 skills)" in blocks["domains"]
    assert "All 89 skills across 8 domains" in blocks["footer"]
