"""Where a deployment's plans are kept, and who gets one per exchange.

:func:`build_plan_book` joins :mod:`omicsclaw.planning` to this
deployment: one book for the process, archiving under
:meth:`~omicsclaw.entry.config.AppConfig.plans_root`, with storage
failures reported here — the planning layer may not log, and a plan
directory that cannot be written is exactly the kind of fact that
otherwise shows up as "the agent keeps forgetting its plan".

:func:`build_injector` is the per-exchange half, and the shape is
deliberately the one :func:`~omicsclaw.entry.compaction.build_compactor`
already has: a function of ``(app, session_id)`` called at the start of
an exchange, returning something the engine consults before every model
call of it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from omicsclaw.planning import (
    FilePlanArchive,
    PlanArchiveError,
    PlanBook,
    PlanInjector,
)

from .config import AppConfig

if TYPE_CHECKING:  # pragma: no cover - a type-only import
    from .assembly import AgentApp

__all__ = ["build_injector", "build_plan_book"]

_log = logging.getLogger(__name__)


def build_plan_book(config: AppConfig) -> PlanBook | None:
    """The book every session's plan is drawn from, or ``None``.

    ``None`` when :attr:`~omicsclaw.entry.config.AppConfig.planning` is
    off, and that ``None`` is the single fact the rest of the wiring
    branches on — ``plan_write`` is not mounted, the prompt has no
    planning section, and no block is injected. One switch, three
    effects, no way to get half of it.

    **Nothing is created on disk here.** The archive makes its directory
    on the first save, so a deployment whose agent never writes a plan
    leaves no trace of the feature being on.
    """
    if not config.planning:
        return None
    return PlanBook(
        FilePlanArchive(config.plans_root()),
        on_archive_error=_report,
    )


def build_injector(app: "AgentApp", *, session_id: str = "") -> PlanInjector | None:
    """The augmentor for one exchange of *session_id*, or ``None``.

    Asking the book for the session's store is also what **restores** it:
    a plan written before a restart is read back here, before the first
    model call of the exchange can be composed. That is the counterpart
    to the write-through in
    :meth:`~omicsclaw.planning.PlanBook.for_session` — together they are
    the reference harness's restore-at-start plus checkpoint-on-write
    (``loop_phases.go:110`` and ``:310``), with the save moved to the
    moment the plan changes.

    ``None`` when the app has no book, which happens only when planning
    is off — :func:`~omicsclaw.entry.assembly.build_app` always sets one
    otherwise, including for an app given tools of its own.
    """
    if app.plans is None:
        return None
    return PlanInjector(
        app.plans.for_session(session_id),
        gate_turns=app.config.planning_gate_turns,
    )


def _report(session_id: str, error: PlanArchiveError) -> None:
    """Log a storage failure and let the exchange carry on.

    Fail-open, matching the reference harness (``loop_phases.go:302``)
    and for its reason: the plan is in memory and correct, so refusing
    the tool call — or the exchange — would turn a disk problem into a
    lost turn. What it costs is durability, which is why it is a warning
    rather than a debug line.

    The session id is logged; the plan's contents are not. Plan items
    name what is being analysed, and this module's whole package is
    under a rule that no tool argument and no tool output is ever logged.
    """
    _log.warning(
        "could not store the plan for session %s: %s", session_id or "-", error
    )
