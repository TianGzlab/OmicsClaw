"""Shared LLM client utilities for the autoagent subsystem.

Consolidates provider resolution, API calls, and JSON response parsing
that were previously duplicated in optimization_loop.py and harness_loop.py.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from omicsclaw.autoagent.constants import (
    LLM_CALL_TIMEOUT_SECONDS,
    LLM_MAX_RETRIES,
    LLM_RETRY_BASE_SECONDS,
)

logger = logging.getLogger(__name__)


def call_llm(
    directive: str,
    *,
    system_prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    llm_provider: str = "",
    llm_model: str = "",
    llm_provider_config: dict[str, Any] | None = None,
) -> str:
    """Call an LLM via the OpenAI-compatible API.

    Parameters
    ----------
    directive:
        The user-role message content (the directive / prompt).
    system_prompt:
        System-role instruction for the model.
    temperature:
        Sampling temperature.
    max_tokens:
        Maximum tokens in the response.
    llm_provider:
        Fallback provider name (used when not in *llm_provider_config*).
    llm_model:
        Fallback model name.
    llm_provider_config:
        Explicit provider configuration dict with keys ``provider``,
        ``base_url``, ``model``, ``api_key``.

    Returns
    -------
    str
        The raw text content of the LLM response.

    Raises
    ------
    RuntimeError
        If no usable model or API key can be resolved.
    """
    from omicsclaw.core.provider_runtime import (
        provider_requires_api_key,
        resolve_provider_runtime,
    )

    config = dict(llm_provider_config or {})
    config_provider = str(config.get("provider", "") or "")
    config_base_url = str(config.get("base_url", "") or "")
    config_model = str(config.get("model", "") or "")
    config_api_key = str(config.get("api_key", "") or "")

    runtime = resolve_provider_runtime(
        provider=config_provider or llm_provider,
        base_url=config_base_url,
        model=config_model or llm_model,
        api_key=config_api_key,
    )

    if not runtime.model:
        raise RuntimeError(
            "No usable LLM model resolved. "
            "Configure an OmicsClaw provider or choose a valid model first."
        )

    if provider_requires_api_key(runtime.provider) and not runtime.api_key:
        raise RuntimeError(
            "No usable LLM provider config resolved "
            f"(provider={runtime.provider or 'unknown'}, source={runtime.source}). "
            "Configure the provider in OmicsClaw-App settings or set the "
            "matching environment variable."
        )

    from openai import OpenAI

    client = OpenAI(
        api_key=runtime.api_key,
        base_url=runtime.base_url or None,
        timeout=LLM_CALL_TIMEOUT_SECONDS,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": directive},
    ]

    last_exc: Exception | None = None
    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=runtime.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            last_exc = exc
            if not _is_retryable(exc):
                raise
            if attempt < LLM_MAX_RETRIES:
                delay = LLM_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "LLM call attempt %d/%d failed (%s), retrying in %.1fs",
                    attempt, LLM_MAX_RETRIES, exc, delay,
                )
                time.sleep(delay)

    raise RuntimeError(
        f"LLM call failed after {LLM_MAX_RETRIES} retries: {last_exc}"
    ) from last_exc


def _is_retryable(exc: Exception) -> bool:
    """Return True if the exception is a transient error worth retrying."""
    # OpenAI SDK raises specific status-code exceptions
    exc_type_name = type(exc).__name__
    # Rate limit (429), server errors (5xx), timeouts, connection issues
    if exc_type_name in ("RateLimitError", "APITimeoutError", "APIConnectionError"):
        return True
    if exc_type_name == "APIStatusError":
        status = getattr(exc, "status_code", 0)
        return status >= 500
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    return False


def parse_json_from_llm(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from an LLM response.

    Handles common response formats:
    1. Plain JSON
    2. JSON wrapped in markdown code fences (``\\`\\`\\`json ... \\`\\`\\```)
    3. JSON preceded/followed by prose (balanced-brace extraction)

    Returns ``None`` if no valid JSON object can be extracted.
    """
    text = text.strip()

    # Strip markdown code fences
    fence_match = re.search(
        r"```(?:json|JSON)?\s*\n(.*?)```", text, re.DOTALL
    )
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract the outermost balanced JSON object.
    start = text.find("{")
    if start != -1:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    logger.warning("Failed to parse LLM response as JSON: %s", text[:200])
    return None
