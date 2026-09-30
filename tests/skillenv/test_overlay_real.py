"""Real overlays on the base interpreter (plan 0061 case 17, F32, F47).

An overlay made with ``python -I -m venv --without-pip --system-site-packages``
sees the base's packages and uses the base's own pip. A base without pip gets
an overlay made with the standard library's ``ensurepip`` instead. A base that
is itself a virtual environment is refused before anyone is asked: an overlay
built on it would inherit the interpreter underneath and not see the venv's
packages (F47).

Run with the ``rapids_singlecell`` interpreter by default; plan 0061 §6 also
asks for a run with ``OMICSCLAW_TEST_BASE_PYTHON=/opt/conda/envs/OmicsClaw/bin/python``
under that interpreter's own pytest.
"""

from __future__ import annotations

import asyncio
import dataclasses
import subprocess

from omicsclaw.skillenv.overlay import OverlayBuilder, OverlayRequest, base_distributions, overlay_key
from omicsclaw.skillenv.probe import run_inventory

from .installing import BASE_PYTHON, PathProbeRunner, RecordingRunner, agent_environment, harness
from .wheels import make_wheel, pip_conf


def _base_prefix() -> str:
    return subprocess.run([BASE_PYTHON, "-I", "-c", "import sys; print(sys.prefix)"], capture_output=True,
                          text=True, timeout=60, check=True).stdout.strip()


def test_the_overlay_sees_the_base_and_uses_the_base_pip(tmp_path):
    wheels = tmp_path / "wh"
    make_wheel(wheels, "oc-leaf", "1.0")
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[wheels]))
    seen = {}

    def inspect():
        (venv,) = [p / ".venv" for p in h.root.iterdir() if len(p.name) == 16]
        python = venv / "bin" / "python"
        seen["cfg"] = (venv / "pyvenv.cfg").read_text()
        seen["pip"] = subprocess.run([str(python), "-I", "-m", "pip", "--version"], capture_output=True, text=True,
                                     timeout=60, env={"PATH": "/usr/bin:/bin"}).stdout
        seen["own_pip"] = list(venv.glob("lib/python*/site-packages/pip"))

    h.runner.after["venv"] = inspect
    assert h.call(["oc-leaf"]).startswith("Installed into the overlay")
    assert "include-system-site-packages = true" in seen["cfg"]
    assert _base_prefix() in seen["pip"] and seen["own_pip"] == []
    create = h.runner.calls[0]
    assert create.argv[1:5] == ["-I", "-m", "venv", "--system-site-packages"] and "--without-pip" in create.argv


def test_a_base_without_pip_gets_an_overlay_with_its_own_pip(tmp_path):
    wheels = tmp_path / "wh"
    make_wheel(wheels, "oc-leaf", "1.0")
    environment = agent_environment(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[wheels]))
    probe = PathProbeRunner(environment)
    inventory = asyncio.run(run_inventory(probe, ["oc_leaf"], "", cwd=str(tmp_path),
                                          env={"PYTHONNOUSERSITE": "1"}))
    inventory = dataclasses.replace(inventory, pip_version=None)
    base = base_distributions(inventory.records)
    runner = RecordingRunner()
    seen = {}

    def inspect():
        seen["own_pip"] = [p for p in (tmp_path / "envs").glob("*/.venv/lib/python*/site-packages/pip")]

    runner.after["venv"] = inspect
    builder = OverlayBuilder(tmp_path / "envs", environment=lambda: environment, runner=runner)
    request = OverlayRequest(skill="oc-skill", names=("oc-leaf",), specs=("oc-leaf",), required_imports=("oc_leaf",))
    result = asyncio.run(builder.build(request, inventory, base, overlay_key(inventory, base, ("oc-leaf",))))
    assert result.status == "installed", result.reason
    assert "--without-pip" not in runner.calls[0].argv
    assert seen["own_pip"], "ensurepip did not put pip in the overlay"


def test_a_virtual_environment_as_base_is_refused(tmp_path):
    vbase = tmp_path / "vbase"
    subprocess.run([BASE_PYTHON, "-I", "-m", "venv", "--without-pip", str(vbase)], check=True, timeout=120)
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[tmp_path]))
    h.probe._path = f"{vbase / 'bin'}:/usr/bin:/bin"
    output = h.call(["oc-leaf"])
    assert "is itself a virtual environment" in output and "refused" in output
    assert h.asked == [] and h.runner.calls == [] and not h.root.exists()
