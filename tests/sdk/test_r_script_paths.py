"""Where skills find the shared R scripts (plan 0062 case 7b).

The 28 shared ``.R`` files moved from ``omicsclaw/r_scripts`` to
``skills/_sdk/r_scripts``. Skills take the directory only under the alias
``_SDK_R_SCRIPTS_DIR`` so it can never overwrite a skill's own variable of
the same name — sc-enrichment's library has both its own ``rscripts/`` and the
shared directory, and the two must stay distinct.
"""

from __future__ import annotations

import ast
import importlib.util
import sys

import pytest

from tests.sdk._scan import REPO_ROOT, python_files, rel

SHARED = REPO_ROOT / "skills" / "_sdk" / "r_scripts"
SCRNA = REPO_ROOT / "skills" / "singlecell" / "scrna"


def _load(path):
    name = f"_r_paths_probe_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as exc:
        if exc.name and not exc.name.startswith(("skills", "omicsclaw")):
            pytest.skip(f"{path.name} needs {exc.name}")
        raise
    finally:
        sys.modules.pop(name, None)
    return module


def test_sc_enrichment_keeps_both_directories():
    script = SCRNA / "sc-enrichment" / "_api.py"
    module = _load(script)
    assert module.R_SCRIPTS_DIR == script.parent / "rscripts"
    assert module.R_SCRIPTS_PROJECT_DIR == SHARED


@pytest.mark.parametrize(
    "script",
    [
        SCRNA / "sc-pseudotime" / "_api.py",
        SCRNA / "sc-differential-abundance" / "_api.py",
    ],
    ids=lambda p: p.name,
)
def test_module_constants_point_at_the_shared_directory(script):
    assert _load(script).R_SCRIPTS_DIR == SHARED


def test_the_shared_directory_is_imported_only_under_its_alias():
    unaliased = []
    for path in python_files("skills"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module == "skills._sdk.r_script_runner":
                for alias in node.names:
                    if alias.name == "R_SCRIPTS_DIR" and alias.asname != "_SDK_R_SCRIPTS_DIR":
                        unaliased.append(f"{rel(path)}:{node.lineno}")
    assert unaliased == []


def test_no_code_builds_the_old_path():
    needle = '"omicsclaw" / ' + '"r_scripts"'
    offenders = [
        rel(p) for p in python_files("skills", "omicsclaw", "tests", "templates", "scripts")
        if needle in p.read_text(encoding="utf-8")
    ]
    assert offenders == []
