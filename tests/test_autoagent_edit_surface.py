"""Tests for omicsclaw.autoagent.edit_surface."""

from __future__ import annotations

from pathlib import Path

import pytest

from omicsclaw.autoagent.edit_surface import (
    ALL_LEVELS,
    FROZEN_PATTERNS,
    LEVEL_1,
    LEVEL_2,
    LEVEL_3,
    LEVEL_4,
    EditLevel,
    EditSurface,
    build_sc_preprocessing_surface,
    build_spatial_domains_surface,
)


class TestEditLevel:
    def test_level1_matches_skill_md(self):
        assert LEVEL_1.matches("skills/singlecell/scrna/sc-preprocessing/SKILL.md")
        assert LEVEL_1.matches("skills/spatial/spatial-domains/SKILL.md")

    def test_level1_rejects_python(self):
        assert not LEVEL_1.matches("skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py")

    def test_level2_matches_skill_python(self):
        assert LEVEL_2.matches("skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py")
        assert LEVEL_2.matches("skills/singlecell/_lib/qc.py")

    def test_level3_matches_config(self):
        assert LEVEL_3.matches("omicsclaw/agents/config.yaml")
        assert LEVEL_3.matches("omicsclaw/agents/prompts.py")

    def test_level3_rejects_runtime(self):
        assert not LEVEL_3.matches("omicsclaw/runtime/context_assembler.py")

    def test_level4_matches_generated(self):
        assert LEVEL_4.matches("skills/generated/new_skill/new_skill.py")
        assert LEVEL_4.matches("skills/generated/new_skill/SKILL.md")


class TestEditSurface:
    def test_level1_only(self, tmp_path):
        surface = EditSurface(max_level=1, project_root=tmp_path)
        assert surface.is_editable("skills/singlecell/scrna/sc-preprocessing/SKILL.md")
        assert not surface.is_editable("skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py")
        assert not surface.is_editable("omicsclaw/agents/config.yaml")

    def test_level2_includes_level1(self, tmp_path):
        surface = EditSurface(max_level=2, project_root=tmp_path)
        assert surface.is_editable("skills/singlecell/scrna/sc-preprocessing/SKILL.md")
        assert surface.is_editable("skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py")
        assert not surface.is_editable("omicsclaw/agents/config.yaml")

    def test_level3_includes_lower(self, tmp_path):
        surface = EditSurface(max_level=3, project_root=tmp_path)
        assert surface.is_editable("skills/singlecell/scrna/sc-preprocessing/SKILL.md")
        assert surface.is_editable("skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py")
        assert surface.is_editable("omicsclaw/agents/config.yaml")

    def test_frozen_always_rejected(self, tmp_path):
        # Even at max level, frozen files are rejected
        surface = EditSurface(max_level=4, project_root=tmp_path)
        assert not surface.is_editable("omicsclaw/runtime/context_assembler.py")
        assert not surface.is_editable("omicsclaw/routing/router.py")
        assert not surface.is_editable("omicsclaw/autoagent/judge.py")
        assert not surface.is_editable("omicsclaw/core/registry.py")
        assert not surface.is_editable("omicsclaw.py")

    def test_explicit_files_override_levels(self, tmp_path):
        surface = EditSurface(
            max_level=4,
            project_root=tmp_path,
            explicit_files=["skills/singlecell/_lib/qc.py"],
        )
        assert surface.is_editable("skills/singlecell/_lib/qc.py")
        assert not surface.is_editable("skills/singlecell/_lib/preprocessing.py")
        assert not surface.is_editable("omicsclaw/agents/config.yaml")

    def test_explicit_files_reject_frozen_paths(self, tmp_path):
        with pytest.raises(ValueError, match="frozen"):
            EditSurface(
                max_level=4,
                project_root=tmp_path,
                explicit_files=["omicsclaw/autoagent/judge.py"],
            )

    def test_explicit_files_reject_project_escape(self, tmp_path):
        with pytest.raises(ValueError, match="escapes project root"):
            EditSurface(
                max_level=4,
                project_root=tmp_path,
                explicit_files=["../outside.py"],
            )

    def test_validate_file_list(self, tmp_path):
        surface = EditSurface(max_level=1, project_root=tmp_path)
        files = [
            "skills/spatial/spatial-domains/SKILL.md",
            "skills/spatial/spatial-domains/spatial_domains.py",
            "omicsclaw/runtime/tool_executor.py",
        ]
        editable, rejected = surface.validate_file_list(files)
        assert len(editable) == 1
        assert "SKILL.md" in editable[0]
        assert len(rejected) == 2

    def test_is_frozen(self, tmp_path):
        surface = EditSurface(max_level=2, project_root=tmp_path)
        assert surface.is_frozen("omicsclaw/autoagent/api.py")
        assert surface.is_frozen("omicsclaw/memory/store.py")
        assert not surface.is_frozen("skills/singlecell/_lib/qc.py")

    def test_paths_outside_project_are_not_editable(self, tmp_path):
        surface = EditSurface(max_level=4, project_root=tmp_path)
        assert not surface.is_editable("../outside.py")
        assert not surface.file_exists("../outside.py")

    def test_describe(self, tmp_path):
        surface = EditSurface(max_level=2, project_root=tmp_path)
        desc = surface.describe()
        assert "Level 1" in desc
        assert "Level 2" in desc
        assert "Level 3" not in desc  # not active at max_level=2
        assert "Frozen" in desc

    def test_describe_explicit_files(self, tmp_path):
        surface = EditSurface(
            max_level=2,
            project_root=tmp_path,
            explicit_files=["a.py", "b.py"],
        )
        desc = surface.describe()
        assert "Explicit file list" in desc
        assert "a.py" in desc

    def test_to_dict(self, tmp_path):
        surface = EditSurface(max_level=2, project_root=tmp_path)
        d = surface.to_dict()
        assert d["max_level"] == 2
        assert len(d["active_levels"]) == 2
        assert len(d["frozen_patterns"]) > 0

    def test_read_file(self, tmp_path):
        skill_dir = tmp_path / "skills" / "test"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Test Skill")

        surface = EditSurface(max_level=1, project_root=tmp_path)
        content = surface.read_file("skills/test/SKILL.md")
        assert content == "# Test Skill"

    def test_read_file_rejects_frozen(self, tmp_path):
        (tmp_path / "omicsclaw").mkdir()
        (tmp_path / "omicsclaw" / "__init__.py").write_text("")

        surface = EditSurface(max_level=4, project_root=tmp_path)
        with pytest.raises(PermissionError):
            surface.read_file("omicsclaw/__init__.py")


