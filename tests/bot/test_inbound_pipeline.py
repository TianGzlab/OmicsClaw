"""Contract test exposing the dead MessageBus / middleware pipeline.

Findings (May 2026 audit, verified at HEAD = e59f89d):

* ``bot/channels/bus.py`` defines ``MessageBus.publish_inbound`` but **no
  production code calls it**. The only ``publish_outbound`` callers live
  inside ``ChannelManager._consumer_loop`` — a loop that itself only runs
  if some channel pushes to ``publish_inbound``, which never happens.
* ``bot/channels/middleware.py`` (``MiddlewarePipeline``,
  ``RateLimit/Audit/Dedup/AllowList/TextLimit`` middlewares) is wired by
  ``bot/run.py:_build_middleware`` and threaded into
  ``ChannelManager(middleware=…)``, but because the consumer loop never
  fires the middleware never executes either.
* The production flow is direct: ``Channel._handle_message`` →
  ``core.llm_tool_loop`` (see ``bot/channels/telegram.py:464``,
  ``bot/channels/feishu.py:760``). Bus + middleware are dead weight.

ADR-0003 (Phase 1 task #3) selects deletion as the resolution. After
Phase 1 P0-A (task #4) ships, the ``xfail`` markers below should be
removed; the assertions then act as the strict guard against
re-introducing the dead pipeline.
"""

from __future__ import annotations

import ast
from importlib.util import find_spec
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# --- Currently passing assertion (documents the state) -------------------


def test_no_production_publish_inbound_callers() -> None:
    """No file outside ``bus.py`` itself calls ``publish_inbound``.

    This is the proof that the entire ``MessageBus`` inbound side is
    unreachable from real channels — and the reason the middleware
    pipeline never executes.
    """
    callers: list[str] = []
    for area in ("bot", "omicsclaw"):
        for path in (REPO_ROOT / area).rglob("*.py"):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel == "bot/channels/bus.py":
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Attribute)
                    and node.attr == "publish_inbound"
                ):
                    callers.append(f"{rel}:{node.lineno}")
    assert callers == [], (
        "publish_inbound has callers — the dead-pipeline finding may be "
        "stale; reconsider ADR-0003. Hits:\n  " + "\n  ".join(callers)
    )


# --- Phase 1 P0-A target assertions (xfail until task #4 ships) ----------


def test_message_bus_module_deleted() -> None:
    """``bot/channels/bus.py`` was deleted in Phase 1 P0-A Slice C."""
    assert find_spec("bot.channels.bus") is None


def test_middleware_module_deleted() -> None:
    """``bot/channels/middleware.py`` was deleted in Phase 1 P0-A Slice C."""
    assert find_spec("bot.channels.middleware") is None


def test_run_py_does_not_build_middleware() -> None:
    """``bot/run.py`` and ``omicsclaw/app/server.py`` must not reference
    ``_build_middleware`` (deleted in Phase 1 P0-A Slice A)."""
    offenders: list[str] = []
    for rel in ("bot/run.py", "omicsclaw/app/server.py"):
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if "_build_middleware" in line:
                offenders.append(f"{rel}:{lineno}")
    assert offenders == [], "\n  ".join(offenders)
