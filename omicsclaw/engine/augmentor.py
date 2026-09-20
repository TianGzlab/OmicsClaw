"""The seam through which a model call is given something extra to read."""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from omicsclaw.schema import Message, ToolDefinition

__all__ = ["TurnAugmentor"]


@runtime_checkable
class TurnAugmentor(Protocol):
    """Appends messages to what one model call is sent, and nothing else.

    Passed to :meth:`~omicsclaw.engine.loop.AgentEngine.run` or
    :meth:`~omicsclaw.engine.loop.AgentEngine.run_stream`, and consulted
    once per turn — **after**
    :class:`~omicsclaw.engine.compactor.HistoryCompactor` and immediately
    before the model is called. The order is the contract, not an
    implementation detail: an augmentor exists to put something where the
    model will certainly see it, and anything added before compaction is
    something compaction can take away again.

    **A second seam rather than a wider first one.** Rewriting the
    conversation and adding to it look similar enough to share an
    interface, and sharing one would be a mistake with a name:
    :func:`~omicsclaw.entry.turn._outcome` reads three concrete
    attributes off the compactor it passed in, so anything that wrapped
    or replaced a compactor would have to forward them, and forgetting
    would not fail — it would silently drop a run's compaction records.
    That is defect R3's shape (see
    :func:`~omicsclaw.entry.assembly.build_registry`), and two narrow
    seams cost less than one wide one that invites it back.

    What an implementation may assume, and what it may not:

    - What it returns is appended to the **sent copy only**. It never
      enters the run's history, never reaches
      :attr:`~omicsclaw.engine.types.RunResult.messages`, and never
      accumulates — every turn starts from the conversation again and
      asks afresh.
    - It is therefore the right place for state that is authoritative
      *outside* the conversation and must be restated inside it, and the
      wrong place for anything the run should remember having said.
    """

    async def augment(
        self,
        history: tuple[Message, ...],
        tools: tuple[ToolDefinition, ...],
    ) -> Sequence[Message]:
        """Extra messages for this call, or an empty sequence for none.

        :param history: What this call would otherwise be sent, already
            compacted.
        :param tools: The tool definitions this call will carry.
        :returns: Messages appended, in order, after *history*. Empty
            means send *history* unchanged.
        :raises Exception: Propagates out of the run. An augmentor that
            considers its own failure survivable must say so itself —
            the loop cannot tell a plan it could not read from a plan
            that says stop.
        """
        ...
