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
    """Directory names like 'spatial-preprocess' resolve to registry aliases."""
    reg = OmicsRegistry()
    reg.load_all()
    # spatial-preprocess dir -> spatial-preprocessing alias
    alias = reg._resolve_alias("spatial-preprocess")
    assert alias == "spatial-preprocessing"


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
    info = reg.skills.get("spatial-preprocessing")
    assert info is not None
    flags = info.get("allowed_extra_flags", set())
    assert "--species" in flags
    assert "--min-genes" in flags


def test_load_all_registers_legacy_aliases():
    """load_all() should register legacy_aliases as lookup keys."""
    reg = OmicsRegistry()
    reg.load_all()
    # "preprocess" is a legacy alias for spatial-preprocessing
    assert "preprocess" in reg.skills
    assert reg.skills["preprocess"]["alias"] == "spatial-preprocessing"
