"""Constraint check by the difference of two ``pip check`` runs (plan 0061 case 16, F49, F60).

An overlay's ``pip check`` sees the overlay and the base, and the base has
violations of its own (fourteen on the OmicsClaw environment). Keeping only
the lines whose subject is a newly installed package misses the case that
matters (F60): a *base* package that depends on the package just installed,
at a version the new one does not satisfy — ``corneto`` against a fake
``cvxpy-base 0.0.1``. Counting lines misses it as well, because the new line
replaced an old one. The set difference ``after − before`` catches both,
and does not care about line order.

The last test feeds real ``pip check`` output from a throw-away overlay, so
the parsing is pinned to what pip actually prints.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from omicsclaw.skillenv.overlay import new_violations

from .wheels import make_wheel

REPORTS = Path(__file__).resolve().parent / "fixtures" / "reports"
BASE_PYTHON = os.environ.get("OMICSCLAW_TEST_BASE_PYTHON") or sys.executable


def test_a_violation_whose_subject_is_a_base_package_is_found():
    before = (REPORTS / "pip_check_before.txt").read_text()
    after = (REPORTS / "pip_check_after.txt").read_text()
    assert len(before.splitlines()) == len(after.splitlines()) == 14
    assert new_violations(before, after) == (
        "corneto 1.0.0b7 has requirement cvxpy-base>=1.5.1, but you have cvxpy-base 0.0.1.",
    )


def test_the_same_lines_in_another_order_are_nothing_new():
    before = (REPORTS / "pip_check_before.txt").read_text()
    shuffled = "\n".join(reversed(before.splitlines())) + "\n"
    assert new_violations(before, before) == ()
    assert new_violations(before, shuffled) == ()


def test_pips_all_clear_line_is_not_a_violation():
    assert new_violations("No broken requirements found.\n", "No broken requirements found.\n") == ()
    assert new_violations("", "x 1.0 requires y, which is not installed.\n") == (
        "x 1.0 requires y, which is not installed.",
    )


def _pip(overlay: Path, *args: str) -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin", "HOME": str(overlay.parent), "PYTHONNOUSERSITE": "1",
           "PIP_CONFIG_FILE": os.devnull, "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PIP_NO_INPUT": "1"}
    return subprocess.run([str(overlay / "bin" / "python"), "-I", "-m", "pip", *args], env=env,
                          cwd=overlay.parent, capture_output=True, text=True, timeout=300)


def test_real_pip_output_is_parsed(tmp_path):
    wheels = tmp_path / "wheels"
    make_wheel(wheels, "oc-user", "1.0", requires=["oc_dep2>=1"])
    make_wheel(wheels, "oc-dep2", "0.1")
    overlay = tmp_path / "ov"
    subprocess.run([BASE_PYTHON, "-I", "-m", "venv", "--without-pip", "--system-site-packages", str(overlay)],
                   check=True, cwd=tmp_path, timeout=120)
    common = ("--no-index", "--find-links", str(wheels), "--no-deps", "--only-binary=:all:")
    assert _pip(overlay, "install", *common, "--", "oc-user==1.0").returncode == 0
    before = _pip(overlay, "check").stdout
    assert _pip(overlay, "install", *common, "--", "oc-dep2==0.1").returncode == 0
    after = _pip(overlay, "check").stdout
    (line,) = new_violations(before, after)
    assert line.lower().replace("_", "-").startswith("oc-user 1.0 has requirement oc-dep2>=1")
    assert line.endswith("but you have oc-dep2 0.1.")
