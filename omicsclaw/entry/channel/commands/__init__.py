"""Slash commands a channel answers without asking the model.

See :mod:`._registry` for the dispatch primitives and :mod:`.builtins` for
the commands themselves.

The registry lives inside the channel surface rather than in a shared layer
because a slash command is a surface's own affordance: the CLI has its own,
spelled differently, and the desktop client has a menu. What the handlers
share with the rest of the process is the assembled
:class:`~omicsclaw.entry.assembly.AgentApp` they are handed, not a module of
globals they reach into — which is what the ported version did, and what made
it unmovable.
"""

from __future__ import annotations

from ._registry import (
    CommandHandler,
    SlashCommandContext,
    dispatch,
    register,
    registered_commands,
)

# Importing builtins triggers the @register decorators that populate
# the dispatch table. Keep this last so the public registry symbols
# are bound before handler modules import them.
from . import builtins  # noqa: F401, E402

__all__ = [
    "CommandHandler",
    "SlashCommandContext",
    "dispatch",
    "register",
    "registered_commands",
]
