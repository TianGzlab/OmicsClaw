"""The step runner's ``reference``: what the step functions and validate checks accept and do.

Rendered from the functions' own signatures and docstrings, read with
:mod:`ast` from their source files, so it always describes the code that is
installed. ``load_demo`` is followed by the registered demo datasets.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

from skills._sdk.notebook import _apidoc, checks
from skills._sdk.notebook import __all__ as STEP_FUNCTIONS
from skills._sdk.notebook._io import DEMOS
from skills._sdk.notebook.contract import LAYOUT

HEADER = """\
Step functions: from skills._sdk.notebook import {steps}
Validate checks: from skills._sdk.notebook.checks import {checks}

Paths: read_input takes a path from the project root (data/..., results/<NN_slug>/tables/...);
write_output and check_files take one inside this module's results, starting with {folders}.
A step finds its module from its own file name, whatever the working directory."""


def names() -> list[str]:
    """Every function the reference covers: the step functions, then the checks."""
    return list(STEP_FUNCTIONS) + list(checks.__all__)


def _function(name: str):
    if name in STEP_FUNCTIONS:
        import skills._sdk.notebook as facade

        return getattr(facade, name)
    return getattr(checks, name)


def _node(function) -> ast.FunctionDef:
    source = Path(inspect.getsourcefile(function) or "")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function.__name__:
            return node
    raise LookupError(f"{function.__name__} is not a top-level function of {source}")


def entry(name: str) -> str:
    """One function's signature and docstring, indented under it."""
    node = _node(_function(name))
    text = [_apidoc.signature(node), textwrap.indent(ast.get_docstring(node) or "", "    ")]
    if name == "load_demo":
        text.append("    Registered demo datasets:")
        text.extend(f"      {demo}: {info['about']}" for demo, info in DEMOS.items())
    return "\n".join(text)


def render(name: str | None = None) -> str:
    """The whole reference, or the entry of the function *name*.

    :raises LookupError: *name* is not a step function or a check.
    """
    if name is not None:
        if name not in names():
            raise LookupError(f"no step function or check named {name!r}; the reference covers: {', '.join(names())}")
        return entry(name)
    folders = ", ".join(f"{folder}/" for folder in LAYOUT["output_dirs"])
    parts = [HEADER.format(steps=", ".join(STEP_FUNCTIONS), checks=", ".join(checks.__all__), folders=folders)]
    parts.extend(entry(function) for function in names())
    return "\n\n".join(parts)
