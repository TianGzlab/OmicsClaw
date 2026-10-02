"""``omicsclaw.skillenv`` sits below ``entry`` and never imports skill code (plan 0061 case 13, §4.11).

It may import the standard library, ``schema``, ``tools`` and ``skills``
(the loader). It must not import ``entry``, ``engine``, ``provider``,
``sandbox`` (a sandbox reaches it as a structural ``BashEnvironment``),
``permission`` or ``common`` — nor the top-level ``skills``
package or anything under it: the dependency registry is read as a file,
because skills and the framework share no code (plan 0062 D3, guard B4).
``omicsclaw.skills`` in turn does not import ``skillenv``; the entry layer
builds the ``use_skill`` callback.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys

import pytest

from .conftest import REPO

PACKAGE = REPO / "omicsclaw" / "skillenv"
ALLOWED = ("omicsclaw.schema", "omicsclaw.tools", "omicsclaw.skills", "omicsclaw.skillenv")


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = list(path.relative_to(REPO).with_suffix("").parts[:-1])
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - (node.level - 1)]
                names.append(".".join([*base, node.module] if node.module else base))
            elif node.module:
                names.append(node.module)
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name in {"__import__", "import_module"} and isinstance(node.args[0].value, str):
                names.append(node.args[0].value)
    return names


def _modules():
    return sorted(PACKAGE.rglob("*.py"))


def test_the_package_exists():
    assert (PACKAGE / "__init__.py").is_file()


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_only_permitted_packages_are_imported(path):
    bad = [
        name for name in _imports(path)
        if (name == "omicsclaw" or name.startswith("omicsclaw.")) and not name.startswith(ALLOWED)
        or name == "skills" or name.startswith("skills.")
    ]
    assert bad == []


def test_the_skills_loader_does_not_import_skillenv():
    for path in sorted((REPO / "omicsclaw" / "skills").rglob("*.py")):
        assert not [n for n in _imports(path) if n.startswith("omicsclaw.skillenv")], path


def test_importing_every_module_loads_no_forbidden_package():
    modules = sorted(
        "omicsclaw.skillenv" + ("" if p.stem == "__init__" else "." + p.stem) for p in _modules()
    )
    code = (
        "import importlib, json, sys\n"
        f"for m in {modules!r}: importlib.import_module(m)\n"
        "print(json.dumps(sorted(sys.modules)))\n"
    )
    env = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run([sys.executable, "-B", "-c", code], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    loaded = json.loads(proc.stdout.strip().splitlines()[-1])
    forbidden = ("omicsclaw.entry", "omicsclaw.engine", "omicsclaw.provider", "omicsclaw.sandbox",
                 "omicsclaw.permission", "omicsclaw.common")
    assert [m for m in loaded if m.startswith(forbidden) or m == "skills" or m.startswith("skills.")] == []
