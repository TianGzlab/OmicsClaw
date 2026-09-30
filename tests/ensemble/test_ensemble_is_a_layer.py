"""``omicsclaw.ensemble`` sits below ``entry`` and splits into two runtimes.

Its agent half (``tool``, ``runner``, ``resources``, ``execution``, ``store``,
``space``) runs in the agent process and may use ``schema``, ``tools`` and
``skills``. Its scoring half (the package ``__init__``, ``metrics/*`` and
``_supervise.py``) runs in the execution environment, possibly under an older
interpreter without the agent's dependencies, so it must not pull in any
agent-side module; ``_supervise.py`` is run by file path and may use only the
standard library.

Two isolation rules are checked on what is actually imported, in a
subprocess, not only on spelling. The agent process must not load numpy,
pandas or scanpy for importing the tool — those belong in the scoring
subprocess. And nothing on the run path may import ``evaluation``, which is
where ground truth lives: trials, the tool and the panels never see it.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "omicsclaw" / "ensemble"

ALLOWED_AGENT_SIDE = ("omicsclaw.schema", "omicsclaw.tools", "omicsclaw.skills", "omicsclaw.ensemble")
FORBIDDEN = (
    "omicsclaw.entry", "omicsclaw.engine", "omicsclaw.provider", "omicsclaw.sandbox",
    "omicsclaw.runtime", "omicsclaw.common",
)
RUN_PATH = ("tool", "runner", "space", "store", "execution", "resources")


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = list(path.relative_to(REPO).with_suffix("").parts[:-1])
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - (node.level - 1)]
                names.append(".".join([*base, node.module] if node.module else base))
            elif node.module:
                names.append(node.module)
    return names


def _modules() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


@pytest.mark.parametrize("path", _modules(), ids=lambda p: str(p.relative_to(PACKAGE)))
def test_only_permitted_omicsclaw_packages_are_imported(path):
    for name in _imports(path):
        if not name.startswith("omicsclaw"):
            continue
        assert not name.startswith(FORBIDDEN), f"{path.name} imports {name}"
        assert name.startswith(ALLOWED_AGENT_SIDE), f"{path.name} imports {name}"


@pytest.mark.parametrize(
    "path",
    [PACKAGE / "__init__.py", *sorted((PACKAGE / "metrics").glob("*.py"))],
    ids=lambda p: str(p.relative_to(PACKAGE)),
)
def test_the_scoring_half_imports_nothing_from_the_agent_side(path):
    for name in _imports(path):
        if name.startswith("omicsclaw"):
            assert name.startswith("omicsclaw.ensemble.metrics"), f"{path.name} imports {name}"


def test_the_supervisor_uses_only_the_standard_library():
    stdlib = set(sys.stdlib_module_names)
    for name in _imports(PACKAGE / "_supervise.py"):
        assert name.split(".")[0] in stdlib, name


@pytest.mark.parametrize("module", RUN_PATH + ("metrics.spatial", "metrics.panel", "metrics.score"))
def test_nothing_on_the_run_path_imports_evaluation(module):
    path = PACKAGE / (module.replace(".", "/") + ".py")
    assert not any("evaluation" in name for name in _imports(path)), module


def _probe(source: str) -> str:
    completed = subprocess.run(
        [sys.executable, "-c", source], capture_output=True, text=True, cwd=REPO, timeout=120
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def test_importing_the_tool_loads_no_numerical_library_and_no_ground_truth():
    loaded = _probe(
        "import sys, omicsclaw.ensemble.tool, omicsclaw.ensemble.runner;"
        "print(sorted(m for m in ('numpy', 'pandas', 'scanpy', 'anndata', 'omicsclaw.ensemble.evaluation',"
        " 'omicsclaw.entry') if m in sys.modules))"
    )
    assert loaded == "[]"


def test_importing_the_package_loads_nothing_else():
    loaded = _probe(
        "import sys, omicsclaw.ensemble;"
        "print(sorted(m for m in sys.modules if m.startswith('omicsclaw.') and m != 'omicsclaw.ensemble'"
        " and m != 'omicsclaw.version'))"
    )
    assert loaded == "[]"


# ---- the tuning package -------------------------------------------------------------------

TUNING = PACKAGE / "tuning"
EXECUTION_SIDE = ("subsample", "stability", "markers", "inspect")


@pytest.mark.parametrize("name", EXECUTION_SIDE)
def test_the_tuning_subprocess_modules_import_only_metrics_and_each_other(name):
    """They run under the skill interpreter, like the scoring half."""
    allowed = ("omicsclaw.ensemble.metrics", *(f"omicsclaw.ensemble.tuning.{m}" for m in EXECUTION_SIDE))
    for imported in _imports(TUNING / f"{name}.py"):
        if imported.startswith("omicsclaw"):
            assert imported.startswith(allowed), f"{name} imports {imported}"


@pytest.mark.parametrize("path", sorted(TUNING.glob("*.py")), ids=lambda p: p.name)
def test_no_tuning_module_reads_ground_truth_or_a_provider(path):
    for imported in _imports(path):
        assert "evaluation" not in imported, path.name
        assert not imported.startswith("omicsclaw.provider"), path.name


def test_importing_the_tuning_tools_loads_no_numerical_library():
    loaded = _probe(
        "import sys, omicsclaw.ensemble.tuning.tools, omicsclaw.ensemble.tuning.pipeline;"
        "print(sorted(m for m in ('numpy', 'pandas', 'scanpy', 'anndata', 'omicsclaw.ensemble.evaluation',"
        " 'omicsclaw.entry', 'omicsclaw.provider') if m in sys.modules))"
    )
    assert loaded == "[]"


def test_the_tuning_package_init_imports_nothing():
    assert [n for n in _imports(TUNING / "__init__.py") if n.startswith("omicsclaw")] == []
