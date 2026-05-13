"""Slash-command registry — replaces the ~250-line if-elif chain in
``bot/agent_loop.py:llm_tool_loop`` with a name → handler dispatch
table.

Phase 1 P0-E (Task #8). The previous chain had 14 ``elif cmd == ...``
branches inline; touching any of them required editing the same
function body, which made review noisy and adding a new command
("just one more elif") the path of least resistance.

The handlers live in ``bot/commands/builtins.py``. They register
themselves at import time via ``@register("/foo")``. The wirer in
``bot/agent_loop.py`` calls ``await dispatch(ctx)`` and treats
``None`` as "not a command — fall through to the LLM".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable


@dataclass(frozen=True)
class SlashCommandContext:
    """Per-request context passed to every slash-command handler.

    Frozen so handlers cannot accidentally mutate caller state. The
    handlers reach into ``bot.core`` / ``bot.agent_loop`` module
    globals (transcript_store, OUTPUT_DIR, ...) directly because
    they are themselves bot-side code; only request-scoped values
    flow through this dataclass.
    """

    chat_id: int | str
    user_id: str | None
    platform: str | None
    user_text: str
    """Raw user input, exactly as the channel received it. The
    dispatcher applies ``.strip().lower()`` for command lookup."""
    workspace: str
    pipeline_workspace: str


CommandHandler = Callable[[SlashCommandContext], Awaitable[str]]


_REGISTRY: dict[str, CommandHandler] = {}


def register(name: str) -> Callable[[CommandHandler], CommandHandler]:
    """Decorator: register *fn* as the handler for command *name*.

    Names must start with ``/`` and be unique. Re-registering the
    same name is treated as a programming error rather than a silent
    overwrite — multiple modules contributing to the same command
    is exactly the bug the registry is here to make obvious.
    """
    if not name.startswith("/"):
        raise ValueError(f"Slash command name must start with '/': {name!r}")
    if name != name.lower():
        raise ValueError(
            f"Slash command name must be lowercase: {name!r} "
            "(dispatch normalises user input to lower)"
        )

    def deco(fn: CommandHandler) -> CommandHandler:
        if name in _REGISTRY:
            raise ValueError(f"Slash command {name!r} already registered")
        _REGISTRY[name] = fn
        return fn

    return deco


async def dispatch(ctx: SlashCommandContext) -> str | None:
    """Try to dispatch ``ctx.user_text`` as a slash command.

    Returns the handler's reply text, or ``None`` if the input is
    not a slash command or no handler is registered for it. The
    caller (agent_loop wirer) returns the reply directly when not
    None and falls through to the LLM otherwise.
    """
    text = ctx.user_text.strip().lower()
    if not text.startswith("/"):
        return None
    handler = _REGISTRY.get(text)
    if handler is None:
        return None
    return await handler(ctx)


def registered_commands() -> tuple[str, ...]:
    """All registered command names, sorted. Useful for ``/help``
    discovery and contract tests."""
    return tuple(sorted(_REGISTRY))
