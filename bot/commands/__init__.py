"""Slash-command registry for ``bot/agent_loop.py:llm_tool_loop``.

Replaces the ~250-line if-elif chain with a name → handler dispatch
table. See ``_registry.py`` for the registry primitives and
``builtins.py`` for the 14 built-in commands.

Phase 1 P0-E (Task #8). The registry stays in ``bot/`` (not
``omicsclaw/``) because every handler reads bot-side state
(transcript_store, DATA_DIR, format_skills_table, etc.) directly —
moving them to omicsclaw/ would require an even bigger DI surface
than EngineDependencies and risk a fresh wave of reverse imports.
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
