"""The seam through which a delegation is actually run."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .definition import SubAgentDefinition

__all__ = ["SUBAGENT_VALUE_KEY", "Delegate"]

SUBAGENT_VALUE_KEY = "subagent"
"""The :class:`~omicsclaw.tools.ToolContext` value naming the sub-agent
whose run a tool call belongs to.

Bound by :class:`~omicsclaw.subagent.task_tool.TaskTool` around the
delegation and read by whatever renders an approval prompt, so a card can
say which agent is asking. Absent means the parent agent is asking.
"""


@runtime_checkable
class Delegate(Protocol):
    """Runs one sub-agent and hands back what it concluded."""

    async def delegate(self, definition: SubAgentDefinition, prompt: str) -> str:
        """Run *definition* once over *prompt* and return its final text.

        :param definition: the sub-agent to run.
        :param prompt: the whole task. The sub-agent sees no other
            history, so anything it needs has to be in here.
        :returns: the sub-agent's closing message, which is the only
            thing the caller gets back.
        :raises Exception: an implementation may fail; the caller turns
            that into an error observation for the model.
        """
        ...
