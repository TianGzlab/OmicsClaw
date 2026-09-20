"""Progressive compaction across the model calls of one run.

:class:`ProgressiveCompactor` is consulted before every model call. It
measures the conversation against the budget, and from the configured
tier upwards compacts it with :func:`~omicsclaw.context.compaction.
compact` — offloading, then summarizing half or all of the head, then
emergency truncation — and decides whether the result replaces the
run's history (:func:`should_write_back`).

It keeps the incremental summary state between calls, so one instance
belongs to one run of one conversation. Its :meth:`~ProgressiveCompactor.
compact` method satisfies the engine's ``HistoryCompactor`` protocol
structurally.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Awaitable, Callable, Sequence

from omicsclaw.schema import Message, ToolDefinition

from .budget import BudgetReport, ContextBudget, Pressure, at_least, measure
from .compaction import (
    DEFAULT_MIN_TAIL,
    CompactionRecord,
    CompactionState,
    MemoryExtractor,
    compact,
)
from .offload import Offloader
from .summary import Summarizer
from .tokens import TokenCounter

__all__ = ["ProgressiveCompactor", "should_write_back"]

MeasureListener = Callable[[BudgetReport], None]
CompactionListener = Callable[[CompactionRecord], Awaitable[None]]


def should_write_back(record: CompactionRecord) -> bool:
    """Whether a compaction's result should replace the history it came from.

    Not when it degraded below the emergency tier: that is a failed
    summary whose truncated fallback should serve one call while the next
    call retries. Always after an emergency truncation, since the full
    history no longer fits at all. Otherwise only when something was
    actually removed or offloaded.
    """
    if record.degraded and record.pressure is not Pressure.EMERGENCY:
        return False
    return (
        record.msgs_after < record.msgs_before
        or record.tokens_after < record.tokens_before
        or bool(record.offloaded)
    )


def _did_something(record: CompactionRecord) -> bool:
    return bool(
        record.degraded
        or record.offloaded
        or record.msgs_after != record.msgs_before
        or record.tokens_after != record.tokens_before
    )


class ProgressiveCompactor:
    """Tiered compaction of one conversation, applied before each model call.

    :param budget: What the conversation must fit in. Each call measures
        against it together with the tool definitions of that call.
    :param summarizer: Writes SOFT and FULL summaries. ``None`` makes those
        tiers fall back to truncation.
    :param offloader: Moves oversized tool results out of the head.
        ``None`` disables offloading.
    :param extractor: Reads messages before a summary replaces them.
    :param state: Summary and anchors carried over from earlier runs.
    :param pinned: Leading messages never compacted — ``1`` for a system
        prompt at index 0.
    :param min_tail: Recent messages never compacted.
    :param trigger: Least severe measured tier that starts a compaction.
    :param counter: Exact tokenizer; the built-in estimate when ``None``.
    :param on_measure: Called with every measurement, compaction or not.
    :param on_compact: Awaited with the record of every compaction that
        changed the conversation or failed. A pass that found nothing to do
        is kept in :attr:`records` but not announced.

    Exceptions raised by either listener are ignored.
    """

    def __init__(
        self,
        budget: ContextBudget,
        *,
        summarizer: Summarizer | None = None,
        offloader: Offloader | None = None,
        extractor: MemoryExtractor | None = None,
        state: CompactionState | None = None,
        pinned: int = 0,
        min_tail: int = DEFAULT_MIN_TAIL,
        trigger: Pressure = Pressure.WARN,
        counter: TokenCounter | None = None,
        on_measure: MeasureListener | None = None,
        on_compact: CompactionListener | None = None,
    ) -> None:
        self._budget = budget
        self._summarizer = summarizer
        self._offloader = offloader
        self._extractor = extractor
        self._state = state if state is not None else CompactionState()
        self._pinned = pinned
        self._min_tail = min_tail
        self._trigger = trigger
        self._counter = counter
        self._on_measure = on_measure
        self._on_compact = on_compact
        self._records: list[CompactionRecord] = []

    @property
    def state(self) -> CompactionState:
        """Summary and anchors to carry into the next run."""
        return self._state

    @property
    def records(self) -> tuple[CompactionRecord, ...]:
        """Every compaction this instance ran, oldest first."""
        return tuple(self._records)

    @property
    def last_record(self) -> CompactionRecord | None:
        """The most recent compaction, or ``None`` if none ran."""
        return self._records[-1] if self._records else None

    async def compact(
        self,
        history: tuple[Message, ...],
        tools: tuple[ToolDefinition, ...],
    ) -> tuple[tuple[Message, ...], bool] | None:
        """Compact *history* if its pressure has reached the trigger tier.

        :returns: ``None`` below the trigger; otherwise the conversation to
            send and whether it should replace *history*.
        """
        report = measure(history, tools, self._budget, counter=self._counter)
        self._notify_measure(report)
        if not at_least(report.pressure, self._trigger):
            return None
        result, record = await self._run(history, report.budget, Pressure.NONE)
        return result, record.written_back

    async def force(
        self,
        history: Sequence[Message],
        tools: Sequence[ToolDefinition] = (),
    ) -> tuple[tuple[Message, ...], CompactionRecord]:
        """Summarize the whole head now, whatever the pressure.

        Offloads and summarizes as the FULL tier does; an emergency-level
        conversation is still truncated. Check
        :attr:`CompactionRecord.written_back` before keeping the result: a
        failed summary is not written back.
        """
        report = measure(history, tools, self._budget, counter=self._counter)
        self._notify_measure(report)
        return await self._run(tuple(history), report.budget, Pressure.FULL)

    async def _run(
        self,
        history: tuple[Message, ...],
        budget: ContextBudget,
        floor: Pressure,
    ) -> tuple[tuple[Message, ...], CompactionRecord]:
        result, record, state = await compact(
            history,
            budget,
            summarizer=self._summarizer,
            state=self._state,
            pinned=self._pinned,
            min_tail=self._min_tail,
            counter=self._counter,
            offloader=self._offloader,
            extractor=self._extractor,
            floor=floor,
        )
        kept = should_write_back(record)
        record = replace(record, written_back=kept)
        if kept:
            self._state = state
        self._records.append(record)
        if _did_something(record):
            await self._notify_compact(record)
        return result, record

    def _notify_measure(self, report: BudgetReport) -> None:
        if self._on_measure is None:
            return
        try:
            self._on_measure(report)
        except Exception:
            pass

    async def _notify_compact(self, record: CompactionRecord) -> None:
        if self._on_compact is None:
            return
        try:
            await self._on_compact(record)
        except Exception:
            pass
