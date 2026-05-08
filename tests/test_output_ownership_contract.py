from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"

RUNNER_OWNED_HELPERS = {
    "write_standard_run_artifacts",
    "write_output_readme",
    "write_analysis_notebook",
}


def _python_skill_files() -> list[Path]:
    return [
        path
        for path in sorted(SKILLS_DIR.rglob("*.py"))
        if "__pycache__" not in path.parts and not path.name.startswith("test_")
    ]


def test_skill_scripts_do_not_write_runner_owned_output_ux_directly():
    violations: list[str] = []
    for path in _python_skill_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported = {alias.name for alias in node.names}
                forbidden = sorted(imported & RUNNER_OWNED_HELPERS)
                if forbidden:
                    violations.append(
                        f"{path.relative_to(ROOT)} imports runner-owned helper(s): {forbidden}"
                    )
            elif isinstance(node, ast.Call):
                func = node.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name in RUNNER_OWNED_HELPERS:
                    violations.append(
                        f"{path.relative_to(ROOT)} calls runner-owned helper: {name}"
                    )

    assert not violations, "\n".join(violations[:120])


def test_skill_docs_do_not_claim_skills_write_runner_owned_output_ux():
    forbidden_fragments = (
        "skill writes `README.md`",
        "wrapper writes `README.md`",
        "writes `README.md`",
        "write `README.md`",
        "Every successful standard run also writes `reproducibility/analysis_notebook.ipynb`",
        "`analysis_notebook.ipynb` should be written on normal successful runs",
    )

    violations: list[str] = []
    for path in sorted(SKILLS_DIR.rglob("SKILL.md")):
        text = path.read_text(encoding="utf-8")
        for fragment in forbidden_fragments:
            if fragment in text:
                violations.append(
                    f"{path.relative_to(ROOT)} still claims skill-owned runner UX: {fragment}"
                )

    assert not violations, "\n".join(violations[:120])