class TestMVPSurface:
    def test_sc_preprocessing_surface(self, tmp_path):
        surface = build_sc_preprocessing_surface(tmp_path)
        assert surface.max_level == 2
        assert len(surface.explicit_files) == 3

        # Allowed files
        assert surface.is_editable("skills/singlecell/scrna/sc-preprocessing/SKILL.md")
        assert surface.is_editable("skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py")
        assert surface.is_editable("skills/singlecell/_lib/qc.py")

        # Rejected: other skill files
        assert not surface.is_editable("skills/singlecell/_lib/preprocessing.py")
        assert not surface.is_editable("skills/singlecell/scrna/sc-batch-integration/sc_integrate.py")

        # Rejected: infrastructure
        assert not surface.is_editable("omicsclaw/autoagent/judge.py")

    def test_spatial_domains_surface(self, tmp_path):
        surface = build_spatial_domains_surface(tmp_path, method="cellcharter")

        assert surface.max_level == 2
        assert surface.explicit_files == [
            "skills/spatial/spatial-domains/SKILL.md",
            "skills/spatial/spatial-domains/spatial_domains.py",
            "skills/spatial/_lib/domains.py",
        ]

        assert surface.is_editable("skills/spatial/spatial-domains/SKILL.md")
        assert surface.is_editable("skills/spatial/spatial-domains/spatial_domains.py")
        assert surface.is_editable("skills/spatial/_lib/domains.py")
        assert not surface.is_editable("skills/spatial/_lib/dependency_manager.py")
        assert not surface.is_editable("skills/spatial-domains/cellcharter/SKILL.md")
