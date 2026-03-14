from omicsclaw.core.registry import OmicsRegistry

def test_registry_load_lightweight():
    registry = OmicsRegistry()
    registry.load_lightweight()

    assert len(registry.lazy_skills) > 0
    assert "preprocess" in registry.lazy_skills

    # Should have basic info
    preprocess = registry.lazy_skills["preprocess"]
    assert preprocess.name == "spatial-preprocess"
    assert len(preprocess.description) > 0
