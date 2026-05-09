"""Eval runtime config resolver.

Single source of truth for the eval suite's effective LLM endpoint, model,
and API key. Delegates to ``omicsclaw.core.provider_registry.resolve_provider``
so the same env semantics that drive ``bot/run.py`` also drive the eval
fixtures — when production runs DeepSeek v4-flash, eval measures DeepSeek
v4-flash, not a hard-coded foreign default.

The ``EVAL_MODEL`` env var is the eval-only override and trumps
``OMICSCLAW_MODEL`` / provider preset; it lets the nightly cron sweep
alternate models without touching the production-facing ``.env``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvalRuntimeConfig:
    """Resolved eval-runtime endpoint settings.

    ``api_key`` is ``None`` when the user has no provider credential set —
    the fixture should skip in that case.
    """

    api_key: str | None
    base_url: str | None
    model: str


def resolve_eval_config(
    env: Mapping[str, str] | None = None,
) -> EvalRuntimeConfig:
    """Resolve the effective eval runtime configuration from env.

    Not yet implemented — RED phase placeholder for TDD.
    """
    raise NotImplementedError("resolve_eval_config is not implemented (RED)")
