"""One ``sys.path`` bootstrap for every skill script (plan 0062 §3.11, case 23).

Each script that imports ``skills.*`` carries the same block before its first
such import: walk up from the script to the first directory holding
``skills/_sdk/__init__.py`` and put it on ``sys.path``; if there is none,
insert nothing and let the caller's ``PYTHONPATH`` decide. Scripts that also
use the repository root import it as ``REPO_ROOT`` from ``skills._sdk``, so a
copy run from outside the repository still points at the repository that
provides ``_sdk``.

The three situations the plan argues through each get a check:

* 23a local — run from an unrelated directory with no ``PYTHONPATH``;
* 23b ensemble — trial directory as cwd, absolute script path,
  ``PYTHONPATH=<repo>``; and a copy outside the repository, which must use
  ``PYTHONPATH`` and fail plainly without it;
* 23c sandbox — the real container path needs ``OMICSCLAW_TEST_SANDBOX=1`` and
  a container runtime; the always-run stand-in copies ``skills/`` and
  ``omicsclaw/`` read-only and checks the block writes nothing.
"""

from __future__ import annotations

import ast
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from tests.sdk._scan import REPO_ROOT, rel

CANONICAL = '''
_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))
'''
_CANONICAL_DUMP = [ast.dump(n) for n in ast.parse(CANONICAL).body]

LIGHT_SCRIPTS = [
    REPO_ROOT / "skills/bulkrna/bulkrna-qc/bulkrna_qc.py",
    REPO_ROOT / "skills/genomics/genomics-qc/genomics_qc.py",
    REPO_ROOT / "skills/proteomics/proteomics-de/proteomics_de.py",
]


def main_scripts() -> list[Path]:
    return sorted(
        p
        for skill_md in (REPO_ROOT / "skills").rglob("SKILL.md")
        for p in skill_md.parent.glob("*.py")
        if not p.name.startswith("_")
    )


def _imports_skills(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module and (
            n.module == "skills" or n.module.startswith("skills.")
        ):
            return True
        if isinstance(n, ast.Import) and any(a.name == "skills" or a.name.startswith("skills.") for a in n.names):
            return True
    return False


def bootstrap_problem(path: Path) -> str | None:
    """Why *path* lacks the canonical block before its first ``skills`` import, or ``None``."""
    body = ast.parse(path.read_text(encoding="utf-8")).body
    first = next((i for i, node in enumerate(body) if _imports_skills(node)), None)
    if first is None:
        return None
    dumps = [ast.dump(n) for n in body[:first]]
    for i in range(len(dumps) - 1):
        if dumps[i:i + 2] == _CANONICAL_DUMP:
            return None
    return f"no canonical bootstrap before line {body[first].lineno}"


def test_there_are_94_main_scripts():
    assert len(main_scripts()) == 94


def test_every_script_and_the_template_use_the_canonical_block():
    targets = main_scripts() + [REPO_ROOT / "templates" / "skill" / "replace_me.py"]
    problems = {rel(p): why for p in targets if (why := bootstrap_problem(p))}
    assert problems == {}


def _env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra)
    return env


def _help(script: Path, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", str(script), "--help"],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=300,
    )


@pytest.mark.parametrize("script", LIGHT_SCRIPTS, ids=lambda p: p.name)
def test_23a_local_run_from_an_unrelated_directory(script, tmp_path):
    proc = _help(script, tmp_path, _env())
    assert proc.returncode == 0, proc.stderr[-2000:]


def test_23b_ensemble_trial_with_pythonpath(tmp_path):
    trial = tmp_path / "trial"
    trial.mkdir()
    proc = _help(LIGHT_SCRIPTS[0], trial, _env(PYTHONPATH=str(REPO_ROOT)))
    assert proc.returncode == 0, proc.stderr[-2000:]


def _probe_copy(script: Path, destination: Path) -> Path:
    """Copy *script* into *destination* and make it print the repository root it resolved."""
    skill_copy = destination / script.parent.name
    shutil.copytree(script.parent, skill_copy, ignore=shutil.ignore_patterns("__pycache__", "tests"))
    probe = skill_copy / script.name
    source = probe.read_text(encoding="utf-8")
    body = ast.parse(source).body
    guard = next(n for n in body if isinstance(n, ast.If) and "_SDK_ANCHOR" in ast.unparse(n.test))
    lines = source.splitlines(keepends=True)
    insert = (
        "from skills._sdk import REPO_ROOT as _PROBE_ROOT\n"
        "print('PROBE_ROOT=' + str(_PROBE_ROOT))\n"
    )
    probe.write_text("".join(lines[: guard.end_lineno]) + insert + "".join(lines[guard.end_lineno:]), encoding="utf-8")
    return probe


def test_23b_a_copy_outside_the_repository_uses_pythonpath(tmp_path):
    probe = _probe_copy(LIGHT_SCRIPTS[0], tmp_path / "outside")
    trial = tmp_path / "trial"
    trial.mkdir()

    with_path = _help(probe, trial, _env(PYTHONPATH=str(REPO_ROOT)))
    assert with_path.returncode == 0, with_path.stderr[-2000:]
    assert f"PROBE_ROOT={REPO_ROOT}" in with_path.stdout

    installed = subprocess.run(
        [sys.executable, "-c", "import skills"], cwd=trial, env=_env(), capture_output=True
    )
    if installed.returncode == 0:
        pytest.skip("this interpreter has OmicsClaw installed, so skills imports without PYTHONPATH")
    without = _help(probe, trial, _env())
    assert without.returncode != 0
    assert "No module named 'skills'" in without.stderr


def test_23c_real_sandbox():
    if os.environ.get("OMICSCLAW_TEST_SANDBOX") != "1" or not (shutil.which("docker") or shutil.which("podman")):
        pytest.skip("OMICSCLAW_TEST_SANDBOX=1 and a container runtime are needed for the real sandbox run")
    pytest.skip("real SandboxExecutor run not automated here; the read-only stand-in below covers the block")


def _make_writable(root: Path) -> None:
    for path in [root, *root.rglob("*")]:
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | stat.S_IWUSR)


def _listing(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*")}


def test_23c_stand_in_read_only_copy_writes_nothing(tmp_path):
    mirror = tmp_path / "mirror"
    ignore = shutil.ignore_patterns("__pycache__", "*.h5ad", "*.pyc", "tests", "data")
    shutil.copytree(REPO_ROOT / "skills", mirror / "skills", ignore=ignore)
    shutil.copytree(REPO_ROOT / "omicsclaw", mirror / "omicsclaw", ignore=ignore)
    for path in [mirror, *mirror.rglob("*")]:
        if not path.is_symlink():
            path.chmod(path.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    try:
        before = _listing(mirror)
        script = mirror / LIGHT_SCRIPTS[0].relative_to(REPO_ROOT)
        cwd = tmp_path / "work"
        cwd.mkdir()
        proc = _help(script, cwd, _env())
        assert proc.returncode == 0, proc.stderr[-2000:]
        assert _listing(mirror) == before
    finally:
        _make_writable(mirror)
