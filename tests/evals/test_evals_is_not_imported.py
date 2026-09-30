"""Nothing in ``omicsclaw/`` outside ``omicsclaw/evals/`` imports the eval package.

The eval package sits above the entry layer: it assembles deployments
the way a surface does. A production module importing it would make the
test harness part of the product.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "omicsclaw"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


def test_no_production_module_imports_omicsclaw_evals():
    offenders = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if (PACKAGE / "evals") in path.parents:
            continue
        for name in _imports(path):
            if name == "omicsclaw.evals" or name.startswith("omicsclaw.evals."):
                offenders.append(f"{path.relative_to(PACKAGE)} imports {name}")
    assert not offenders, offenders


def test_the_eval_package_imports_no_skill_code():
    offenders = [
        f"{path.name} imports {name}"
        for path in sorted((PACKAGE / "evals").rglob("*.py"))
        for name in _imports(path)
        if name == "skills" or name.startswith("skills.")
    ]
    assert not offenders, offenders
