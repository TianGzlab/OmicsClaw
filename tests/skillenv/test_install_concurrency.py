"""Two installations of one overlay, half-built overlays and changed bases (plan 0061 case 19, F62, §4.6).

The lock of overlay ``<key>`` is ``<root>/.locks/<key>.lock`` and is never
deleted: a lock file inside the directory that a failure removes stops
excluding anyone (F62 — a waiter holding the deleted inode and a newcomer
holding the new one both get in). Inside the lock the fingerprint is checked
again, so of two calls for the same key only one installs and the other
reuses its result, whether the two are coroutines of one process or two
processes. A directory without a fingerprint is what a killed process leaves
behind; the next call removes it under the lock and builds again. A finished
overlay is never removed, and a changed base simply gets a new key while the
old overlay stays as it was.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from omicsclaw.skillenv import tool as tool_module
from omicsclaw.skillenv.overlay import FINGERPRINT, base_distributions
from omicsclaw.tools.context import ApprovalDecision, use_tool_context

from .conftest import REPO
from .installing import SKILL, harness
from .wheels import make_wheel, pip_conf


def _wheels(directory: Path) -> Path:
    make_wheel(directory, "oc-leaf", "1.0", requires=["oc-dep>=1"])
    make_wheel(directory, "oc-dep", "1.0")
    make_wheel(directory, "oc-multi", "1.0")
    make_wheel(directory, "oc-extra", "1.0")
    return directory


def test_two_coroutines_install_once(tmp_path):
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[_wheels(tmp_path / "wh")]))

    async def main():
        with use_tool_context(approval=lambda request: ApprovalDecision(approved=True)):
            payload = json.dumps({"skills": [SKILL], "packages": ["oc-leaf"]})
            return await asyncio.gather(h.tool.execute(payload), h.tool.execute(payload))

    outputs = asyncio.run(asyncio.wait_for(main(), 300))
    firsts = sorted(output.splitlines()[0].split(" ")[0] for output in outputs)
    assert firsts == ["An", "Installed"], outputs
    assert h.runner.stages().count("install") == 1
    (key_dir,) = h.key_dirs()
    assert (key_dir / ".venv" / FINGERPRINT).is_file()
    assert (h.root / ".locks" / f"{key_dir.name}.lock").is_file()


_PROCESS = """
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, {repo!r})
from tests.skillenv.installing import harness
from tests.skillenv.wheels import pip_conf
from omicsclaw.tools.context import ApprovalDecision, use_tool_context
own = Path(sys.argv[1])
h = harness(own, pip_conf(own / "pip.conf", find_links=[{wheels!r}]), root=Path({root!r}))
async def main():
    with use_tool_context(approval=lambda request: ApprovalDecision(approved=True)):
        return await h.tool.execute(json.dumps({{"skills": ["oc-skill"], "packages": ["oc-leaf"]}}))
output = asyncio.run(main())
print(json.dumps({{"first": output.splitlines()[0], "installs": h.runner.stages().count("install")}}))
"""


def test_two_processes_install_once(tmp_path):
    wheels = _wheels(tmp_path / "wh")
    root = tmp_path / "shared-envs"
    script = tmp_path / "one_install.py"
    script.write_text(_PROCESS.format(repo=str(REPO), wheels=str(wheels), root=str(root)))
    processes = []
    for name in ("p1", "p2"):
        (tmp_path / name).mkdir()
        processes.append(subprocess.Popen([sys.executable, str(script), str(tmp_path / name)], cwd=str(REPO),
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    reports = []
    for process in processes:
        out, err = process.communicate(timeout=300)
        assert process.returncode == 0, err
        reports.append(json.loads(out.strip().splitlines()[-1]))
    assert sum(report["installs"] for report in reports) == 1, reports
    assert sorted(report["first"].split(" ")[0] for report in reports) == ["An", "Installed"], reports
    finished = [p for p in root.iterdir() if len(p.name) == 16]
    assert len(finished) == 1 and (finished[0] / ".venv" / FINGERPRINT).is_file()


def test_a_half_built_overlay_is_removed_and_built_again(tmp_path):
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[_wheels(tmp_path / "wh")]))
    assert h.call(["oc-leaf"]).startswith("Installed")
    (key_dir,) = h.key_dirs()
    (key_dir / ".venv" / FINGERPRINT).unlink()
    (key_dir / "left-by-a-killed-process").write_text("x")
    output = h.call(["oc-leaf"])
    assert output.startswith("Installed"), output
    assert len(h.asked) == 2
    assert (key_dir / ".venv" / FINGERPRINT).is_file()
    assert not (key_dir / "left-by-a-killed-process").exists()


def test_a_failure_never_removes_a_finished_overlay(tmp_path):
    wheels = _wheels(tmp_path / "wh")
    make_wheel(wheels, "oc-needs-old", "1.0", requires=["packaging<1"])
    make_wheel(wheels, "packaging", "0.9")
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[wheels]))
    assert h.call(["oc-leaf"]).startswith("Installed")
    (finished,) = h.key_dirs()
    failed = h.call(["oc-needs-old"])
    assert failed.startswith("install_skill_deps failed"), failed
    assert h.key_dirs() == [finished] and (finished / ".venv" / FINGERPRINT).is_file()
    assert len(list((h.root / ".locks").glob("*.lock"))) == 2


def test_a_changed_base_gets_a_new_key_and_the_old_overlay_stays(tmp_path, monkeypatch):
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[_wheels(tmp_path / "wh")]))
    assert h.call(["oc-leaf"]).startswith("Installed")
    (old,) = h.key_dirs()

    def changed(records):
        return base_distributions([*records, ("oc-upgraded-in-base", "2.0", "oc_upgraded_in_base-2.0.dist-info")])

    monkeypatch.setattr(tool_module, "base_distributions", changed)
    output = h.call(["oc-leaf"])
    assert output.startswith("Installed"), output
    dirs = h.key_dirs()
    assert len(dirs) == 2 and old in dirs
    assert all((d / ".venv" / FINGERPRINT).is_file() for d in dirs)


def test_an_entry_with_also_installs_every_distribution(tmp_path):
    h = harness(tmp_path, pip_conf(tmp_path / "pip.conf", find_links=[_wheels(tmp_path / "wh")]))
    output = h.call(["oc-multi"])
    assert output.startswith("Installed"), output
    assert "oc_multi-1.0-py3-none-any.whl" in output and "oc_extra-1.0-py3-none-any.whl" in output
    dry = next(c for c in h.runner.calls if c.stage == "dry-run")
    assert dry.argv[dry.argv.index("--") + 1:] == ["oc-multi", "oc-extra"]
