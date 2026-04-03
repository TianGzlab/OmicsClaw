import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from omicsclaw.core.registry import registry

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
    assert "spatial" in registry.domains
    assert registry.domains["singlecell"]["skill_count"] == 14
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
    assert len(registry.skills) > 0
    assert len(registry.domains) > 0
