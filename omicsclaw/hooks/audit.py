"""A record per tool call: what ran, how it ended, and nothing else.

The one hook this package ships. The other three the reference harness
mounts already have homes in this tree — permission and the danger
patterns are :mod:`omicsclaw.permission`, oversized output is
:mod:`omicsclaw.context`'s ``Offloader``, plan persistence is
:mod:`omicsclaw.planning` — and re-implementing any of them here would
give a deployment two answers to the same question.

Observability is what was left. ``docs/plans/0031-entry-layer.md``
deferred it by name ("hooks：permission / danger / offload /
observability | 不做（Q13）"), and
``entry/channel/telegram.py`` records the consequence: *"plan 0031 has no
audit log yet, and inventing one here would be a second unowned place
that writes about users."* This is the owned place.

**No OpenTelemetry.** The reference's equivalent
(``observability/hook.go``) starts a span and records two instruments;
this layer imports the standard library and nothing else, like every
other leaf in the rebuild, and hands a :class:`AuditRecord` to a
:class:`AuditSink` the composition root supplied. A deployment that
wants OTEL writes a twelve-line sink; a deployment that does not is not
made to carry the dependency.

**No duration.** Two layers already time a tool call and a third number
would be a third answer: ``ToolResult.metadata["duration_s"]``
(``tools/registry.py:416-422``, measured around the tool itself) and
``EngineEvent.duration_s`` (``engine/types.py:229-247``, measured around
the executor seam and *including* any approval wait). The second is the
one that reaches a surface. This record says a call happened and how it
ended; asking it to also say how long would have needed per-call state
on a hook object shared by every concurrent call.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

from omicsclaw.tools.context import context_value

from .base import Hook, HookCall, HookDenied

_log = logging.getLogger(__name__)

__all__ = [
    "AuditHook",
    "AuditOutcome",
    "AuditRecord",
    "AuditSink",
    "JsonlAuditSink",
    "SESSION_ID_KEY",
    "arguments_digest",
    "outcome_of",
]

SESSION_ID_KEY = "session_id"
"""The :class:`~omicsclaw.tools.context.ToolContext` value naming the session.

Bound by ``entry/turn.py`` around every exchange. Spelled here as a
constant for the reason ``tools/_workspace.py`` spells its own: a typo
read through :func:`~omicsclaw.tools.context.context_value` yields the
default, which is indistinguishable from a surface that bound nothing.
``tests/hooks/test_audit.py`` reads ``entry/turn.py`` as text and asserts
the two spellings still agree — this layer may not import ``entry`` to
check, and an assumption about another layer's literal that nothing
checks is how a whole audit log quietly loses its session column.
"""

_DIGEST_CHARS = 16
"""Hex characters of SHA-256 kept. Matches ``context/offload.py``'s
``offload_key``, so the two shortenings in this tree are one length."""


def arguments_digest(arguments: str) -> str:
    """A short, stable fingerprint of a raw argument payload.

    **The payload itself is never recorded, and that is the point.**
    ``permission/gate.py`` states the rule for the layer that sees the
    same bytes — *"Arguments are never logged — this is the layer that
    sees a bash command line and a write_file body"* — and an audit log
    is a file that outlives the session, so the rule is stricter here,
    not looser. What a call was *for* is already in the transcript, which
    the session owner controls; this file is execution facts.

    A digest is enough to do the one job the raw text would do: join a
    record to the transcript entry that produced it, and tell two calls
    of the same tool apart. Byte-exact, so it joins on what was actually
    sent rather than on a re-encoding of it.
    """
    return hashlib.sha256(arguments.encode("utf-8")).hexdigest()[:_DIGEST_CHARS]


class AuditOutcome(StrEnum):
    """How a call ended. Four values, because four things happen."""

    OK = "ok"
    """The tool returned."""

    ERROR = "error"
    """The tool raised. ``detail`` names the exception class, not its
    message — see :func:`_detail_of`."""

    DENIED = "denied"
    """A hook further down the chain refused. The tool never ran."""

    CANCELLED = "cancelled"
    """The turn was cancelled or interrupted while the tool was running.

    Distinct from :attr:`ERROR` because it is not a fault of the tool and
    a log that conflates the two reports a failure rate that is really a
    user pressing Ctrl-C. Visible at all only because a
    :class:`~omicsclaw.hooks.chain.HookedTool` closes every hook that
    decided, whatever ended the call."""


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """One completed tool call, as a line in an audit trail."""

    tool: str
    """The tool's registered name."""

    outcome: AuditOutcome

    arguments_digest: str
    """See :func:`arguments_digest`. Not the arguments."""

    at: float
    """Wall-clock :func:`time.time` when the record was made.

    Wall clock rather than :func:`time.perf_counter` because a record's
    job is to be correlated with something outside this process — a
    transcript, a surface's log, a person's memory of when they ran it.
    A monotonic counter cannot be."""

    session_id: str = ""
    """Empty when nothing bound a session — a script, a test, a tool
    driven directly. Not an error: the record is still true."""

    detail: str = ""
    """What went wrong, as much of it as may be written down.

    For :attr:`AuditOutcome.ERROR` this is the exception's **class name
    alone** — not its message, which routinely quotes the argument the
    tool could not use. For :attr:`AuditOutcome.DENIED` it is the
    refusal a hook in this deployment composed. Empty otherwise. See
    :func:`_detail_of`, which is where that asymmetry is argued."""

    def as_json(self) -> str:
        """One JSON object on one line, keys sorted.

        Sorted so two records of the same shape are byte-identical
        regardless of field order, which is what lets a diff over an
        audit file mean something.
        """
        return json.dumps(
            {
                "at": self.at,
                "tool": self.tool,
                "outcome": self.outcome.value,
                "arguments_digest": self.arguments_digest,
                "session_id": self.session_id,
                "detail": self.detail,
            },
            sort_keys=True,
            ensure_ascii=False,
        )


