from __future__ import annotations

import importlib
import inspect


def test_skill_runner_module_exposes_run_skill_contract():
    module = importlib.import_module("omicsclaw.core.skill_runner")

    assert hasattr(module, "run_skill")
    signature = inspect.signature(module.run_skill)
    assert list(signature.parameters) == [
        "skill_name",
        "input_path",
        "input_paths",
        "output_dir",
        "demo",
        "session_path",
        "extra_args",
    ]


def test_root_omicsclaw_reexports_shared_run_skill():
    root = importlib.import_module("omicsclaw")
    runner = importlib.import_module("omicsclaw.core.skill_runner")

    assert root.run_skill is runner.run_skill
