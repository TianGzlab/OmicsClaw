from pathlib import Path
from omicsclaw.core.lazy_metadata import LazySkillMetadata

def test_lazy_metadata_loads_basic_info():
    skill_path = Path("skills/spatial/spatial-preprocess")
    lazy = LazySkillMetadata(skill_path)

    assert lazy.name == "spatial-preprocess"
    assert "Load spatial transcriptomics data" in lazy.description
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
    assert full["version"] == "0.3.0"
