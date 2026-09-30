"""What a sub-agent is, and which tools one is allowed to reach."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

__all__ = ["TASK_TOOL_NAME", "InvalidDefinition", "SubAgentDefinition"]

TASK_TOOL_NAME = "task"
"""Name of the delegation tool, and the one name a sub-agent never gets.

Spelled here rather than in :mod:`omicsclaw.subagent.task_tool` because
:meth:`SubAgentDefinition.resolve_tools` has to remove it and that module
imports this one.
"""

_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class InvalidDefinition(ValueError):
    """A definition is missing a required field or spells its name illegally.

    Raised by :meth:`SubAgentDefinition.validate` and by
    :func:`~omicsclaw.subagent.frontmatter.parse_agent_file`.
    """


@dataclass(frozen=True, slots=True)
class SubAgentDefinition:
    """One sub-agent: who it is, what it may use, and how it is told so."""

    name: str
    """Identifier the model passes as ``subagent_type``. Lowercase
    alphanumerics and hyphens, starting with a letter or digit."""

    description: str
    """When to delegate to this sub-agent, written for the model. It is
    the only thing the model reads when choosing between sub-agents."""

    system_prompt: str
    """The sub-agent's own instructions. Becomes message zero of its run."""

    tools: tuple[str, ...] = ()
    """Allow-list of parent tool names. Empty inherits every parent tool."""

    disallowed_tools: tuple[str, ...] = ()
    """Names removed after the allow-list is applied."""

    model: str = ""
    """Model override. Empty keeps the parent's model."""

    max_turns: int = 0
    """Turn ceiling for the delegated run. ``0`` keeps the engine default."""

    skills: tuple[str, ...] = ()
    """Skill names whose bodies are preloaded into the sub-agent's prompt."""

    source: str = ""
    """Where the definition came from — ``"builtin"`` or a file path. For
    diagnostics only; nothing dispatches on it."""

    def validate(self) -> None:
        """Check the three required fields.

        :raises InvalidDefinition: the name is empty or malformed, or the
            description or system prompt is blank.
        """
        if not self.name:
            raise InvalidDefinition("a sub-agent needs a name")
        if not _NAME.match(self.name):
            raise InvalidDefinition(
                f"{self.name!r} is not a usable sub-agent name; use lowercase "
                "letters, digits and hyphens, starting with a letter or digit"
            )
        if not self.description.strip():
            raise InvalidDefinition(
                f"sub-agent {self.name!r} has no description, so the model has "
                "nothing to choose it by"
            )
        if not self.system_prompt.strip():
            raise InvalidDefinition(
                f"sub-agent {self.name!r} has no system prompt, so it would run "
                "with no instructions at all"
            )

    def resolve_tools(self, all_names: Iterable[str]) -> tuple[str, ...]:
        """The parent tool names this sub-agent may use, in *all_names* order.

        :param all_names: every tool name the parent has mounted, in the
            order it mounted them.
        :returns: *all_names* filtered by :attr:`tools`, minus
            :attr:`disallowed_tools`, minus :data:`TASK_TOOL_NAME`.

        The order of *all_names* is preserved rather than the allow-list's,
        because a tool table reordered per sub-agent invalidates a prompt
        prefix cache that would otherwise be shared.

        :data:`TASK_TOOL_NAME` is removed whether or not it was asked for:
        a sub-agent that can delegate can delegate to itself.
        """
        allowed = frozenset(self.tools) if self.tools else None
        denied = frozenset(self.disallowed_tools)
        return tuple(
            name
            for name in all_names
            if name != TASK_TOOL_NAME
            and name not in denied
            and (allowed is None or name in allowed)
        )
