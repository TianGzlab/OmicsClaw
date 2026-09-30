"""Static import scanning shared by the ``skills/_sdk`` boundary tests.

Everything here reads source with :mod:`ast` and never imports the scanned
modules. An "import" is an ``import`` statement, a ``from … import …``
statement (relative ones expanded against the file's package path), or a
string-literal first argument to ``__import__``, ``importlib.import_module``
or ``importlib.util.find_spec`` — the last three are how
``skills/spatial/_lib/dependency_manager.py`` once reached
``omicsclaw.core.external_env`` without an import statement (plan 0062 F3).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_DYNAMIC_IMPORTERS = {"__import__", "import_module", "find_spec"}


@dataclass(frozen=True)
class ImportRef:
    """One import found in a file: the module, the names taken from it, and where."""

    path: str
    lineno: int
    module: str
    names: tuple[str, ...] = ()


def python_files(*roots: str) -> list[Path]:
    """Every ``.py`` file under the given repo-relative roots, skipping caches."""
    out: list[Path] = []
    for root in roots:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        out.extend(
            p for p in sorted(base.rglob("*.py"))
            if "__pycache__" not in p.parts and not any(part.startswith(".") for part in p.relative_to(REPO_ROOT).parts)
        )
    return out


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def is_test_path(path: Path) -> bool:
    """True for anything inside a ``tests`` directory."""
    return "tests" in path.relative_to(REPO_ROOT).parts[:-1]


def _package_of(path: Path) -> list[str]:
    parts = list(path.relative_to(REPO_ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        return parts[:-1]
    return parts[:-1]


def _dynamic_name(call: ast.Call) -> str | None:
    func = call.func
    name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
    if name not in _DYNAMIC_IMPORTERS or not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def imports_of(path: Path) -> list[ImportRef]:
    """All imports in *path*, including lazy ones inside functions."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    where = rel(path)
    refs: list[ImportRef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                refs.append(ImportRef(where, node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package = _package_of(path)
                base = package[: len(package) - (node.level - 1)] if node.level > 1 else package
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            refs.append(ImportRef(where, node.lineno, module, tuple(a.name for a in node.names)))
        elif isinstance(node, ast.Call):
            name = _dynamic_name(node)
            if name:
                refs.append(ImportRef(where, node.lineno, name))
    return refs


def targets(ref: ImportRef) -> list[str]:
    """The dotted modules an import can bind: the module, and ``module.name`` for a bare package."""
    if ref.module in {"skills", "omicsclaw"} and ref.names:
        return [f"{ref.module}.{n}" for n in ref.names if n != "*"]
    return [ref.module]


def within(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


# ---- "the module exists on disk" -------------------------------------------

def _namespace_dir(parts: list[str]) -> bool:
    """``skills`` and ``skills/<domain>`` are namespace directories with no ``__init__.py``."""
    return parts[0] == "skills" and len(parts) <= 2


def module_exists(module: str) -> bool:
    """A module exists when its ``.py`` file does, or its directory is a package.

    Only ``.py`` files and directories with ``__init__.py`` count (plus the two
    known namespace levels), so a leftover ``__pycache__`` or empty directory
    never makes a deleted module look present.
    """
    parts = module.split(".")
    base = REPO_ROOT.joinpath(*parts)
    if base.with_suffix(".py").is_file():
        return True
    if base.is_dir() and ((base / "__init__.py").is_file() or _namespace_dir(parts)):
        return True
    return False


def _top_level_bindings(init: Path) -> set[str]:
    tree = ast.parse(init.read_text(encoding="utf-8"))
    bound: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        bound.add(n.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            bound.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split(".")[0])
    return bound


def missing_targets(ref: ImportRef) -> list[str]:
    """What an ``omicsclaw.*`` or ``skills.*`` import names that is not on disk."""
    if not ref.module:
        return []
    if not module_exists(ref.module):
        return [ref.module]
    missing: list[str] = []
    parts = ref.module.split(".")
    package_dir = REPO_ROOT.joinpath(*parts)
    if package_dir.is_dir():
        init = package_dir / "__init__.py"
        bound = _top_level_bindings(init) if init.is_file() else set()
        for name in ref.names:
            if name == "*" or name in bound or module_exists(f"{ref.module}.{name}"):
                continue
            missing.append(f"{ref.module}.{name}")
    return missing
