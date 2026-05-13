from __future__ import annotations

import importlib
import sys

from omicsclaw.core.registry import OmicsRegistry


def _fresh_import_bot_core():
    for module_name in (
        "bot.core",
        "omicsclaw.runtime.context_assembler",
        "omicsclaw.runtime.context_layers",
    ):
        sys.modules.pop(module_name, None)
    return importlib.import_module("bot.core")


def test_importing_bot_core_does_not_force_registry_load(monkeypatch):
    calls: list[tuple[tuple, dict]] = []
    real_load_all = OmicsRegistry.load_all

    def spy(self, *args, **kwargs):
        calls.append((args, kwargs))
        return real_load_all(self, *args, **kwargs)

    monkeypatch.setattr(OmicsRegistry, "load_all", spy)

    _fresh_import_bot_core()

    assert calls == []


def test_bot_core_loads_registry_on_demand(monkeypatch):
    calls: list[tuple[tuple, dict]] = []
    real_load_all = OmicsRegistry.load_all

    def spy(self, *args, **kwargs):
        calls.append((args, kwargs))
        return real_load_all(self, *args, **kwargs)

    monkeypatch.setattr(OmicsRegistry, "load_all", spy)

    core = _fresh_import_bot_core()
    assert calls == []

    tool_registry = core.get_tool_registry()

    assert tool_registry is not None
    assert len(calls) >= 1


def test_bot_core_lazy_TOOLS_attribute_resolves_without_nameerror():
    """``bot.core.TOOLS`` is a legacy lazy re-export of the tools-list
    produced by ``bot.agent_loop.get_tools()``. The ``__getattr__`` branch
    at bot/core.py:572-573 calls ``get_tools()`` directly, but ``get_tools``
    is only available through the ``_AGENT_LOOP_REEXPORTS`` lazy-import
    path further down — it is *not* in module scope at line 573. Result:
    every access to ``bot.core.TOOLS`` raises NameError.

    Sibling lazy attributes ``TOOL_RUNTIME`` and ``TOOL_EXECUTORS`` work
    because their backing functions are imported eagerly from
    ``bot.tool_executors`` at the top of the file.

    Caught by pyflakes audit on 2026-05-13."""
    core = _fresh_import_bot_core()

    tools = core.TOOLS  # must not raise
    assert isinstance(tools, list), (
        f"bot.core.TOOLS should be a list of tool definitions; "
        f"got {type(tools).__name__}: {tools!r}"
    )
    # Sanity: at least the core omicsclaw tool should be registered.
    assert any(
        isinstance(t, dict)
        and t.get("function", {}).get("name") == "omicsclaw"
        for t in tools
    ), (
        f"bot.core.TOOLS missing the 'omicsclaw' tool — get_tools() likely "
        f"returned an unrelated value. Tools: {tools!r}"
    )
