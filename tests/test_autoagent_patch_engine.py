"""Tests for omicsclaw.autoagent.patch_engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omicsclaw.autoagent.edit_surface import EditSurface, build_spatial_domains_surface
from omicsclaw.autoagent.patch_engine import (
    FileDiff,
    Hunk,
    PatchPlan,
    ValidationResult,
    apply_patch,
    backup_files,
    parse_patch_response,
    revert_files,
    validate_patch,
)


def _write_spatial_domains_fixture(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "spatial" / "spatial-domains"
    skill_dir.mkdir(parents=True, exist_ok=True)
    lib_dir = tmp_path / "skills" / "spatial" / "_lib"
    lib_dir.mkdir(parents=True, exist_ok=True)

    (skill_dir / "SKILL.md").write_text("### CellCharter\n", encoding="utf-8")
    (skill_dir / "spatial_domains.py").write_text(
        "def main():\n    summary = dispatch_method(args.method, adata)\n",
        encoding="utf-8",
    )
    (lib_dir / "domains.py").write_text(
        """def identify_domains_leiden(adata):
    marker = "leiden"
    return marker


def identify_domains_stagate(adata):
    marker = "stagate"
    return marker


def identify_domains_cellcharter(adata):
    marker = "cellcharter"
    return marker


def _cluster_fixed_k():
    return "fixed"


def _cluster_auto_k():
    return "auto"


def dispatch_method(method, adata):
    return method
