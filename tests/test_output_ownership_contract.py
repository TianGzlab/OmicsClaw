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


def test_skill_scripts_do_not_write_to_runner_owned_paths():
    """Catch skills that bypass the helper layer and write directly to paths
    the runner owns (e.g., ``(output_dir / "README.md").write_text(...)`` or
    ``_write_text(output_dir / "README.md", ...)``).

    Read-only checks like ``(output_dir / "README.md").exists()`` are allowed
    — the runner writes that file and skills are free to reflect it in their
    summaries.
    """

    runner_owned_constants = {
        "README.md",
        "analysis_notebook.ipynb",
    }
    write_function_names = {"write_text", "write_bytes", "_write_text"}

    def _path_targets_runner_owned(node: ast.AST) -> str | None:
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Div):
            return None
        right = node.right
        if isinstance(right, ast.Constant) and right.value in runner_owned_constants:
            return right.value
        return None

    violations: list[str] = []
    for path in _python_skill_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            func = node.func
            func_name = ""
            if isinstance(func, ast.Attribute):
                func_name = func.attr
            elif isinstance(func, ast.Name):
                func_name = func.id

            if func_name not in write_function_names:
                continue

            # Method form: <path-expr>.write_text(...) — check the receiver.
            if isinstance(func, ast.Attribute):
                target = _path_targets_runner_owned(func.value)
                if target:
                    violations.append(
                        f"{path.relative_to(ROOT)}:{node.lineno} writes runner-owned file via "
                        f"{func_name}: {target!r}"
                    )
                    continue

            # Function form: _write_text(<path-expr>, ...) — check first positional arg.
            if node.args:
                target = _path_targets_runner_owned(node.args[0])
                if target:
                    violations.append(
                        f"{path.relative_to(ROOT)}:{node.lineno} writes runner-owned file via "
                        f"{func_name}: {target!r}"
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
