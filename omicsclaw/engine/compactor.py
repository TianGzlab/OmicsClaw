"""The seam through which a run's history is compacted between model calls."""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from omicsclaw.schema import Message, ToolDefinition

__all__ = ["HistoryCompactor"]


@runtime_checkable
class HistoryCompactor(Protocol):
    """Rewrites the conversation before each model call of one run.

    Passed to :meth:`~omicsclaw.engine.loop.AgentEngine.run` or
    :meth:`~omicsclaw.engine.loop.AgentEngine.run_stream`, and consulted
    once per turn, after the tool list is read and before the model is
    called.
    """

    async def compact(
        self,
        history: tuple[Message, ...],
        tools: tuple[ToolDefinition, ...],
    ) -> tuple[Sequence[Message], bool] | None:
        """Decide what this turn's model call is sent.

        :param history: The run's history so far, inputs included.
        :param tools: The tool definitions this call will carry.
        :returns: ``None`` to send *history* unchanged, or ``(messages,
            keep)``: *messages* is sent for this call, and when *keep* is
            true it also replaces the run's history, so later turns and
            the returned trajectory build on it. An empty *messages* is
            ignored.
        :raises Exception: Propagates out of the run.
        """
        ...