""",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Parse tests
# ---------------------------------------------------------------------------


class TestParsePatchResponse:
    def test_parse_basic(self):
        response = json.dumps({
            "patch_plan": {
                "target_files": ["skills/test/SKILL.md"],
                "description": "Update default threshold",
                "expected_improvements": ["Better QC"],
                "rollback_conditions": ["Retention < 5%"],
            },
            "diffs": [
                {
                    "file": "skills/test/SKILL.md",
                    "hunks": [
                        {
                            "old_code": "min_genes: 200",
                            "new_code": "min_genes: 300",
                        }
                    ],
                }
            ],
            "reasoning": "Higher threshold filters noise.",
        })
        plan = parse_patch_response(response)
        assert not plan.converged
        assert plan.target_files == ["skills/test/SKILL.md"]
        assert len(plan.diffs) == 1
        assert plan.diffs[0].hunks[0].old_code == "min_genes: 200"
        assert plan.reasoning == "Higher threshold filters noise."

    def test_parse_with_markdown_fences(self):
        response = "Here is my patch:\n```json\n" + json.dumps({
            "patch_plan": {"target_files": ["a.py"]},
            "diffs": [{"file": "a.py", "hunks": [
                {"old_code": "x = 1", "new_code": "x = 2"}
            ]}],
            "reasoning": "test",
        }) + "\n```"
        plan = parse_patch_response(response)
        assert len(plan.diffs) == 1

    def test_parse_convergence(self):
        response = json.dumps({
            "converged": True,
            "reasoning": "No further improvements possible.",
        })
        plan = parse_patch_response(response)
        assert plan.converged is True
        assert "No further" in plan.reasoning

    def test_parse_invalid_json(self):
        with pytest.raises(ValueError):
            parse_patch_response("this is not json at all")

    def test_parse_skips_noop_hunks(self):
        response = json.dumps({
            "patch_plan": {"target_files": ["a.py"]},
            "diffs": [{"file": "a.py", "hunks": [
                {"old_code": "same", "new_code": "same"},  # no-op
                {"old_code": "old", "new_code": "new"},  # real
            ]}],
            "reasoning": "test",
        })
        plan = parse_patch_response(response)
        assert len(plan.diffs[0].hunks) == 1
        assert plan.diffs[0].hunks[0].old_code == "old"

    def test_patch_plan_properties(self):
        plan = PatchPlan(
            diffs=[
                FileDiff("a.py", [Hunk("x", "y"), Hunk("a", "b")]),
                FileDiff("b.py", [Hunk("c", "d")]),
            ]
        )
        assert plan.n_hunks == 3
        assert "2 file(s)" in plan.diff_summary
        assert "3 hunk(s)" in plan.diff_summary

    def test_to_dict(self):
        plan = PatchPlan(
            target_files=["a.py"],
            description="test",
            diffs=[FileDiff("a.py", [Hunk("old", "new")])],
            reasoning="why",
        )
        d = plan.to_dict()
        assert d["target_files"] == ["a.py"]
        assert d["diffs"][0]["hunks"][0]["old_code"] == "old"


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


class TestValidatePatch:
    def test_valid_patch(self, tmp_path):
        # Create file
        skill_dir = tmp_path / "skills" / "test"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("min_genes: 200\nother: stuff")

        surface = EditSurface(
            max_level=1, project_root=tmp_path,
            explicit_files=["skills/test/SKILL.md"],
        )
        patch = PatchPlan(diffs=[
            FileDiff("skills/test/SKILL.md", [
                Hunk("min_genes: 200", "min_genes: 300")
            ])
        ])
        result = validate_patch(patch, surface)
        assert result.valid is True

    def test_outside_surface(self, tmp_path):
        surface = EditSurface(
            max_level=1, project_root=tmp_path,
            explicit_files=["skills/test/SKILL.md"],
        )
        patch = PatchPlan(diffs=[
            FileDiff("omicsclaw/runtime/tool_executor.py", [
                Hunk("old", "new")
            ])
        ])
        result = validate_patch(patch, surface)
        assert result.valid is False
        assert "frozen" in result.errors[0]

    def test_old_code_not_found(self, tmp_path):
        skill_dir = tmp_path / "skills" / "test"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("actual content here")

        surface = EditSurface(
            max_level=1, project_root=tmp_path,
            explicit_files=["skills/test/SKILL.md"],
        )
        patch = PatchPlan(diffs=[
            FileDiff("skills/test/SKILL.md", [
                Hunk("nonexistent code", "new code")
            ])
        ])
        result = validate_patch(patch, surface)
        assert result.valid is False
        assert "not found" in result.errors[0]

    def test_empty_diffs(self, tmp_path):
        surface = EditSurface(max_level=1, project_root=tmp_path)
        patch = PatchPlan(diffs=[])
        result = validate_patch(patch, surface)
        assert result.valid is False
        assert "no diffs" in result.errors[0].lower()

    def test_rejects_project_escape(self, tmp_path):
        patch = PatchPlan(diffs=[
            FileDiff("../outside.py", [Hunk("old", "new")])
        ])
        surface = EditSurface(max_level=4, project_root=tmp_path)
        result = validate_patch(patch, surface)
        assert result.valid is False
        assert "escapes project root" in result.errors[0]

    def test_rejects_non_target_method_patch_for_spatial_domains(self, tmp_path):
        _write_spatial_domains_fixture(tmp_path)
        surface = build_spatial_domains_surface(tmp_path, method="cellcharter")
        patch = PatchPlan(diffs=[
            FileDiff("skills/spatial/_lib/domains.py", [
                Hunk('marker = "stagate"', 'marker = "stagate_v2"')
            ])
        ])

        result = validate_patch(patch, surface)

        assert result.valid is False
        assert "non-target method code" in result.errors[0]
        assert "cellcharter" in result.errors[0]

    def test_allows_target_helper_patch_for_spatial_domains(self, tmp_path):
        _write_spatial_domains_fixture(tmp_path)
        surface = build_spatial_domains_surface(tmp_path, method="cellcharter")
        patch = PatchPlan(diffs=[
            FileDiff("skills/spatial/_lib/domains.py", [
                Hunk('return "fixed"', 'return "fixed_v2"')
            ])
        ])

        result = validate_patch(patch, surface)

        assert result.valid is True


# ---------------------------------------------------------------------------
# Apply / revert tests
# ---------------------------------------------------------------------------


class TestApplyPatch:
    def test_apply_single_hunk(self, tmp_path):
        (tmp_path / "test.py").write_text(
            "def foo():\n    return 200\n"
        )
        surface = EditSurface(
            max_level=4,
            project_root=tmp_path,
            explicit_files=["test.py"],
        )
        patch = PatchPlan(diffs=[
            FileDiff("test.py", [
                Hunk("return 200", "return 300")
            ])
        ])
        modified = apply_patch(patch, surface)
        assert modified == ["test.py"]
        assert "return 300" in (tmp_path / "test.py").read_text()

    def test_apply_multiple_hunks(self, tmp_path):
        (tmp_path / "test.py").write_text(
            "x = 1\ny = 2\nz = 3\n"
        )
        surface = EditSurface(
            max_level=4,
            project_root=tmp_path,
            explicit_files=["test.py"],
        )
        patch = PatchPlan(diffs=[
            FileDiff("test.py", [
                Hunk("x = 1", "x = 10"),
                Hunk("z = 3", "z = 30"),
            ])
        ])
        modified = apply_patch(patch, surface)
        content = (tmp_path / "test.py").read_text()
        assert "x = 10" in content
        assert "y = 2" in content
        assert "z = 30" in content

    def test_apply_multiple_files(self, tmp_path):
        (tmp_path / "a.py").write_text("a = 1\n")
        (tmp_path / "b.py").write_text("b = 2\n")
        surface = EditSurface(
            max_level=4,
            project_root=tmp_path,
            explicit_files=["a.py", "b.py"],
        )
        patch = PatchPlan(diffs=[
            FileDiff("a.py", [Hunk("a = 1", "a = 10")]),
            FileDiff("b.py", [Hunk("b = 2", "b = 20")]),
        ])
        modified = apply_patch(patch, surface)
        assert set(modified) == {"a.py", "b.py"}

    def test_apply_hunk_not_found(self, tmp_path):
        (tmp_path / "test.py").write_text("real content\n")
        surface = EditSurface(
            max_level=4,
            project_root=tmp_path,
            explicit_files=["test.py"],
        )
        patch = PatchPlan(diffs=[
            FileDiff("test.py", [Hunk("nonexistent", "new")])
        ])
        with pytest.raises(ValueError, match="not found"):
            apply_patch(patch, surface)

    def test_apply_rejects_paths_outside_surface(self, tmp_path):
        (tmp_path / "test.py").write_text("value = 1\n")
        surface = EditSurface(
            max_level=4,
            project_root=tmp_path,
            explicit_files=["allowed.py"],
        )
        patch = PatchPlan(diffs=[
            FileDiff("test.py", [Hunk("value = 1", "value = 2")])
        ])
        with pytest.raises(PermissionError, match="explicit editable file list"):
            apply_patch(patch, surface)

    def test_apply_rejects_project_escape(self, tmp_path):
        outside = tmp_path.parent / "outside.py"
        outside.write_text("value = 1\n")
        surface = EditSurface(max_level=4, project_root=tmp_path)
        patch = PatchPlan(diffs=[
            FileDiff("../outside.py", [Hunk("value = 1", "value = 2")])
        ])
        with pytest.raises(ValueError, match="escapes project root"):
            apply_patch(patch, surface)
        assert outside.read_text() == "value = 1\n"


class TestBackupRevert:
    def test_backup_and_revert(self, tmp_path):
        src_dir = tmp_path / "src"
        backup_dir = tmp_path / "backup"
        src_dir.mkdir()

        (src_dir / "test.py").write_text("original content")

        # Backup
        backup_files(["test.py"], src_dir, backup_dir)
        assert (backup_dir / "test.py").exists()

        # Modify
        (src_dir / "test.py").write_text("modified content")

        # Revert
        revert_files(["test.py"], src_dir, backup_dir)
        assert (src_dir / "test.py").read_text() == "original content"
