from __future__ import annotations

from omicsclaw.core.skill_result import coerce_skill_run_result


def test_skill_run_result_normalizes_failed_zero_exit_for_adapters():
    result = coerce_skill_run_result(
        {
            "skill": "demo-skill",
            "success": False,
            "exit_code": 0,
            "stdout": "",
            "stderr": "missing dependency",
        }
    )

    assert result.adapter_exit_code == 1
    assert result.error_text(default="skill_runner_failed") == "missing dependency"
    assert result.combined_output == "missing dependency"


def test_skill_run_result_preserves_run_skill_legacy_dict_shape():
    result = coerce_skill_run_result(
        {
            "skill": "demo-skill",
            "success": True,
            "exit_code": 0,
            "output_dir": "/tmp/demo",
            "files": ("result.json",),
            "stdout": "ok",
            "stderr": "",
            "duration_seconds": 1.25,
            "method": "demo",
            "readme_path": "/tmp/demo/README.md",
            "notebook_path": "/tmp/demo/reproducibility/analysis_notebook.ipynb",
        }
    )

    assert result.to_legacy_dict() == {
        "skill": "demo-skill",
        "success": True,
        "exit_code": 0,
        "output_dir": "/tmp/demo",
        "files": ["result.json"],
        "stdout": "ok",
        "stderr": "",
        "duration_seconds": 1.25,
        "method": "demo",
        "readme_path": "/tmp/demo/README.md",
        "notebook_path": "/tmp/demo/reproducibility/analysis_notebook.ipynb",
    }
