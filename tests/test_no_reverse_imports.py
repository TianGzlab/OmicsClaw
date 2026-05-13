"""Architectural guardrail: ``omicsclaw/`` must not import from ``bot/``.

The dependency direction is one-way: user-facing entries (``bot/``,
``omicsclaw/app/``, ``omicsclaw/interactive/``) consume the engine
living in ``omicsclaw/``. The reverse — engine code reaching back
into ``bot/`` — creates cycles, blocks the boundary refactor planned
in ``docs/adr/0001-bot-core-decomposition.md``, and was the root
cause of multiple un-shippable migrations called out in the May 2026
audit.

The guardrail comes in two strengths:

1. **Top-level imports** (``import bot.x`` at module scope). These
   evaluate at import time and create real cycle risk. **Strictly
   forbidden** — this set must always be empty.

2. **Function-body lazy imports** (``import bot.x`` inside a
   ``def``/``async def``). These defer the dependency to call time
   and were used historically to side-step the cycle (see e.g.
   ``omicsclaw/runtime/preflight/sc_batch.py:265-267`` — the author's
   comment names the workaround explicitly). They are **technical
   debt**: tracked in ``GRANDFATHERED_LAZY_IMPORTS``, ratcheted
   monotonically, but do not block the test today.

Phase 1 P0-D landed the policy split (May 2026). Future cleanups
(scheduled as Phase 2 work) move the bot-side helpers into
``omicsclaw/`` so the lazy allowlist can shrink to zero.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOT = REPO_ROOT / "omicsclaw"


# Lazy reverse imports remaining as the bot-side helpers are progressively
# moved into ``omicsclaw/``. All are inside function bodies; none execute
# at import time. Each entry is a deferred dependency the next slice can
# retire by lifting the bot helper into ``omicsclaw/``.
GRANDFATHERED_LAZY_IMPORTS: frozenset[tuple[str, int]] = frozenset(
    {
        # omicsclaw/app/server.py — desktop /bridge/* endpoints reach
        # into bot.channels / bot.run for channel orchestration.
        # Future fix: move CHANNEL_REGISTRY + ChannelManager into
        # omicsclaw/channels/.
        ("omicsclaw/app/server.py", 351),
        ("omicsclaw/app/server.py", 4602),
        ("omicsclaw/app/server.py", 4753),
        ("omicsclaw/app/server.py", 4800),
        ("omicsclaw/app/server.py", 4813),
        ("omicsclaw/app/server.py", 4814),
        # omicsclaw/interactive/{interactive,tui}.py — both surfaces
        # call bot.core.llm_tool_loop directly. Future fix: expose a
        # surface-agnostic entry from omicsclaw.engine.
        ("omicsclaw/interactive/interactive.py", 1379),
        ("omicsclaw/interactive/interactive.py", 1422),
        ("omicsclaw/interactive/tui.py", 580),
        ("omicsclaw/interactive/tui.py", 856),
        ("omicsclaw/interactive/tui.py", 872),
        ("omicsclaw/interactive/tui.py", 1016),
        # omicsclaw/runtime/preflight/sc_batch.py — auto-prepare chain
        # late-imports the bot-side skill runner + tool entry. Future
        # fix: move _run_omics_skill_step into omicsclaw/runtime/, and
        # invert control flow so execute_omicsclaw runs the final step
        # itself.
        ("omicsclaw/runtime/preflight/sc_batch.py", 465),
        ("omicsclaw/runtime/preflight/sc_batch.py", 466),
    }
)


def _is_bot_module(name: str) -> bool:
    return name == "bot" or name.startswith("bot.")


def _import_lineno(node: ast.AST) -> int | None:
    """Return the line number for any bot-module import in *node*, or None."""
    if isinstance(node, ast.ImportFrom):
        if node.module and _is_bot_module(node.module):
            return node.lineno
    elif isinstance(node, ast.Import):
        for alias in node.names:
            if _is_bot_module(alias.name):
                return node.lineno
    return None


def _imports_inside_any_function(tree: ast.AST) -> set[int]:
    """Set of node ``id()``s that live somewhere inside a
    FunctionDef / AsyncFunctionDef body. Class bodies are *not*
    function bodies — class-level statements run at class-definition
    time, which happens at import time, so they count as top-level."""
    inside: set[int] = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for descendant in ast.walk(fn):
            if descendant is fn:
                continue
            inside.add(id(descendant))
    return inside


def _scan(*, lazy: bool) -> set[tuple[str, int]]:
    """Find every bot-module import under SCAN_ROOT.

    ``lazy=False`` returns imports that execute at module-import
    time — module body, class body, or any non-function nesting
    (``if`` / ``try`` at module scope).
    ``lazy=True`` returns imports nested inside any function body
    (sync or async). These defer to call time and don't create
    import-time cycles.
    """
    found: set[tuple[str, int]] = set()
    for path in SCAN_ROOT.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        in_function = _imports_inside_any_function(tree)
        for node in ast.walk(tree):
            lineno = _import_lineno(node)
            if lineno is None:
                continue
            is_lazy = id(node) in in_function
            if is_lazy == lazy:
                found.add((rel, lineno))
    return found


def test_no_top_level_reverse_imports() -> None:
    """Module-scope ``import bot.x`` is strictly forbidden — these
    evaluate at import time and create real cycle risk."""
    top_level = _scan(lazy=False)
    assert not top_level, (
        "Top-level reverse imports introduced (omicsclaw/ → bot/). "
        "These run at import time and create cycle risk. Move the "
        "shared code into omicsclaw/engine/ or use a lazy import "
        "inside a function body if the cycle truly cannot be broken.\n  "
        + "\n  ".join(f"{p}:{ln}" for p, ln in sorted(top_level))
    )


def test_lazy_reverse_imports_match_grandfathered_set() -> None:
    """Function-body ``import bot.x`` is allowed *only* at the sites
    listed in ``GRANDFATHERED_LAZY_IMPORTS``. New lazy imports must be
    declared explicitly; entries in the allowlist that no longer match
    real code must be removed (the set ratchets monotonically as the
    bot-side helpers move into omicsclaw/)."""
    found = _scan(lazy=True)

    new_violations = sorted(found - GRANDFATHERED_LAZY_IMPORTS)
    assert not new_violations, (
        "New lazy reverse imports introduced (omicsclaw/ → bot/). "
        "Either move the helper into omicsclaw/ or, if you must keep "
        "the lazy import temporarily, add the (path, lineno) tuple to "
        "GRANDFATHERED_LAZY_IMPORTS in this file.\n  "
        + "\n  ".join(f"{p}:{ln}" for p, ln in new_violations)
    )

    stale = sorted(GRANDFATHERED_LAZY_IMPORTS - found)
    assert not stale, (
        "Allowlist contains entries that no longer match real code. "
        "Either the line moved or the violation was fixed — update "
        "GRANDFATHERED_LAZY_IMPORTS in this file.\n  "
        + "\n  ".join(f"{p}:{ln}" for p, ln in stale)
    )


def test_grandfathered_set_documents_phase_2_target() -> None:
    """The lazy allowlist must shrink monotonically toward 0. When it
    reaches 0, delete this test and ``GRANDFATHERED_LAZY_IMPORTS``,
    leaving the strict checks (top-level + lazy = ∅) as the
    canonical guards."""
    assert (
        len(GRANDFATHERED_LAZY_IMPORTS) == 14
    ), "Allowlist size changed — update the count or remove this test once allowlist is empty."
