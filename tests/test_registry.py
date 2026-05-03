import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from omicsclaw.core.registry import registry


def test_registry_import_does_not_require_package_file():
    """App-server startup must not crash if omicsclaw is a namespace package."""
    code = """
import importlib
import omicsclaw

omicsclaw.__file__ = None
registry = importlib.import_module("omicsclaw.core.registry")
assert registry.OMICSCLAW_DIR.name == "OmicsClaw"
assert registry.SKILLS_DIR.name == "skills"
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

def test_registry_loaded():
    registry.load_all()
    assert "spatial-preprocessing" in registry.skills
    assert "spatial-preprocess" in registry.skills
    assert registry.skills["spatial-preprocessing"]["alias"] == "spatial-preprocess"
    assert "spatial-orchestrator" not in registry.skills
    assert "orchestrator" in registry.skills
    assert registry.skills["orchestrator"]["domain"] == "orchestrator"
    assert Path(registry.skills["orchestrator"]["script"]).name == "omics_orchestrator.py"
    assert "sc-qc" in registry.skills  # verify singlecell subdomain nesting
    assert "spatial-microenvironment-subset" in registry.skills
    assert "spatial-raw-processing" in registry.skills
    assert "st_pipeline" in [
        keyword.lower()
        for keyword in registry.skills["spatial-raw-processing"].get("trigger_keywords", [])
    ]
    assert "spatial" in registry.domains
    assert registry.domains["singlecell"]["skill_count"] == len(
        registry.iter_primary_skills(domain="singlecell")
    )
    for skill in [
        "sc-standardize-input",
        "sc-qc",
        "sc-preprocessing",
        "sc-filter",
        "sc-ambient-removal",
        "sc-doublet-detection",
        "sc-cell-annotation",
        "sc-pseudotime",
        "sc-velocity",
        "sc-batch-integration",
        "sc-de",
        "sc-markers",
        "sc-grn",
        "sc-cell-communication",
    ]:
        assert skill in registry.skills
    assert registry.domains["spatial"]["skill_count"] == len(
        registry.iter_primary_skills(domain="spatial")
    )
    assert len(registry.skills) > 0
    assert len(registry.domains) > 0