@runtime_checkable
class AuditSink(Protocol):
    """Where records go. Supplied by whoever knows where that is.

    ``async`` so a sink may be a socket or a queue.
    :class:`JsonlAuditSink` is the local one; anything else — OTEL, a
    database, a test's list — satisfies this structurally.

    A sink that raises is logged and dropped by :class:`AuditHook`; see
    :class:`~omicsclaw.hooks.chain.HookedTool` for why an observer does
    not get to fail a tool.
    """

    async def write(self, record: AuditRecord) -> None:
        """Record one call. Ordering between calls is not promised."""
        ...


class JsonlAuditSink:
    """Append one JSON object per line to a file.

    JSON Lines rather than a JSON array: an array has to be rewritten to
    be appended to, so a process killed mid-turn leaves a file that no
    parser will open — which is precisely the run whose record is worth
    having.

    The directory is created on first write, not in ``__init__``, so
    constructing a sink for a deployment whose runs never call a tool
    leaves no empty directory behind. Mode ``0o700`` on the directory and
    ``0o600`` on the file, matching ``memory/offload.py``: an audit trail
    names what a machine did and belongs to its owner.

    **The write is blocking**, one short line under an append-mode open,
    the same way :mod:`logging` writes. A sink that must not block the
    event loop is a different sink, and this class being small is what
    makes writing one cheap.
    """

    __slots__ = ("_path", "_prepared")

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._prepared = False

    @property
    def path(self) -> Path:
        """Where records are appended."""
        return self._path

    async def write(self, record: AuditRecord) -> None:
        """Append *record*. Raises if the file cannot be written.

        Raising rather than swallowing is deliberate: the caller is
        :class:`AuditHook`, which contains it and logs it, so the failure
        has exactly one place that decides what it means. A sink that
        silently dropped records would make an empty audit file and a
        quiet machine look identical.
        """
        if not self._prepared:
            self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._prepared = True
        with open(
            self._path, "a", encoding="utf-8", opener=_owner_only
        ) as handle:
            handle.write(record.as_json() + "\n")


def _owner_only(path: str, flags: int) -> int:
    """``open`` opener that creates with ``0o600``.

    Passing ``mode=`` to :func:`open` is not available for text mode, and
    ``chmod`` after the fact leaves a window in which the file exists
    world-readable. An opener closes it.
    """
    return os.open(path, flags, 0o600)


