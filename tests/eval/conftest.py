"""Pytest fixtures for the real-LLM behavioral-parity eval suite.

Exposes ``real_llm_runner``: an async callable that takes a user query
plus optional context (skill / domain / workspace), assembles the
production system prompt + tool list (same path bot/core.py uses), and
hits the configured LLM for a *single* round (no tool execution).
Returns a structured ``LLMRoundResult`` so invariant assertions can
inspect tool_calls / response_text without re-implementing the LLM
plumbing.

When ``LLM_API_KEY`` is unset the fixture skips gracefully — eval
tests collected but not executed, exit code 0. This lets contributors
run the default ``pytest`` (eval markers excluded) without ever
needing API credentials, and lets the nightly workflow detect missing
secrets without alarm.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from tests.eval.runtime_config import EvalRuntimeConfig, resolve_eval_config


# --- Result shape -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolCallObservation:
    """A single tool call the model emitted during the captured round."""

    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LLMRoundResult:
    """One round of LLM output captured for invariant evaluation.

    The runner does NOT execute the captured tool calls — eval is about
    "what does the model decide to do given this prompt", not the
    full agent loop. ``raw`` keeps the provider-side response object so
    advanced assertions can poke at usage / finish_reason / etc.
    """

    query: str
    response_text: str
    tool_calls: tuple[ToolCallObservation, ...] = ()
    raw: dict[str, Any] | None = None
    model: str = ""

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(tc.name for tc in self.tool_calls)


# --- Skip-without-credentials helper ----------------------------------------


@pytest.fixture
def eval_runtime_config() -> EvalRuntimeConfig:
    """Effective eval runtime config (model + base_url + key) for this run.

    Delegates to ``resolve_eval_config`` so eval and production both
    consume ``omicsclaw.core.provider_registry.resolve_provider``.

    Function-scoped so ``monkeypatch.setenv`` in any future test sees a
    freshly-resolved config — caching is cheap (dict lookups), so there
    is no perf reason to widen the scope.
    """
    return resolve_eval_config()


@pytest.fixture
def eval_model_name(eval_runtime_config: EvalRuntimeConfig) -> str:
    """Effective eval model name. Override via ``EVAL_MODEL`` env var."""
    return eval_runtime_config.model


@pytest.fixture
def real_llm_runner(
    eval_model_name: str,
    eval_runtime_config: EvalRuntimeConfig,
):
    """Async runner: ``await runner(query, **context) -> LLMRoundResult``.

    Skips the test gracefully when no API key is configured. The runner
    re-uses ``omicsclaw.runtime`` builders so the captured behaviour
    matches what the production bot path produces — no mock, no
    alternate prompt, no alternate tool list.
    """
    api_key = eval_runtime_config.api_key
    if not api_key:
        pytest.skip(
            "No provider API key configured (checked LLM_API_KEY / "
            "ANTHROPIC_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY / "
            "etc.); behavioral-parity eval requires LLM access. Set "
            "the env var and rerun with ``pytest -m eval``."
        )

    base_url = eval_runtime_config.base_url

    async def _run(
        query: str,
        *,
        skill: str = "",
        domain: str = "",
        workspace: str = "",
        capability_context: str = "",
    ) -> LLMRoundResult:
        from openai import AsyncOpenAI

        from omicsclaw.runtime.bot_tools import (
            build_bot_tool_specs,
            build_default_bot_tool_context,
        )
        from omicsclaw.runtime.context_layers import ContextAssemblyRequest
        from omicsclaw.runtime.system_prompt import build_system_prompt
        from omicsclaw.runtime.tool_registry import select_tool_specs

        # Build the production-shape system prompt.
        system_prompt = build_system_prompt(
            surface="bot",
            skill=skill,
            query=query,
            domain=domain,
            capability_context=capability_context,
            workspace=workspace,
        )

        # Build the production-shape tool list. Reuses the same
        # ``BotToolContext`` builder ``bot/core.py`` uses, so the
        # ``omicsclaw`` tool's ``skill`` enum exposes the full skill
        # registry + ``"auto"`` and the model sees the real domain
        # briefing — not a 2-skill stub. Without this the eval would
        # measure a fictional surface that can't route to skills like
        # ``bulkrna-de`` / ``genomics-variant-calling`` even when the
        # production prompt would.
        ctx = build_default_bot_tool_context()
        all_specs = build_bot_tool_specs(ctx)
        request = ContextAssemblyRequest(
            surface="bot",
            skill=skill,
            query=query,
            domain=domain,
            capability_context=capability_context,
            workspace=workspace,
        )
        selected_specs = select_tool_specs(all_specs, request=request)
        tools = [spec.to_openai_tool() for spec in selected_specs]

        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        async with AsyncOpenAI(**client_kwargs) as client:
            response = await client.chat.completions.create(
                model=eval_model_name,
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ],
                tools=tools or None,
                max_tokens=2048,
            )

        message = response.choices[0].message
        tool_calls: list[ToolCallObservation] = []
        for tc in message.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments)
            except (TypeError, ValueError, AttributeError):
                args = {}
            tool_calls.append(
                ToolCallObservation(name=tc.function.name, arguments=args)
            )

        return LLMRoundResult(
            query=query,
            response_text=message.content or "",
            tool_calls=tuple(tool_calls),
            raw=response.model_dump() if hasattr(response, "model_dump") else None,
            model=eval_model_name,
        )

    return _run
