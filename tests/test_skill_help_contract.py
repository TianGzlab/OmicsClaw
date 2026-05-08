"""Contract tests for cheap, registry-wide skill help introspection."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from omicsclaw.core.registry import OmicsRegistry


ROOT = Path(__file__).resolve().parent.parent


def _primary_skill_scripts() -> list[pytest.ParamSpec]:
    registry = OmicsRegistry()
    registry.load_all()

    cases = []
    for alias, info in registry.iter_primary_skills():
        script = Path(info["script"])
        if not script.is_absolute():
            script = ROOT / script
        cases.append(pytest.param(alias, script, id=alias))
    return cases


@pytest.mark.parametrize("alias,script", _primary_skill_scripts())
def test_primary_skill_script_help_exits_successfully(alias: str, script: Path):
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{ROOT}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else str(ROOT)
    )
    env.setdefault("MPLBACKEND", "Agg")

    command = [sys.executable, str(script), "--help"]
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = f"{result.stdout}\n{result.stderr}".strip()

    assert result.returncode == 0, (
        f"{alias} --help failed\n"
        f"script: {script.relative_to(ROOT)}\n"
        f"command: {' '.join(command)}\n"
        f"returncode: {result.returncode}\n"
        f"output:\n{output[:4000]}"
    )
    lowered = output.lower()
    assert output and any(token in lowered for token in ("usage", "options", "--help")), (
        f"{alias} --help did not look like help output\n"
        f"script: {script.relative_to(ROOT)}\n"
        f"output:\n{output[:2000]}"
    )
