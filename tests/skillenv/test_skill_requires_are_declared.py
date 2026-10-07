"""Every optional backend a skill's code asks for is declared by that skill (plan 0061 case 7).

For each skill, the string arguments of dependency-API calls in its main
scripts, ``_api.py``, and the ``skills.<domain>._lib`` modules they import
directly are collected with plan 0062's F29 rule: ``require``,
``is_available``, ``install_hint`` and ``get_dependency`` taken from
``skills._sdk.deps``, attribute calls on a ``skills._sdk.deps`` alias, and
``get`` imported from ``skills._sdk.deps`` (a bare ``get`` elsewhere is
``dict.get``). Each name is resolved against the registry by key,
normalised key and module; the key must appear in that skill's own
``## Dependencies``.

The rerun at P1 start (after 0062 stage two) found ten skills: the eight of
plan 0061 F58 plus ``sc-enrichment`` and ``spatial-enrichment`` → gseapy,
visible now because the F29 rule counts ``get`` imported from the registry
module. Six were real omissions and were declared in P0b; the four
scrublet hits are listed in ``EXCEPTIONS``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from omicsclaw.skillenv.registry import parse_dependencies, read_registry, resolve

from .conftest import REAL_REGISTRY, REPO

EXCLUDED_MODULES = {
    "skills/singlecell/_lib/preflight.py": (
        "Checks the backends of every method of every single-cell skill in one "
        "place and is imported by all of them; at module granularity it would "
        "charge each skill with every other skill's backends."
    ),
}

EXCEPTIONS = {
    (skill, "scrublet"): (
        "Imports skills/singlecell/_lib/qc.py only for QC metrics, filtering and "
        "plots; the scrublet calls in that module are in calculate_doublet_scores "
        "and run_scrublet_detection, which only sc-doublet-detection calls."
    )
    for skill in ("sc-qc", "sc-filter", "sc-preprocessing", "scatac-preprocessing")
}
"""(skill directory name, registry key) pairs a module-level scan reports but the skill cannot reach."""

_API = {"require", "is_available", "install_hint", "get_dependency"}


def _call_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    aliases: set[str] = set()
    direct: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "skills._sdk":
            aliases |= {a.asname or a.name for a in node.names if a.name == "deps"}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "skills._sdk.deps":
            direct |= {a.asname or a.name for a in node.names if a.name in _API | {"get"}}
        elif isinstance(node, ast.Import):
            aliases |= {a.asname for a in node.names if a.name == "skills._sdk.deps" and a.asname}
    names: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in direct:
            names.add(node.args[0].value)
        elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in aliases:
            names.add(node.args[0].value)
    return names


def _lib_modules(script: Path) -> set[Path]:
    """The ``skills.<domain>._lib`` modules *script* imports directly."""
    found: set[Path] = set()
    for node in ast.walk(ast.parse(script.read_text(encoding="utf-8"))):
        modules: list[tuple[str, list[str]]] = []
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append((node.module, [a.name for a in node.names]))
        elif isinstance(node, ast.Import):
            modules.extend((a.name, []) for a in node.names)
        for module, names in modules:
            parts = module.split(".")
            if len(parts) < 3 or parts[0] != "skills" or parts[2] != "_lib":
                continue
            base = REPO.joinpath(*parts)
            if base.with_suffix(".py").is_file():
                found.add(base.with_suffix(".py"))
                continue
            for name in names:
                if (base / f"{name}.py").is_file():
                    found.add(base / f"{name}.py")
                elif (base / "__init__.py").is_file():
                    found.add(base / "__init__.py")
            if not names and (base / "__init__.py").is_file():
                found.add(base / "__init__.py")
    return found


def undeclared() -> dict[tuple[str, str], set[str]]:
    """(skill, key) → where the call was found, for every call the skill does not declare."""
    registry = read_registry(REAL_REGISTRY)
    out: dict[tuple[str, str], set[str]] = {}
    for skill_md in sorted((REPO / "skills").rglob("SKILL.md")):
        directory = skill_md.parent
        declared = {
            resolve(name, registry).key or name
            for name in parse_dependencies(skill_md.read_text(encoding="utf-8"), source=skill_md)
        }
        for script in sorted(p for p in directory.glob("*.py")
                             if not p.name.startswith("_") or p.name == "_api.py"):
            for source in {script} | _lib_modules(script):
                where = source.relative_to(REPO).as_posix()
                if where in EXCLUDED_MODULES:
                    continue
                for name in _call_names(source):
                    key = resolve(name, registry).key or name
                    if key not in declared:
                        out.setdefault((directory.name, key), set()).add(where)
    return out


def test_every_called_backend_is_declared_by_its_skill():
    missing = {pair: sorted(where) for pair, where in undeclared().items() if pair not in EXCEPTIONS}
    assert missing == {}


def test_every_exception_is_still_needed():
    """A stale exception — a skill that no longer exists, or a hit that went away — fails."""
    found = set(undeclared())
    assert set(EXCEPTIONS) - found == set()


def test_exclusions_and_exceptions_carry_reasons():
    for reason in (*EXCLUDED_MODULES.values(), *EXCEPTIONS.values()):
        assert len(reason) > 40
    for path in EXCLUDED_MODULES:
        assert (REPO / path).is_file()


def test_an_aliased_deps_module_is_collected(tmp_path):
    source = tmp_path / "x.py"
    source.write_text(
        "from skills._sdk import deps as dm\n"
        "from skills._sdk.deps import get\n"
        "def f():\n"
        "    dm.require('louvain')\n"
        "    get('gseapy')\n"
        "    {}.get('not-a-dependency')\n",
        encoding="utf-8",
    )
    assert _call_names(source) == {"louvain", "gseapy"}


def test_scan_includes_api_and_its_direct_domain_helpers(tmp_path, monkeypatch):
    monkeypatch.setitem(undeclared.__globals__, "REPO", tmp_path)
    directory = tmp_path / "skills" / "singlecell" / "test-skill"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text("## Dependencies\n\n`numpy`\n")
    (directory / "_api.py").write_text(
        "from skills._sdk.deps import require\n"
        "from skills.singlecell._lib.helper import compute\n"
        "def analyze():\n    require('scanpy')\n    require('not-declared')\n"
    )
    helper = tmp_path / "skills" / "singlecell" / "_lib" / "helper.py"
    helper.parent.mkdir()
    helper.write_text("from skills._sdk.deps import require\nrequire('scrublet')\n")
    assert undeclared() == {
        ("test-skill", "scanpy"): {"skills/singlecell/test-skill/_api.py"},
        ("test-skill", "not-declared"): {"skills/singlecell/test-skill/_api.py"},
        ("test-skill", "scrublet"): {"skills/singlecell/_lib/helper.py"},
    }


@pytest.mark.parametrize("skill", ["spatial-domains"])
def test_the_scan_sees_spatial_domains_calling_cellcharter(skill):
    """The declaration P0b added is load-bearing: without it this pair would be reported."""
    registry = read_registry(REAL_REGISTRY)
    script = REPO / "skills" / "spatial" / skill / "spatial_domains.py"
    names = set().union(*(_call_names(p) for p in {script} | _lib_modules(script)))
    assert "cellcharter" in {resolve(n, registry).key for n in names}
