"""The seam through which an exchange reads its history and hands it back.

Plan 0027 §12.4.2. The loop still owns no conversation: a
:class:`Conversation` is read at the start of an exchange and written at
the end of it, and between those two points the trajectory lives where it
always did, in the run itself.

**``commit`` replaces; it does not append.** The temptation is an
``extend`` that takes only what this exchange added, and it is wrong for
a reason that shows up nowhere until a conversation gets long enough to
compact. A compactor that keeps its rewrite replaces the *run's* history
(``loop.py:259-260``), so the messages it folded away no longer exist in
the trajectory — only the summary does. An append-only seam would write
the folded-away originals back into storage and leave the summary in the
:class:`~omicsclaw.engine.types.RunResult` alone, where the next exchange
never sees it: compaction would then work perfectly within one exchange
and not at all between two, which is the only place it was needed.
Replacement has no such failure mode, and it is what every implementation
of this idea in reach already does.

**The engine strips its own system message.** It put one there, so it
takes it back out rather than making every implementation remember to.

**Storage is not this seam's business.** ``commit`` is handed a
trajectory, not a transaction: an implementation that persists is free
to, and one that only holds the conversation in memory — leaving a
registry to decide when a session reaches a disk — is the arrangement
this was written for. Nothing about compaction *state* crosses here
either; that belongs to whoever configured the compactor.

This module imports :mod:`typing` and :mod:`omicsclaw.schema`, and
nothing else.
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from omicsclaw.schema import Message

__all__ = ["Conversation"]


@runtime_checkable
class Conversation(Protocol):
    """The history one exchange starts from, and where it is left.

    Passed to :meth:`~omicsclaw.engine.loop.AgentEngine.exchange` or
    :meth:`~omicsclaw.engine.loop.AgentEngine.exchange_stream`, or given
    to the engine as a default at construction. Read once, written once,
    never touched during a turn.
    """

    def messages(self) -> Sequence[Message]:
        """The conversation so far, oldest first, **without a system
        message**.

        The engine prepends its own when it has a
        :class:`~omicsclaw.engine.prompt.PromptSource`, and two system
        messages are not a longer prompt — they are a stale persona
        standing beside the current one.

        Synchronous: an exchange is about to be composed out of this, and
        a history that has to be fetched should be fetched before the
        exchange rather than inside the composition of its first call.
        """
        ...

    async def commit(self, messages: Sequence[Message]) -> None:
        """Take this exchange's whole trajectory, replacing what was there.

        :param messages: Everything the run ended with — the history it
            was given, as compaction may have rewritten it, plus what
            this exchange produced — with the engine's system message
            already removed, so it can be handed straight back from
            :meth:`messages` next time.
        :raises Exception: Propagates out of the exchange, which is the
            honest outcome: a conversation that could not be recorded is
            one the next exchange would silently continue without.

        Called **once**, after the run has finished. An exchange that
        raised, or a stream the caller walked away from, commits nothing:
        a trajectory nobody completed is not a conversation to carry
        forward.
        """
        ...
