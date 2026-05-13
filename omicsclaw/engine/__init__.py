"""Surface-agnostic LLM engine helpers.

This package exists so user-facing surfaces (``bot/``,
``omicsclaw/app/``, ``omicsclaw/interactive/``) can share the
``llm_tool_loop`` and its supporting helpers without any of them
having to reach back into ``bot/`` (which would create a cycle and
which the ``tests/test_no_reverse_imports.py`` guardrail forbids).

Phase 1 P0-B (this module) seeds the package with the pure helpers
extracted from ``bot/agent_loop.py`` — the model-identity anchor and
its companion resolver. Phase 1 P0-C will land the main loop here as
``omicsclaw/engine/loop.py``.
"""

from __future__ import annotations

from ._dependencies import EngineDependencies
from ._identity_anchor import (
    apply_model_identity_anchor,
    resolve_effective_model_provider,
)

__all__ = [
    "EngineDependencies",
    "apply_model_identity_anchor",
    "resolve_effective_model_provider",
]
