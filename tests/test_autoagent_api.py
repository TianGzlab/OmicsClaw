from __future__ import annotations

import asyncio
from pathlib import Path

from omicsclaw.autoagent import _resolve_optimization_output_root, run_optimization
from omicsclaw.autoagent.api import optimizable_skills


def test_optimize_skills_catalog_is_canonical_and_launchable():
    result = asyncio.run(optimizable_skills())

    names = {item["skill"] for item in result["skills"]}
    assert "sc-batch-integration" in names
    assert "sc-integrate" not in names
    assert "spatial-integrate" in names
    assert "spatial-integration" not in names
    assert "sc-clustering" in names
    assert "sc-cell-annotation" in names

    for item in result["skills"]:
        assert item["skill"] == item["canonical_skill"]
        assert item["methods"]
        assert all(method["params"] for method in item["methods"])

    batch_skill = next(item for item in result["skills"] if item["skill"] == "sc-batch-integration")
    harmony = next(method for method in batch_skill["methods"] if method["name"] == "harmony")
    assert harmony["params"] == ["harmony_theta", "integration_pcs"]
    assert harmony["fixed_params"] == [
        {
            "name": "batch_key",
            "type": "string",
            "required": False,
            "default": "batch",
            "cli_flag": "--batch-key",
        }
    ]

    spatial_deconv = next(item for item in result["skills"] if item["skill"] == "spatial-deconv")
    flashdeconv = next(method for method in spatial_deconv["methods"] if method["name"] == "flashdeconv")
    fixed_names = {param["name"] for param in flashdeconv["fixed_params"]}
    assert {"reference", "cell_type_key"} <= fixed_names


def test_resolve_optimization_output_root_defaults_under_workspace_output(tmp_path):
    output_root = _resolve_optimization_output_root(
        "sc-batch-integration",
        "harmony",
        cwd=str(tmp_path),
    )

    assert output_root.parent == tmp_path / "output"
    assert output_root.name.startswith("optimize_sc-batch-integration_harmony_")


def test_resolve_optimization_output_root_resolves_relative_output_dir_against_workspace(tmp_path):
    output_root = _resolve_optimization_output_root(
        "sc-batch-integration",
        "harmony",
        cwd=str(tmp_path),
        output_dir="custom-output/run-001",
    )

    assert output_root == Path(tmp_path) / "custom-output" / "run-001"


def test_run_optimization_rejects_relative_input_path_without_cwd():
    result = run_optimization(
        skill_name="sc-batch-integration",
        method="harmony",
        input_path="data/demo.h5ad",
        max_trials=1,
    )

    assert result["success"] is False
    assert "Relative input_path requires cwd" in result["error"]


def test_run_optimization_rejects_missing_required_fixed_params_before_trials():
    result = run_optimization(
        skill_name="sc-batch-integration",
        method="scanvi",
        demo=True,
        max_trials=1,
        fixed_params={"batch_key": "sample_id"},
    )

    assert result["success"] is False
    assert "Missing required fixed parameters" in result["error"]
    assert "labels_key" in result["error"]
