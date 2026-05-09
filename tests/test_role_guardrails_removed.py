"""Phase 3 (Task 3.1) RED tests pinning the deletion of the
``role_guardrails`` injector and its public surface.

Once Phase 3 lands, every external entry point that referenced
``role_guardrails`` must be gone — the SOUL.md single-source content
covers what used to live in this layer, and the surface-conditional
voice rules move to the ``surface_voice_rules`` layer.
"""

from __future__ import annotations

import pytest

from omicsclaw.runtime.context_layers import (
    DEFAULT_CONTEXT_LAYER_INJECTORS,
    ContextAssemblyRequest,
)


def test_role_guardrails_layer_not_in_default_injectors() -> None:
    names = [inj.name for inj in DEFAULT_CONTEXT_LAYER_INJECTORS]
    assert "role_guardrails" not in names, (
        f"role_guardrails injector still present in default list: {names}"
    )


def test_get_role_guardrails_no_longer_exported_from_runtime() -> None:
    """The function should be removed from the runtime ``__all__``."""
    from omicsclaw import runtime

    assert "get_role_guardrails" not in getattr(runtime, "__all__", []), (
        "get_role_guardrails still listed in omicsclaw.runtime.__all__"
    )


def test_get_role_guardrails_no_longer_exported_from_context_layers() -> None:
    from omicsclaw.runtime import context_layers

    assert "get_role_guardrails" not in getattr(context_layers, "__all__", [])


def test_context_assembly_request_drops_include_role_guardrails_field() -> None:
    """The boolean toggle was bound to a layer that no longer exists."""
    fields = ContextAssemblyRequest.__dataclass_fields__
    assert "include_role_guardrails" not in fields, (
        "include_role_guardrails still on ContextAssemblyRequest; "
        "drop it now that the layer is gone."
    )
    assert "role_guardrails_builder" not in fields


def test_build_system_prompt_does_not_accept_include_role_guardrails_kwarg() -> None:
    """The kwarg is removed from build_system_prompt."""
    import inspect

    from omicsclaw.runtime.system_prompt import build_system_prompt

    sig = inspect.signature(build_system_prompt)
    assert "include_role_guardrails" not in sig.parameters
