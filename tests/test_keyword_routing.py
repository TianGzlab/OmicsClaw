"""Tests for SKILL.md-driven keyword routing.

Validates that trigger_keywords from SKILL.md files are correctly
extracted by LazySkillMetadata and assembled into keyword maps
by OmicsRegistry.build_keyword_map().
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from omicsclaw.core.lazy_metadata import LazySkillMetadata
from omicsclaw.core.registry import OmicsRegistry, SKILLS_DIR


# ---------------------------------------------------------------------------
# LazySkillMetadata.trigger_keywords
# ---------------------------------------------------------------------------


def test_trigger_keywords_property():
    """SKILL.md trigger_keywords are parsed into a list."""
    skill_path = SKILLS_DIR / "spatial" / "spatial-preprocess"
    lazy = LazySkillMetadata(skill_path)
    kws = lazy.trigger_keywords
    assert isinstance(kws, list)
    assert len(kws) > 0
    # At least "preprocess" should be present (case-insensitive check)
    lower_kws = [k.lower() for k in kws]
    assert any("preprocess" in k for k in lower_kws)


def test_trigger_keywords_missing_graceful():
    """A skill dir without SKILL.md returns empty trigger_keywords."""
    lazy = LazySkillMetadata(Path("/tmp/nonexistent-skill"))
    assert lazy.trigger_keywords == []


# ---------------------------------------------------------------------------
# OmicsRegistry.build_keyword_map
# ---------------------------------------------------------------------------


def test_build_keyword_map_spatial():
    """Spatial domain keyword map contains entries from SKILL.md files."""
    reg = OmicsRegistry()
    kw_map = reg.build_keyword_map(domain="spatial")
    assert len(kw_map) > 0
    # "preprocess" should route to a spatial skill
    assert "preprocess" in kw_map


def test_build_keyword_map_singlecell():
    """Single-cell domain keyword map includes sc-* skills."""
    reg = OmicsRegistry()
    kw_map = reg.build_keyword_map(domain="singlecell")
    assert len(kw_map) > 0
    # Check that at least one sc skill is present in values
    sc_skills = [v for v in kw_map.values() if v.startswith("sc-")]
    assert len(sc_skills) > 0


def test_build_keyword_map_all_domains():
    """Without domain filter, all domains contribute keywords."""
    reg = OmicsRegistry()
    kw_map = reg.build_keyword_map()
    assert len(kw_map) > 20


def test_build_keyword_map_with_fallback():
    """Fallback keywords are included in the built map."""
    reg = OmicsRegistry()
    fallback = {"exotic test keyword": "some-test-skill"}
    kw_map = reg.build_keyword_map(domain="spatial", fallback_map=fallback)
    assert "exotic test keyword" in kw_map
    assert kw_map["exotic test keyword"] == "some-test-skill"


def test_skill_md_keywords_override_fallback():
    """SKILL.md keywords take priority over fallback entries."""
    reg = OmicsRegistry()
    # "preprocess" is defined in spatial-preprocess/SKILL.md, so it should
    # override this fallback that points to a wrong skill
    fallback = {"preprocess": "wrong-skill"}
    kw_map = reg.build_keyword_map(domain="spatial", fallback_map=fallback)
    assert kw_map["preprocess"] != "wrong-skill"


def test_keywords_are_lowercased():
    """All keyword map keys should be lowercase."""
    reg = OmicsRegistry()
    kw_map = reg.build_keyword_map()
    for key in kw_map:
        assert key == key.lower(), f"Keyword '{key}' is not lowercase"


# ---------------------------------------------------------------------------
# Alias resolution
# ---------------------------------------------------------------------------


def test_resolve_alias():
    """Directory names like 'spatial-preprocess' resolve to canonical skill names."""
    reg = OmicsRegistry()
    reg.load_all()
    # spatial-preprocess dir -> spatial-preprocess canonical name
    alias = reg._resolve_alias("spatial-preprocess")
    assert alias == "spatial-preprocess"


def test_resolve_alias_identity():
    """Unknown directory names fall through as-is."""
    reg = OmicsRegistry()
    alias = reg._resolve_alias("nonexistent-skill-xyz")
    assert alias == "nonexistent-skill-xyz"


# ---------------------------------------------------------------------------
# SKILL.md-first loading (Issue #2)
# ---------------------------------------------------------------------------


def test_allowed_extra_flags_from_skill_md():
    """allowed_extra_flags are parsed from SKILL.md frontmatter."""
    skill_path = SKILLS_DIR / "spatial" / "spatial-preprocess"
    lazy = LazySkillMetadata(skill_path)
    flags = lazy.allowed_extra_flags
    assert isinstance(flags, set)
    assert "--species" in flags
    assert "--min-genes" in flags
    assert "--tissue" in flags
    assert "--resolutions" in flags


def test_legacy_aliases_from_skill_md():
    """legacy_aliases are parsed from SKILL.md frontmatter."""
    skill_path = SKILLS_DIR / "spatial" / "spatial-preprocess"
    lazy = LazySkillMetadata(skill_path)
    aliases = lazy.legacy_aliases
    assert isinstance(aliases, list)
    assert "preprocess" in aliases


def test_saves_h5ad_from_skill_md():
    """saves_h5ad boolean is parsed from SKILL.md frontmatter."""
    skill_path = SKILLS_DIR / "spatial" / "spatial-preprocess"
    lazy = LazySkillMetadata(skill_path)
    assert lazy.saves_h5ad is True


def test_requires_preprocessed_from_skill_md():
    """requires_preprocessed boolean is parsed from SKILL.md frontmatter."""
    skill_path = SKILLS_DIR / "spatial" / "spatial-de"
    lazy = LazySkillMetadata(skill_path)
    assert lazy.requires_preprocessed is True


def test_load_all_uses_skill_md_flags():
    """load_all() should populate allowed_extra_flags from SKILL.md."""
    reg = OmicsRegistry()
    reg.load_all()
    info = reg.skills.get("spatial-preprocess")
    assert info is not None
    flags = info.get("allowed_extra_flags", set())
    assert "--species" in flags
    assert "--min-genes" in flags


def test_load_all_registers_legacy_aliases():
    """load_all() should register legacy_aliases as lookup keys."""
    reg = OmicsRegistry()
    reg.load_all()
    # "preprocess" is a legacy alias for spatial-preprocess
    assert "preprocess" in reg.skills
    assert reg.skills["preprocess"]["alias"] == "spatial-preprocess"
    assert "spatial-preprocessing" in reg.skills
    assert reg.skills["spatial-preprocessing"]["alias"] == "spatial-preprocess"


def test_load_all_uses_skill_md_param_hints():
    """load_all() should populate method-specific param_hints from SKILL.md."""
    reg = OmicsRegistry()
    reg.load_all()
    info = reg.skills.get("spatial-genes")
    assert info is not None
    hints = info.get("param_hints", {})
    assert "morans" in hints
    assert "morans_n_neighs" in hints["morans"]["params"]


def test_load_all_uses_spatial_preprocess_param_hints():
    """load_all() should populate preprocess param_hints from SKILL.md."""
    reg = OmicsRegistry()
    reg.load_all()
    info = reg.skills.get("spatial-preprocess")
    assert info is not None
    hints = info.get("param_hints", {})
    assert "scanpy_standard" in hints
    assert "tissue" in hints["scanpy_standard"]["params"]
    assert "leiden_resolution" in hints["scanpy_standard"]["params"]


def test_load_all_uses_spatial_integration_param_hints():
    """load_all() should populate spatial integration method hints from SKILL.md."""
    reg = OmicsRegistry()
    reg.load_all()
    info = reg.skills.get("spatial-integrate")
    assert info is not None
    hints = info.get("param_hints", {})
    assert "harmony" in hints
    assert "bbknn" in hints
    assert "scanorama" in hints
    assert "harmony_theta" in hints["harmony"]["params"]
    assert "scanorama_batch_size" in hints["scanorama"]["params"]


def test_load_all_uses_spatial_communication_param_hints():
    """load_all() should populate spatial communication method hints from SKILL.md."""
    reg = OmicsRegistry()
    reg.load_all()
    info = reg.skills.get("spatial-communication")
    assert info is not None
    hints = info.get("param_hints", {})
    assert "liana" in hints
    assert "cellphonedb" in hints
    assert "fastccc" in hints
    assert "cellchat_r" in hints
    assert "liana_expr_prop" in hints["liana"]["params"]
    assert "cellchat_prob_type" in hints["cellchat_r"]["params"]


def test_load_all_uses_spatial_deconv_param_hints():
    """load_all() should populate spatial deconvolution method hints from SKILL.md."""
    reg = OmicsRegistry()
    reg.load_all()
    info = reg.skills.get("spatial-deconv")
    assert info is not None
    hints = info.get("param_hints", {})
    assert "cell2location" in hints
    assert "rctd" in hints
    assert "tangram" in hints
    assert "spotlight" in hints
    assert "cell2location_n_cells_per_spot" in hints["cell2location"]["params"]
    assert "spotlight_weight_id" in hints["spotlight"]["params"]


def test_load_all_uses_spatial_register_param_hints():
    """load_all() should populate spatial registration method hints from SKILL.md."""
    reg = OmicsRegistry()
    reg.load_all()
    info = reg.skills.get("spatial-register")
    assert info is not None
    hints = info.get("param_hints", {})
    assert "paste" in hints
    assert "stalign" in hints
    assert "paste_alpha" in hints["paste"]["params"]
    assert "stalign_a" in hints["stalign"]["params"]


def test_load_all_uses_spatial_trajectory_param_hints():
    """load_all() should populate spatial trajectory method hints from SKILL.md."""
    reg = OmicsRegistry()
    reg.load_all()
    info = reg.skills.get("spatial-trajectory")
    assert info is not None
    hints = info.get("param_hints", {})
    assert "dpt" in hints
    assert "cellrank" in hints
    assert "palantir" in hints
    assert "dpt_n_dcs" in hints["dpt"]["params"]
    assert "cellrank_frac_to_keep" in hints["cellrank"]["params"]
    assert "palantir_num_waypoints" in hints["palantir"]["params"]


def test_spatial_communication_keywords_route_to_alias():
    """Communication trigger keywords should resolve to the canonical skill name."""
    reg = OmicsRegistry()
    kw_map = reg.build_keyword_map(domain="spatial")
    assert kw_map["ligand receptor"] == "spatial-communication"


def test_spatial_deconv_keywords_route_to_alias():
    """Deconvolution trigger keywords should resolve to the canonical skill name."""
    reg = OmicsRegistry()
    kw_map = reg.build_keyword_map(domain="spatial")
    assert kw_map["cell type deconvolution"] == "spatial-deconv"


def test_spatial_register_keywords_route_to_alias():
    """Registration trigger keywords should resolve to the canonical skill name."""
    reg = OmicsRegistry()
    kw_map = reg.build_keyword_map(domain="spatial")
    assert kw_map["slice alignment"] == "spatial-register"


def test_spatial_trajectory_keywords_route_to_alias():
    """Trajectory trigger keywords should resolve to the registry alias."""
    reg = OmicsRegistry()
    kw_map = reg.build_keyword_map(domain="spatial")
    assert kw_map["pseudotime"] == "spatial-trajectory"
