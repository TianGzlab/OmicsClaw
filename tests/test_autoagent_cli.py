from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


def _load_omicsclaw_script():
    spec = importlib.util.spec_from_file_location("omicsclaw_main_autoagent_cli_test", ROOT / "omicsclaw.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_optimize_rejects_unknown_flags(monkeypatch, capsys):
    oc = _load_omicsclaw_script()
    monkeypatch.setattr(
        sys,
        "argv",
        ["omicsclaw.py", "optimize", "foo", "--method", "bar", "--badflag", "baz"],
    )

    with pytest.raises(SystemExit) as excinfo:
        oc.main()

    assert excinfo.value.code == 2
    assert "unrecognized arguments: --badflag baz" in capsys.readouterr().err


def test_run_still_forwards_unknown_flags(monkeypatch):
    oc = _load_omicsclaw_script()
    captured: dict[str, object] = {}

    from omicsclaw.core.skill_result import build_skill_run_result

    def fake_run_skill(skill, **kwargs):
        captured["skill"] = skill
        captured.update(kwargs)
        return build_skill_run_result(
            skill=skill,
            success=True,
            exit_code=0,
            output_dir=None,
        )

    monkeypatch.setattr(oc, "run_skill", fake_run_skill)
    monkeypatch.setattr(
        sys,
        "argv",
        ["omicsclaw.py", "run", "demo-skill", "--method", "demo", "--new-flag", "42"],
    )

    oc.main()
    assert captured["skill"] == "demo-skill"
    assert captured["extra_args"] == ["--method", "demo", "--new-flag", "42"]


def test_optimize_forwards_cwd_for_relative_input(monkeypatch):
    oc = _load_omicsclaw_script()
    import omicsclaw.autoagent as autoagent_pkg

    captured: dict[str, object] = {}

    def fake_run_optimization(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "output_dir": "/tmp/optimized",
            "reproduce_command": "",
        }

    monkeypatch.setattr(autoagent_pkg, "run_optimization", fake_run_optimization)
    monkeypatch.setattr(oc.os, "getcwd", lambda: "/tmp/workspace")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "omicsclaw.py",
            "optimize",
            "sc-batch-integration",
            "--method",
            "harmony",
            "--input",
            "data/demo.h5ad",
            "--max-trials",
            "1",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        oc.main()

    assert excinfo.value.code == 0
    assert captured["input_path"] == "data/demo.h5ad"
    assert captured["cwd"] == "/tmp/workspace"
