"""No module that defines HTTP routes inside a function postpones annotations.

``omicsclaw/entry/desktop/server.py`` imports FastAPI inside
``create_desktop_app`` so that importing the package needs no web
framework, which puts every route handler, and the ``Request`` name its
parameter is annotated with, inside that function. With
``from __future__ import annotations`` the annotation is the *string*
``"Request"``; FastAPI resolves it against the module's globals, where no
``Request`` exists, and falls back to treating ``request`` as a required
query parameter. Every route then answered 422 over real HTTP, while the
HTTP tests that would have shown it were skipped wherever FastAPI was not
installed.

This guard is a source scan, so it holds in every interpreter.
"""

from __future__ import annotations

import ast
import pathlib

PACKAGE = pathlib.Path(__file__).resolve().parents[2] / "omicsclaw"

ROUTE_DECORATORS = frozenset(
    {
        "api_route",
        "delete",
        "get",
        "head",
        "options",
        "patch",
        "post",
        "put",
        "route",
        "websocket",
    }
)


def _postpones_annotations(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        and any(alias.name == "annotations" for alias in node.names)
        for node in tree.body
    )


def _is_route_decorator(decorator: ast.expr) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return isinstance(target, ast.Attribute) and target.attr in ROUTE_DECORATORS


def _nested_routes(tree: ast.Module) -> list[str]:
    """Names of route handlers defined inside another function's body."""
    found: list[str] = []
    functions = (ast.FunctionDef, ast.AsyncFunctionDef)
    for outer in ast.walk(tree):
        if not isinstance(outer, functions):
            continue
        for inner in ast.walk(outer):
            if inner is outer or not isinstance(inner, functions):
                continue
            if any(_is_route_decorator(d) for d in inner.decorator_list):
                found.append(f"{outer.name}.{inner.name}")
    return found


def offenders(root: pathlib.Path) -> list[str]:
    bad: list[str] = []
    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "annotations" not in source:
            continue
        tree = ast.parse(source, filename=str(path))
        if _postpones_annotations(tree) and _nested_routes(tree):
            bad.append(str(path.relative_to(root.parent)))
    return bad


def test_no_module_with_nested_routes_postpones_annotations():
    assert offenders(PACKAGE) == []


def test_the_desktop_server_is_one_of_the_modules_this_scans():
    """Not vacuous: the scan does find the desktop server's routes."""
    tree = ast.parse((PACKAGE / "entry" / "desktop" / "server.py").read_text("utf-8"))
    routes = _nested_routes(tree)
    assert "create_desktop_app.chat_stream" in routes
    assert "create_desktop_app.chat_permission" in routes
    assert not _postpones_annotations(tree)


def test_the_guard_catches_the_shape_it_exists_for(tmp_path: pathlib.Path):
    package = tmp_path / "omicsclaw"
    package.mkdir()
    (package / "bad.py").write_text(
        "from __future__ import annotations\n"
        "def create():\n"
        "    from fastapi import FastAPI, Request\n"
        "    api = FastAPI()\n"
        "    @api.post('/x')\n"
        "    async def x(request: Request):\n"
        "        return {}\n"
        "    return api\n",
        encoding="utf-8",
    )
    (package / "fine.py").write_text(
        "from __future__ import annotations\n"
        "def helper():\n"
        "    def inner():\n"
        "        return 1\n"
        "    return inner\n",
        encoding="utf-8",
    )
    assert offenders(package) == ["omicsclaw/bad.py"]
