"""The compactor one exchange runs with, and where its files go.

:func:`build_compactor` joins the context layer's
:class:`~omicsclaw.context.ProgressiveCompactor` to this deployment: the
budget and summarizer of the app, a file store for offloaded tool results
inside the workspace (so ``read_file`` can read them back), and a JSONL
log of every compaction. Both live under ``<workspace>/.omicsclaw/``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from omicsclaw.context import (
    BudgetReport,
    CompactionRecord,
    CompactionState,
    Offloader,
    ProgressiveCompactor,
)
from omicsclaw.memory import FileOffloadStore, JsonlCompactionLog

from .config import STATE_DIRNAME, AppConfig
from .memory import build_memory_extractor

if TYPE_CHECKING:  # pragma: no cover - a type-only import
    from .assembly import AgentApp

__all__ = [
    "PINNED_SYSTEM_MESSAGES",
    "RECORDS_DIRNAME",
    "STATE_DIRNAME",
    "TOOL_RESULTS_DIRNAME",
    "build_compactor",
    "compaction_log",
    "offload_store",
]

_log = logging.getLogger(__name__)

PINNED_SYSTEM_MESSAGES = 1
"""Messages at the head of a composed conversation that compaction keeps:
the one system message :func:`~omicsclaw.context.assemble` puts at index 0.
The history carried between exchanges drops the same number."""

TOOL_RESULTS_DIRNAME = "tool_results"
"""Offloaded tool results, one subdirectory per session."""

RECORDS_DIRNAME = "compaction_records"
"""Compaction logs, one ``<session>.jsonl`` per session."""


def _state_dir(config: AppConfig) -> Path:
    return config.state_dir()


def offload_store(config: AppConfig, session_id: str = "") -> FileOffloadStore:
    """Where *session_id*'s offloaded tool results are kept.

    References are workspace-relative, which is what ``read_file`` takes.
    """
    return FileOffloadStore(
        _state_dir(config) / TOOL_RESULTS_DIRNAME,
        session_id,
        reference_base=config.workspace,
    )


def compaction_log(config: AppConfig) -> JsonlCompactionLog:
    """The log every compaction in this deployment is appended to."""
    return JsonlCompactionLog(_state_dir(config) / RECORDS_DIRNAME)


def build_compactor(
    app: "AgentApp",
    *,
    session_id: str = "",
    state: CompactionState | None = None,
    on_measure: Callable[[BudgetReport], None] | None = None,
    on_compact: Callable[[CompactionRecord], None] | None = None,
) -> ProgressiveCompactor:
    """A compactor for one exchange of *session_id*.

    Compacts from :attr:`AppConfig.compact_at` upwards, keeps the system
    message, offloads into :func:`offload_store`, hands summarized-away
    messages to an extractor when there is one, and logs every compaction
    that changed the conversation or failed to :func:`compaction_log`. A
    listener that raises or a log that cannot be written costs a log
    line, never the exchange or the other.

    **The extractor is built here, from the app, on every call**, rather
    than held on the app. It needs a model and a store, and the model is
    :attr:`AgentApp.summarizer` — so building it once at assembly would
    freeze a summarizer the app can be given a different one of later,
    and extraction would quietly keep calling the old one. Reading both
    fields in the same breath is what keeps them the same decision.
    :attr:`AgentApp.memory_extractor` overrides this when it is set, for
    a deployment that wants extraction through something else.

    :param state: Summary and anchors from the session's earlier exchanges.
    :param on_measure: Called with every pre-call measurement.
    :param on_compact: Called with every compaction record, before it is
        logged.
    """
    config = app.config
    log = compaction_log(config)
    extractor = app.memory_extractor
    if extractor is None:
        extractor = build_memory_extractor(app.memory, app.summarizer)

    async def record(entry: CompactionRecord) -> None:
        if on_compact is not None:
            try:
                on_compact(entry)
            except Exception:
                _log.exception("a compaction listener failed")
        _log.info(
            "compacted at %s: %d→%d tokens, %d→%d messages, %d offloaded%s%s",
            entry.pressure,
            entry.tokens_before,
            entry.tokens_after,
            entry.msgs_before,
            entry.msgs_after,
            len(entry.offloaded),
            "" if entry.written_back else " (not kept)",
            f" (degraded: {entry.degraded})" if entry.degraded else "",
        )
        try:
            await log.append(session_id, entry)
        except OSError as error:
            _log.warning(
                "could not log a compaction of session %s: %s",
                session_id or "-",
                error,
            )

    return ProgressiveCompactor(
        app.budget,
        summarizer=app.summarizer,
        offloader=Offloader(offload_store(config, session_id)),
        extractor=extractor,
        state=state,
        pinned=PINNED_SYSTEM_MESSAGES,
        trigger=config.compact_at,
        on_measure=on_measure,
        on_compact=record,
    )
