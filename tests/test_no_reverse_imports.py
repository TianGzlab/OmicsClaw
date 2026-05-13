"""Architectural guardrail: ``omicsclaw/`` must not import from ``bot/``.

The dependency direction is one-way: user-facing entries (``bot/``,
``omicsclaw/app/``, ``omicsclaw/interactive/``) consume the engine living
in ``omicsclaw/``. The reverse — engine code reaching back into ``bot/`` —
creates cycles, blocks the boundary refactor planned in
``docs/adr/0001-bot-core-decomposition.md``, and was the root cause of
multiple un-shippable migrations called out in the May 2026 audit.

This test scans every ``.py`` file under ``omicsclaw/`` and refuses any
``from bot…`` / ``import bot…`` (top-level **or** function-body lazy
import — both count). Known pre-existing violations are grandfathered in
``GRANDFATHERED_VIOLATIONS`` so this test stays green today; the set must
shrink monotonically as Phase 1 boundary work lands. Adding a new site
or leaving a stale entry in the allowlist both fail the test.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOT = REPO_ROOT / "omicsclaw"

# Pre-existing reverse-import sites at HEAD = e59f89d (16 total).
# Phase 1 P0-A → P0-D will drive this set to empty. When that happens,
# delete the allowlist and let the strict check (set must equal {}) stand.
GRANDFATHERED_VIOLATIONS: frozenset[tuple[str, int]] = frozenset(
    {
        # omicsclaw/app/server.py — 4753-4814 removed by Phase 1 P0-A
        # (delete /bridge/start middleware wiring); 351 / 4602 redirected
        # to omicsclaw.engine by Phase 1 P0-D.
        ("omicsclaw/app/server.py", 351),
        ("omicsclaw/app/server.py", 4602),
        ("omicsclaw/app/server.py", 4753),
        ("omicsclaw/app/server.py", 4800),
        ("omicsclaw/app/server.py", 4813),
        ("omicsclaw/app/server.py", 4814),
        # omicsclaw/interactive/ — to be redirected at Phase 1 P0-D.
        ("omicsclaw/interactive/interactive.py", 1379),
        ("omicsclaw/interactive/interactive.py", 1422),
        ("omicsclaw/interactive/tui.py", 580),
        ("omicsclaw/interactive/tui.py", 856),
        ("omicsclaw/interactive/tui.py", 872),
        ("omicsclaw/interactive/tui.py", 1016),
        # omicsclaw/runtime/preflight/sc_batch.py — to be redirected at P0-D.
        ("omicsclaw/runtime/preflight/sc_batch.py", 271),
        ("omicsclaw/runtime/preflight/sc_batch.py", 378),
        ("omicsclaw/runtime/preflight/sc_batch.py", 477),
        ("omicsclaw/runtime/preflight/sc_batch.py", 478),
    }
)


def _is_bot_module(name: str) -> bool:
    return name == "bot" or name.startswith("bot.")


def _scan_reverse_imports() -> set[tuple[str, int]]:
    found: set[tuple[str, int]] = set()
    for path in SCAN_ROOT.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and _is_bot_module(node.module):
                    found.add((rel, node.lineno))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_bot_module(alias.name):
                        found.add((rel, node.lineno))
    return found


def test_no_new_reverse_imports() -> None:
    """omicsclaw/ may not import bot/ except at grandfathered sites."""
    found = _scan_reverse_imports()

    new_violations = sorted(found - GRANDFATHERED_VIOLATIONS)
    assert not new_violations, (
        "New reverse imports introduced (omicsclaw/ → bot/). "
        "The dependency direction is one-way; move the shared code into "
        "omicsclaw/engine/ instead.\n  "
        + "\n  ".join(f"{p}:{ln}" for p, ln in new_violations)
    )

    stale_allowlist = sorted(GRANDFATHERED_VIOLATIONS - found)
    assert not stale_allowlist, (
        "Allowlist contains entries that no longer match real code. "
        "Either the line moved or the violation was fixed — update "
        "GRANDFATHERED_VIOLATIONS in this file.\n  "
        + "\n  ".join(f"{p}:{ln}" for p, ln in stale_allowlist)
    )


def test_grandfathered_set_documents_phase_1_target() -> None:
    """The allowlist must be non-empty until Phase 1 P0-D ships;
    once empty, this test (and the allowlist) should be deleted, leaving
    test_no_new_reverse_imports as the strict guard."""
    assert (
        len(GRANDFATHERED_VIOLATIONS) == 16
    ), "Allowlist size changed — update the count or remove this test once allowlist is empty."
