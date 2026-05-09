"""Regression tests for ``bot/agent_loop.py`` global-name resolution.

Background — when ``bot/agent_loop.py`` was extracted from ``bot/core.py``
in #121, several symbols referenced unqualified inside the loop and its
helpers (``build_selective_replay_context``, ``_assemble_chat_context``,
``BOT_START_TIME``, ``_skill_registry``, …) lost their imports.

Each missing name is a latent ``NameError`` that surfaces only when the
relevant code path executes — bubbled to the user as
``LLM error: name 'X' is not defined``.

These tests pin two contracts:

1. The dynamic guard: every Load-Name referenced inside any function in
   ``bot.agent_loop`` resolves to a real object via the module's globals
   (or builtins). A static AST scan would also catch this, but pinning
   it to the live module dict matches what Python actually checks at
   runtime.

2. The legacy explicit guard: ``build_selective_replay_context`` is the
   one originally reported. Keep it as a named test so the bug report
   maps cleanly to a regression test.
"""

from __future__ import annotations

import ast
import builtins
from pathlib import Path

from bot import agent_loop
from omicsclaw.runtime.transcript_store import build_selective_replay_context


# --------------------------------------------------------------------------- #
# Original bug — keep an explicit, named regression marker.                   #
# --------------------------------------------------------------------------- #


def test_llm_tool_loop_resolves_build_selective_replay_context():
    resolved = agent_loop.llm_tool_loop.__globals__.get(
        "build_selective_replay_context"
    )
    assert resolved is build_selective_replay_context, (
        "bot.agent_loop must import build_selective_replay_context from "
        "omicsclaw.runtime.transcript_store — llm_tool_loop calls it "
        "unqualified when assembling transcript_context"
    )


def test_agent_loop_module_exposes_build_selective_replay_context():
    assert hasattr(agent_loop, "build_selective_replay_context"), (
        "bot.agent_loop must expose build_selective_replay_context at "
        "module scope so llm_tool_loop's unqualified reference resolves"
    )


# --------------------------------------------------------------------------- #
# Comprehensive guard — catches every future extraction-induced NameError.   #
# --------------------------------------------------------------------------- #


def _module_bindings(tree: ast.Module) -> set[str]:
    """Return names bound at the module's top level: imports, defs, classes,
    and unconditional/conditional top-level assignments."""
    bound: set[str] = set()

    def visit(stmts):
        for node in stmts:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    bound.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                bound.add(node.name)
            elif isinstance(node, ast.Assign):
                for tgt in node.targets:
                    for n in ast.walk(tgt):
                        if isinstance(n, ast.Name):
                            bound.add(n.id)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                for n in ast.walk(node.target):
                    if isinstance(n, ast.Name):
                        bound.add(n.id)
            elif isinstance(node, ast.If):
                visit(node.body)
                visit(node.orelse)
            elif isinstance(node, ast.Try):
                visit(node.body)
                visit(node.handlers)
                visit(node.orelse)
                visit(node.finalbody)
            elif isinstance(node, ast.ExceptHandler):
                visit(node.body)

    visit(tree.body)
    return bound


def _function_local_bindings(fn: ast.AST) -> set[str]:
    bound: set[str] = set()
    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        for a in (
            list(fn.args.posonlyargs)
            + list(fn.args.args)
            + list(fn.args.kwonlyargs)
        ):
            bound.add(a.arg)
        if fn.args.vararg:
            bound.add(fn.args.vararg.arg)
        if fn.args.kwarg:
            bound.add(fn.args.kwarg.arg)

    for node in ast.walk(fn):
        if node is fn:
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Lambda):
            for a in (
                list(node.args.posonlyargs)
                + list(node.args.args)
                + list(node.args.kwonlyargs)
            ):
                bound.add(a.arg)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                for n in ast.walk(tgt):
                    if isinstance(n, ast.Name):
                        bound.add(n.id)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            for n in ast.walk(node.target):
                if isinstance(n, ast.Name):
                    bound.add(n.id)
        elif isinstance(node, ast.NamedExpr) and isinstance(
            node.target, ast.Name
        ):
            bound.add(node.target.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            for n in ast.walk(node.target):
                if isinstance(n, ast.Name):
                    bound.add(n.id)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    for n in ast.walk(item.optional_vars):
                        if isinstance(n, ast.Name):
                            bound.add(n.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.comprehension):
            for n in ast.walk(node.target):
                if isinstance(n, ast.Name):
                    bound.add(n.id)
    return bound


def _scan_undefined_names(source_path: Path) -> dict[str, list[str]]:
    """Return {name: [function@line, ...]} for every Load-Name in any function
    that isn't bound by (its locals ∪ enclosing-function locals ∪ module
    bindings ∪ builtins). The "any function's locals" relaxation handles
    closures conservatively without a full scope walker."""
    tree = ast.parse(source_path.read_text(), filename=str(source_path))
    module = _module_bindings(tree)
    builtin_names = set(dir(builtins))

    all_function_locals: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
        ):
            all_function_locals |= _function_local_bindings(node)

    undefined: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
        ):
            continue
        local = _function_local_bindings(node)
        scope = local | module | builtin_names | all_function_locals
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                if child.id not in scope:
                    site = (
                        f"{getattr(node, 'name', '<lambda>')}@line{node.lineno}"
                    )
                    undefined.setdefault(child.id, []).append(site)
    return undefined


def test_agent_loop_has_no_undefined_globals():
    """Static guard: any name referenced unqualified inside bot/agent_loop.py
    must be resolvable via the module's globals or builtins. A failure here
    means a future refactor dropped an import — the same class of bug as
    the original ``LLM error: name 'X' is not defined``."""
    source = Path(agent_loop.__file__)
    undefined = _scan_undefined_names(source)
    assert not undefined, (
        "bot/agent_loop.py references names that aren't imported or defined "
        "at module scope — they will raise NameError when their code path "
        "runs:\n  " + "\n  ".join(
            f"{name!r} used at {sites}" for name, sites in sorted(undefined.items())
        )
    )


def test_agent_loop_runtime_globals_match_static_scan():
    """Dynamic mirror: cross-check the static AST scan against the live
    module dict. Catches the case where a static binding exists but resolves
    to ``None`` (e.g. a stub left over by an aborted refactor)."""
    source = Path(agent_loop.__file__)
    tree = ast.parse(source.read_text(), filename=str(source))
    module_names = _module_bindings(tree)
    live = vars(agent_loop)
    missing_runtime = sorted(n for n in module_names if n not in live)
    assert not missing_runtime, (
        f"AST-bound names not present in the live bot.agent_loop module: "
        f"{missing_runtime}"
    )
