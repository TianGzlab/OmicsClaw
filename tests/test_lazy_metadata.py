from pathlib import Path
from omicsclaw.core.lazy_metadata import LazySkillMetadata

def test_lazy_metadata_loads_basic_info():
    skill_path = Path("skills/spatial/spatial-preprocess")
    lazy = LazySkillMetadata(skill_path)

    assert lazy.name == "spatial-preprocess"
    assert "Load raw spatial transcriptomics data" in lazy.description
    assert lazy.domain == "spatial"

def test_lazy_metadata_loads_full_on_demand():
    skill_path = Path("skills/spatial/spatial-preprocess")
    lazy = LazySkillMetadata(skill_path)

    # Basic info loaded immediately
    assert lazy.name == "spatial-preprocess"

    # Full metadata loaded on-demand
    full = lazy.get_full()
    assert "tags" in full
    assert "version" in full
    assert full["version"] == "0.4.0"


def test_lazy_metadata_loads_param_hints():
    skill_path = Path("skills/spatial/spatial-genes")
    lazy = LazySkillMetadata(skill_path)

    hints = lazy.param_hints
    assert isinstance(hints, dict)
    assert "morans" in hints
    assert "sparkx" in hints
    assert "morans_n_neighs" in hints["morans"]["params"]
    assert "sparkx_option" in hints["sparkx"]["params"]


def test_lazy_metadata_loads_method_specific_flags():
    skill_path = Path("skills/spatial/spatial-genes")
    lazy = LazySkillMetadata(skill_path)

    flags = lazy.allowed_extra_flags
    assert "--morans-n-neighs" in flags
    assert "--spatialde-no-aeh" in flags
    assert "--sparkx-option" in flags
    assert "--flashs-n-rand-features" in flags
