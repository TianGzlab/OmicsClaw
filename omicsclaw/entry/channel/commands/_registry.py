"""Slash-command registry: a name to handler dispatch table.

Ported verbatim from ``omicsclaw/surfaces/channels/commands/_registry.py``
for plan 0031 task D1, apart from :class:`SlashCommandContext`'s two new
fields and this docstring. It replaced a 14-branch ``elif cmd == ...`` chain,
where touching any one command meant editing the same function body and
adding one more was the path of least resistance.

The handlers live in :mod:`~omicsclaw.entry.channel.commands.builtins` and
register themselves at import time via ``@register("/foo")``. A channel calls
``await dispatch(ctx)`` and treats ``None`` as "not a command — hand it to the
agent instead".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:  # pragma: no cover - a type-only import
    from omicsclaw.entry.assembly import AgentApp


@dataclass(frozen=True)
class SlashCommandContext:
    """Per-request context passed to every slash-command handler.

    Frozen so handlers cannot accidentally mutate caller state.

    **Two fields are new and one is gone**, which is the whole of this
    file's port. The handlers used to read the deleted
    ``omicsclaw.runtime.agent.state`` module's globals — a transcript store, a
    data directory, a skills table — so only request-scoped values needed to
    travel here. There are no such globals now: the deployment is an
    assembled :class:`~omicsclaw.entry.assembly.AgentApp`, and a handler that
    cannot see it can answer nothing. ``pipeline_workspace`` left with the
    two commands that read it (see
    :mod:`~omicsclaw.entry.channel.commands.builtins`).
    """

    chat_id: int | str
    user_id: str | None
    platform: str | None
    user_text: str
    """Raw user input, exactly as the channel received it. The
    dispatcher applies ``.strip().lower()`` for command lookup."""
    workspace: str
    app: "AgentApp | None" = None
    """The assembled deployment, or ``None`` for a caller that has none.

    Optional so a channel can dispatch the static commands — ``/help``,
    ``/examples`` — before it is bound. A handler that needs the app says so
    by answering that it is not available rather than raising into a callback.
    """

    session_id: str = ""
    """Which conversation this command acts on, for the two that act on one.
    Empty means "no conversation", which those two report."""


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

    Returns the handler's reply text, or ``None`` if the input is not a slash
    command or no handler is registered for it. A channel sends the reply
    directly when it is not ``None`` and submits the message as an exchange
    otherwise.
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
