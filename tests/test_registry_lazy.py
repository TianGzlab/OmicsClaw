from omicsclaw.core.registry import OmicsRegistry

def test_registry_load_lightweight():
    registry = OmicsRegistry()
    registry.load_lightweight()

    assert len(registry.lazy_skills) > 0
    assert "spatial-preprocess" in registry.lazy_skills

    # Should have basic info
    preprocess = registry.lazy_skills["spatial-preprocess"]
    assert preprocess.name == "spatial-preprocess"
    assert len(preprocess.description) > 0

    # Verify singlecell subdomain nesting is discovered
    assert "sc-qc" in registry.lazy_skills
