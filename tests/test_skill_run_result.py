from __future__ import annotations

from pathlib import Path

from omicsclaw.core.skill_result import build_skill_run_result, coerce_skill_run_result


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


def test_build_skill_run_result_normalizes_runner_fields_for_legacy_dict():
    result = build_skill_run_result(
        skill="demo-skill",
        success=True,
        exit_code=0,
        output_dir=Path("/tmp/demo"),
        files=[Path("result.json"), "report.md"],
        stdout="ok",
        stderr="",
        duration_seconds=1.234,
        method="demo",
        readme_path=Path("/tmp/demo/README.md"),
        notebook_path=Path("/tmp/demo/reproducibility/analysis_notebook.ipynb"),
    )

    assert result.to_legacy_dict() == {
        "skill": "demo-skill",
        "success": True,
        "exit_code": 0,
        "output_dir": "/tmp/demo",
        "files": ["result.json", "report.md"],
        "stdout": "ok",
        "stderr": "",
        "duration_seconds": 1.23,
        "method": "demo",
        "readme_path": "/tmp/demo/README.md",
        "notebook_path": "/tmp/demo/reproducibility/analysis_notebook.ipynb",
    }


def test_build_skill_run_result_treats_single_file_string_as_one_file():
    result = build_skill_run_result(
        skill="demo-skill",
        success=True,
        exit_code=0,
        output_dir="/tmp/demo",
        files="result.json",
    )

    assert result.files == ("result.json",)
