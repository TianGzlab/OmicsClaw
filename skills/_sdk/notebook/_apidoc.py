"""The generated ``## API`` section of a skill's ``SKILL.md``.

The section is rendered from the skill's ``_api.py`` with :mod:`ast` only,
so neither rendering nor checking imports the library. For every name in
``__all__``, in order, it gives a ``### `name(signature)``` heading, with
annotations and defaults as written, followed by the function's docstring
as written (dedented). The section sits between two marker comments.
"""

from __future__ import annotations

import ast
from pathlib import Path

BEGIN = "<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->"
END = "<!-- api:end -->"


class ApiError(ValueError):
    """``_api.py`` or ``SKILL.md`` cannot give a valid API section."""


def _functions(api: Path) -> tuple[list[str], dict[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    tree = ast.parse(api.read_text(encoding="utf-8"))
    declared: list[str] | None = None
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions[node.name] = node
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets) and node.value is not None:
            declared = [str(name) for name in ast.literal_eval(node.value)]
    if declared is None:
        raise ApiError(f"{api}: no __all__")
    return declared, functions


def library_problems(api: Path) -> list[str]:
    """Names in ``__all__`` that are not documented top-level functions."""
    declared, functions = _functions(api)
    problems = []
    for name in declared:
        node = functions.get(name)
        if node is None:
            problems.append(f"{name} is in __all__ but is not a top-level function")
        elif not ast.get_docstring(node):
            problems.append(f"{name} has no docstring")
    return problems


def signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    text = f"{node.name}({ast.unparse(node.args)})"
    if node.returns is not None:
        text += f" -> {ast.unparse(node.returns)}"
    return text


def render(api: Path) -> str:
    """The API section, markers included, for the library at *api*."""
    problems = library_problems(api)
    if problems:
        raise ApiError(f"{api}: " + "; ".join(problems))
    declared, functions = _functions(api)
    parts = [BEGIN, ""]
    for name in declared:
        node = functions[name]
        parts.append(f"### `{signature(node)}`")
        parts.append("")
        parts.append(ast.get_docstring(node) or "")
        parts.append("")
    parts.append(END)
    return "\n".join(parts)


def _span(text: str, source: Path) -> tuple[int, int]:
    begins = text.count(BEGIN)
    ends = text.count(END)
    if begins != 1 or ends != 1:
        raise ApiError(f"{source}: expected one API section between the markers, found {begins} begin and {ends} end")
    start = text.index(BEGIN)
    end = text.index(END, start) + len(END)
    return start, end


def current(skill_md: Path) -> str:
    text = skill_md.read_text(encoding="utf-8")
    start, end = _span(text, skill_md)
    return text[start:end]


def check(skill_dir: Path) -> list[str]:
    """Why ``SKILL.md``'s API section does not match ``_api.py``; empty when it does."""
    api = skill_dir / "_api.py"
    skill_md = skill_dir / "SKILL.md"
    if not api.is_file():
        return [f"{skill_dir} has no _api.py"]
    problems = library_problems(api)
    if problems:
        return problems
    try:
        existing = current(skill_md)
    except (ApiError, OSError) as exc:
        return [str(exc)]
    text = skill_md.read_text(encoding="utf-8")
    if text.count("\n## API\n") != 1:
        problems.append("SKILL.md should have exactly one `## API` heading")
    if existing != render(api):
        problems.append("the API section differs from _api.py; regenerate it with `run.py api <skill dir> --write`")
    return problems


def write(skill_dir: Path) -> bool:
    """Regenerate the API section in place; return whether ``SKILL.md`` changed.

    Without markers the section goes right after the ``## API`` heading.
    """
    skill_md = skill_dir / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    rendered = render(skill_dir / "_api.py")
    if BEGIN in text or END in text:
        start, end = _span(text, skill_md)
        updated = text[:start] + rendered + text[end:]
    else:
        heading = "\n## API\n"
        if text.count(heading) != 1:
            raise ApiError(f"{skill_md}: add one `## API` heading where the generated section should go")
        at = text.index(heading) + len(heading)
        updated = text[:at] + "\n" + rendered + "\n\n" + text[at:].lstrip("\n")
    if updated == text:
        return False
    skill_md.write_text(updated, encoding="utf-8")
    return True
