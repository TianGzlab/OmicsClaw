"""Runtime patches and discovery helpers for LLM provider quirks.

Two leaf utilities, both must be invoked explicitly — no module-import-time
side effects. Both never raise into callers; failure modes degrade to the
unpatched behavior or an empty result.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# DeepSeek reasoning_content multi-turn passback
# ---------------------------------------------------------------------------
#
# DeepSeek V3.x/V4 thinking-mode endpoints require every historical
# assistant message in the request payload to carry a ``reasoning_content``
# field. Without it, multi-turn requests fail with HTTP 400 "The
# reasoning_content in the thinking mode must be passed back".
#
# OmicsClaw's autoagent uses the raw OpenAI SDK and does not capture
# ``reasoning_content`` from past responses, so we inject an empty string
# fallback for any assistant message that lacks the field. Empirically
# tolerated by both thinking and non-thinking DeepSeek endpoints.
# ---------------------------------------------------------------------------


def apply_deepseek_reasoning_passback(
    messages: list[Any],
) -> list[Any]:
    """Return a new list with ``reasoning_content`` injected on assistant messages.

    Caller's dicts are not mutated — non-assistant messages and non-dict items
    pass through by reference.

    Args:
        messages: chat-completions style messages list.

    Returns:
        New list. Each assistant dict that lacks ``reasoning_content`` gets
        a copy with ``reasoning_content=""`` injected.
    """
    out: list[Any] = []
    for msg in messages:
        if not isinstance(msg, dict):
            out.append(msg)
            continue
        if msg.get("role") != "assistant":
            out.append(msg)
            continue
        if "reasoning_content" in msg:
            out.append(msg)
            continue
        copy = dict(msg)
        copy["reasoning_content"] = ""
        out.append(copy)
    return out


# ---------------------------------------------------------------------------
# Ollama installed-model discovery
# ---------------------------------------------------------------------------


def discover_ollama_models(base_url: str | None, *, timeout: float = 5.0) -> list[str]:
    """Probe ``GET {base_url}/api/tags`` for installed models.

    Returns the list of model names, or ``[]`` on any failure (no URL,
    connection error, non-200 status, malformed JSON).
    Never raises.
    """
    if not base_url or not isinstance(base_url, str):
        return []
    try:
        import httpx

        resp = httpx.get(
            f"{base_url.rstrip('/')}/api/tags", timeout=timeout
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []
    models = data.get("models", []) if isinstance(data, dict) else []
    return [
        m.get("name", "") for m in models
        if isinstance(m, dict) and m.get("name")
    ]


async def discover_ollama_models_async(
    base_url: str | None, *, timeout: float = 1.5
) -> list[str]:
    """Async variant of :func:`discover_ollama_models`."""
    if not base_url or not isinstance(base_url, str):
        return []
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/api/tags")
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []
    models = data.get("models", []) if isinstance(data, dict) else []
    return [
        m.get("name", "") for m in models
        if isinstance(m, dict) and m.get("name")
    ]


__all__ = [
    "apply_deepseek_reasoning_passback",
    "discover_ollama_models",
    "discover_ollama_models_async",
]