class AuditHook(Hook):
    """Write one :class:`AuditRecord` per completed tool call.

    Overrides two of :class:`~omicsclaw.hooks.Hook`'s three methods and
    leaves ``before_execute`` alone, which is the shape most hooks have:
    it observes, it decides nothing, and nothing it does can change what
    the model reads.

    Mount it **first** in the chain. Ordering is what decides what it can
    see: :meth:`~omicsclaw.hooks.chain.HookedTool.execute` closes hooks
    in reverse, so the first hook mounted is the last told — and it is
    told even when a hook mounted *after* it denied the call, which is
    the only way :attr:`AuditOutcome.DENIED` ever appears. Mounted last,
    it would record every call as ``ok`` or ``error`` and silently omit
    the refusals, which are the records an audit trail exists for. (The
    reference harness mounts its observability hook last, for the
    opposite reason: its interface gives a denied call no closing call at
    all, so position cannot rescue it — ``hooks/hook.go:70-75``.)
    """

    __slots__ = ("_sink",)

    def __init__(self, sink: AuditSink) -> None:
        self._sink = sink

    @property
    def sink(self) -> AuditSink:
        """Where this hook writes."""
        return self._sink

    async def after_execute(self, call: HookCall, output: str) -> str:
        """Record a success and return *output* untouched.

        This hook never rewrites. Returning the argument it was given is
        the whole body, and ``tests/hooks/test_audit.py`` pins it,
        because an observer that changes what the model reads is no
        longer an observer.
        """
        await self._record(call, AuditOutcome.OK)
        return output

    async def on_failure(self, call: HookCall, error: BaseException) -> None:
        """Record a failure, a refusal or a cancellation."""
        await self._record(call, outcome_of(error), detail=_detail_of(error))

    async def _record(
        self, call: HookCall, outcome: AuditOutcome, detail: str = ""
    ) -> None:
        """Build the record and hand it to the sink, containing a raise."""
        record = AuditRecord(
            tool=call.name,
            outcome=outcome,
            arguments_digest=arguments_digest(call.arguments),
            at=time.time(),
            session_id=str(context_value(SESSION_ID_KEY, "") or ""),
            detail=detail,
        )
        try:
            await self._sink.write(record)
        except Exception:
            _log.exception(
                "audit sink refused a %s record for %s",
                outcome.value,
                call.name,
            )


def outcome_of(error: BaseException) -> AuditOutcome:
    """Which of the three failure outcomes *error* is.

    **Public because it has a second consumer.**
    :class:`~omicsclaw.observability.hook.TracingHook` labels a tool span
    with the same vocabulary, and a private copy of these four lines over
    there would be a second answer to "did that call fail, or was it
    refused?" — the duplication :mod:`omicsclaw.hooks` exists to prevent.
    The classification stays here, with the enum it produces.

    ``HookDenied`` first, because it is an :exc:`Exception` and would
    otherwise be filed as a tool error — the tool did not run at all.
    Then anything that is not an :exc:`Exception` (``CancelledError``,
    ``KeyboardInterrupt``, ``SystemExit``), which is the boundary
    ``tools/registry.py:314-321`` already draws between "the tool failed"
    and "something is ending this process".
    """
    if isinstance(error, HookDenied):
        return AuditOutcome.DENIED
    if not isinstance(error, Exception):
        return AuditOutcome.CANCELLED
    return AuditOutcome.ERROR


def _detail_of(error: BaseException) -> str:
    """What may be written down about a failure.

    **A tool's exception contributes its class name and nothing else, and
    that is a repair rather than a simplification.** The first version of
    this function recorded ``ClassName: message`` to match the wording
    the model was shown; ``tests/entry/test_hook_wiring.py`` then caught
    a ``read_file`` failure putting the requested path into the audit
    file — because a tool's error message quotes the argument it could
    not use. That is true of most of them: ``write_file`` names the path,
    ``bash`` quotes the command, ``web_fetch`` echoes the URL. So the
    message is dropped, and the class name is kept because it is a fixed
    vocabulary no argument can reach. The full text is already in the
    transcript, which the session's owner controls and which does not
    outlive the session the way this file does.

    **A refusal is the exception**, and the difference is who wrote the
    string. A :exc:`~omicsclaw.hooks.HookDenied` carries a reason a hook
    in *this deployment's* own code composed, so recording it is
    recording what the deployment chose to say about itself — and a
    refusal with no reason is an audit line nobody can act on. The one
    thing to know: a hook that interpolates its arguments into
    ``deny(...)`` puts them in this file, which is the hook author's
    decision to make and not one this layer can second-guess.
    """
    if isinstance(error, HookDenied):
        return str(error) or type(error).__name__
    return type(error).__name__
