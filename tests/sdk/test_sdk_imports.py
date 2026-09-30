"""``skills._sdk`` imports cleanly without the framework (plan 0062 case 8 and B10).

Each check runs in a fresh interpreter so that modules the test process has
already imported cannot mask a missing or forbidden import.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from tests.sdk._scan import REPO_ROOT

MOVED_MODULES = ("external_env", "deps", "r_script_runner", "r_utils", "r_dependency_manager")


def _sdk_modules() -> list[str]:
    return sorted(
        f"skills._sdk.{p.stem}"
        for p in (REPO_ROOT / "skills" / "_sdk").glob("*.py")
        if p.stem != "__init__"
    )


def _run(code: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=300,
    )


def test_moved_modules_import_without_loading_the_framework():
    code = (
        "import importlib, json, sys\n"
        f"for m in {list(MOVED_MODULES)!r}:\n"
        "    importlib.import_module('skills._sdk.' + m)\n"
        "print(json.dumps(sorted(n for n in sys.modules if n == 'omicsclaw' or n.startswith('omicsclaw.'))))\n"
    )
    proc = _run(code)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == []


def test_importing_the_package_loads_no_scientific_stack():
    proc = _run(
        "import sys, skills._sdk as s\n"
        "print(s.REPO_ROOT)\n"
        "print('numpy' in sys.modules, 'pandas' in sys.modules)\n"
    )
    assert proc.returncode == 0, proc.stderr
    root, loaded = proc.stdout.strip().splitlines()[-2:]
    assert root == str(REPO_ROOT)
    assert loaded == "False False"


def test_sdk_modules_import_with_the_framework_blocked():
    """B10, ``_sdk`` half: with ``omicsclaw`` unimportable, every ``_sdk`` module still imports.

    A failure whose chain mentions ``omicsclaw`` is a violation; a missing
    third-party package is reported as skipped, not passed.
    """
    modules = _sdk_modules()
    assert modules, "skills/_sdk has no modules"
    code = (
        "import importlib, json, sys, traceback\n"
        "sys.modules['omicsclaw'] = None\n"
        "out = {}\n"
        f"for m in {modules!r}:\n"
        "    try:\n"
        "        importlib.import_module(m)\n"
        "        out[m] = 'ok'\n"
        "    except BaseException as e:\n"
        "        tb = traceback.format_exc()\n"
        "        chain, x = [], e\n"
        "        while x is not None:\n"
        "            chain.append(str(x) + ' ' + str(getattr(x, 'name', '') or ''))\n"
        "            x = x.__cause__ or x.__context__\n"
        "        if any('omicsclaw' in c for c in chain):\n"
        "            out[m] = 'violation: ' + tb\n"
        "        elif isinstance(e, ModuleNotFoundError):\n"
        "            out[m] = 'skipped: ' + str(e.name)\n"
        "        else:\n"
        "            out[m] = 'error: ' + tb\n"
        "print(json.dumps(out))\n"
    )
    proc = _run(code)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    skipped = {m: v for m, v in result.items() if v.startswith("skipped")}
    if skipped:
        print("skipped for missing third-party packages:", skipped)
    bad = {m: v for m, v in result.items() if not v.startswith(("ok", "skipped"))}
    assert bad == {}
    if len(skipped) == len(result):
        pytest.skip(f"every _sdk module skipped: {skipped}")
