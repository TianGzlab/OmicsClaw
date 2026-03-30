"""Skill interface contract for OmicsClaw analysis skills.

Defines the expected interface that every skill script should follow.
Since skills run as isolated subprocesses, this Protocol is used for
**static type checking** (mypy/pyright) and **runtime validation**
via ``validate_skill_module()``, not for inheritance.

Usage for static checking::

    from omicsclaw.core.skill_protocol import SkillModule
    mod: SkillModule = importlib.import_module("skills.spatial.spatial_preprocess")

Usage for runtime validation::

    from omicsclaw.core.skill_protocol import validate_skill_module
    report = validate_skill_module(Path("skills/spatial/spatial-preprocess/spatial_preprocess.py"))
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Protocol definition (for static type checkers)
# ---------------------------------------------------------------------------


@runtime_checkable
class SkillModule(Protocol):
    """Expected interface for an OmicsClaw skill module.

    Every skill script should define at minimum:
    - ``SKILL_NAME``  — kebab-case identifier (e.g. ``"spatial-preprocess"``)
    - ``SKILL_VERSION`` — semver string (e.g. ``"0.3.0"``)
    - ``main()``       — CLI entry point (called via ``if __name__ == "__main__"``)
    """

    SKILL_NAME: str
    SKILL_VERSION: str

    def main(self) -> None: ...


# ---------------------------------------------------------------------------
# AST-based validation (no imports needed, safe for any skill)
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of validating a single skill script."""

    path: Path
    skill_name: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def summary_line(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        n_warn = len(self.warnings)
        extra = f" ({n_warn} warning{'s' if n_warn != 1 else ''})" if n_warn else ""
        name = self.skill_name or self.path.stem
        return f"  [{status}] {name}{extra}"


def validate_skill_module(script_path: Path) -> ValidationResult:
    """Validate a skill script against the OmicsClaw conventions.

    Uses AST parsing — does NOT import the module, so it's safe to run
    on scripts with heavy dependencies (torch, scanpy, etc.).

    Checks:
        - SKILL_NAME constant defined
        - SKILL_VERSION constant defined
        - main() function defined
        - write_report() function defined (warning if missing)
        - generate_figures() or similar function (warning if missing)
        - --input, --output, --demo in argparse (warning if missing)
    """
    result = ValidationResult(path=script_path)

    if not script_path.exists():
        result.errors.append(f"File not found: {script_path}")
        return result

    source = script_path.read_text(encoding="utf-8")

    try:
        tree = ast.parse(source, filename=str(script_path))
    except SyntaxError as e:
        result.errors.append(f"Syntax error: {e}")
        return result

    # Collect top-level names
    top_assigns: dict[str, str] = {}  # name -> value repr
    top_functions: set[str] = set()

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if isinstance(node.value, ast.Constant):
                        top_assigns[target.id] = str(node.value.value)
        if isinstance(node, ast.FunctionDef):
            top_functions.add(node.name)

    # --- Required: SKILL_NAME ---
    if "SKILL_NAME" in top_assigns:
        result.skill_name = top_assigns["SKILL_NAME"]
        result.info.append(f"SKILL_NAME = {result.skill_name!r}")
    else:
        result.errors.append("Missing SKILL_NAME constant")

    # --- Required: SKILL_VERSION ---
    if "SKILL_VERSION" in top_assigns:
        result.info.append(f"SKILL_VERSION = {top_assigns['SKILL_VERSION']!r}")
    else:
        result.errors.append("Missing SKILL_VERSION constant")

    # --- Required: main() ---
    if "main" in top_functions:
        result.info.append("main() defined")
    else:
        result.errors.append("Missing main() function")

    # --- Recommended: write_report() or write_*_report() ---
    report_funcs = [f for f in top_functions if "report" in f.lower() and "write" in f.lower()]
    if report_funcs:
        result.info.append(f"Report function: {report_funcs[0]}")
    else:
        result.warnings.append("No write_report() or write_*_report() function found")

    # --- Recommended: generate_figures() or generate_*_figures() ---
    fig_funcs = [f for f in top_functions if "figure" in f.lower() or "fig" in f.lower()]
    if fig_funcs:
        result.info.append(f"Figure function: {fig_funcs[0]}")
    else:
        result.warnings.append("No generate_figures() function found")

    # --- Recommended: --input, --output, --demo args ---
    has_input = "--input" in source or '"input"' in source
    has_output = "--output" in source or '"output"' in source
    has_demo = "--demo" in source
    if not has_input:
        result.warnings.append("No --input CLI argument detected")
    if not has_output:
        result.warnings.append("No --output CLI argument detected")
    if not has_demo:
        result.warnings.append("No --demo CLI argument detected")

    # --- Info: demo data function ---
    demo_funcs = [f for f in top_functions if "demo" in f.lower()]
    if demo_funcs:
        result.info.append(f"Demo function: {demo_funcs[0]}")

    return result
