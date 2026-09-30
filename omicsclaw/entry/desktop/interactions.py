"""Process-local state behind the Desktop return channels, and their logic.

:class:`DesktopInteractions` is created once per
:func:`~omicsclaw.entry.desktop.server.create_desktop_app` and holds three
bounded maps, all in memory and none persisted:

* the approval requests a ``/chat/stream`` body has shown as a
  ``permission_request`` card, keyed by ``request_id``, so that
  ``/chat/permission`` knows the session and the tool a decision is about;
* the tools a session has allowed for the rest of its life in this
  process ("allow for this session"), keyed by ``session_id``;
* the sessions in the ``full_access`` permission profile;
* ``(session_id, source_request_id) → turn_id``, so that ``/chat/abort``
  can find the exchange a client is streaming, and a resuming
  ``/chat/stream`` the exchange to reattach to;
* ``turn_id → TurnUsage``, what the model calls of each exchange cost,
  gathered across every stream that observed it.

:func:`answer_permission`, :func:`abort_chat` and
:func:`change_permission_profile` are the logic of ``POST
/chat/permission``, ``POST /chat/abort`` and ``POST
/chat/session-permission-profile`` over an already parsed JSON document,
with no web framework in their signatures.

``full_access`` allows, without a card, every request that is not marked
``ask_every_time`` — the same line ``auto-approve`` draws — so a
dangerous command, an explicit ``ask`` rule and a change to a protected
file are still asked about. It lives here, per session and in memory,
rather than in the permission gate's mode, which is one per process and
shared by every session.

A session grant and ``full_access`` are applied by an observer of the
stream: an approval request raised while no ``/chat/stream`` body is
reading the exchange is answered only once somebody observes it again.
"""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Final, Mapping

from omicsclaw.entry.approval import ApprovalBroker
from omicsclaw.entry.assembly import AgentApp
from omicsclaw.entry.events import TurnEvent
from omicsclaw.entry.turn import TurnHandle
from omicsclaw.tools import ApprovalDecision, ApprovalRequest

from .turn_submission import (
    DEFAULT_PERMISSION_PROFILE,
    FULL_ACCESS,
    PERMISSION_PROFILES,
    DesktopIngressError,
)

__all__ = [
    "DEFAULT_MAX_PENDING_APPROVALS",
    "DENIED_REASON",
    "PERMISSION_PROFILES",
    "USAGE_KEYS",
    "DesktopInteractions",
    "PendingApproval",
    "TurnUsage",
    "abort_chat",
    "answer_permission",
    "change_permission_profile",
]

_log = logging.getLogger(__name__)

DEFAULT_MAX_PENDING_APPROVALS: Final = 256
"""Approval requests remembered before settled ones are dropped."""

DENIED_REASON: Final = "denied in the desktop app"
"""The reason the model is given when a person denies without a message."""

PERMISSION_BEHAVIORS: Final = frozenset({"allow", "deny"})
PERMISSION_SCOPES: Final = frozenset({"once", "session", "always"})

_REQUEST_ID = re.compile(r"\A([0-9a-f]{32})#[1-9][0-9]{0,8}\Z")
"""``<turn_id>#<n>``: a 32-hex turn id, then a positive counter."""

_SOURCE_REQUEST_ID = re.compile(r"\A[0-9a-f]{32}\Z")

USAGE_KEYS: Final = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
)
"""The token counts a ``result`` frame's ``usage`` sums, as ``to_wire``
names them on a ``TURN_END``."""


class TurnUsage:
    """The model calls of one exchange, and which of its events were read.

    Every stream body observing the exchange records here each
    ``TURN_END`` it reads, keyed by the event's sequence number so that a
    call two bodies both read counts once, and marks the sequence numbers
    it read. A resumed stream can then report the usage of the whole
    exchange, including the calls an earlier connection read.
    """

    __slots__ = ("_calls", "_spans")

    def __init__(self) -> None:
        self._calls: dict[int, dict[str, int] | None] = {}
        self._spans: list[list[int]] = []

    def record_call(self, seq: int, usage: Mapping[str, Any] | None) -> None:
        """Record the model call whose ``TURN_END`` is *seq*.

        *usage* is ``None`` when the call reported none. The first record
        of a sequence number is kept.
        """
        if seq in self._calls:
            return
        if usage is None:
            self._calls[seq] = None
            return
        counts = dict.fromkeys(USAGE_KEYS, 0)
        for key in USAGE_KEYS:
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                counts[key] = value
        self._calls[seq] = counts

    def cover(self, start: int, end: int) -> None:
        """Mark the sequence numbers *start* to *end* as read by a body."""
        if end < start:
            return
        spans = self._spans
        if spans and spans[-1][0] <= start <= spans[-1][1] + 1:
            spans[-1][1] = max(spans[-1][1], end)
            return
        spans.append([start, end])
        spans.sort()
        merged: list[list[int]] = []
        for span in spans:
            if merged and span[0] <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], span[1])
            else:
                merged.append(span)
        self._spans = merged

    def covers(self, end: int) -> bool:
        """Whether every sequence number from 1 to *end* was read."""
        return any(start <= 1 and end <= stop for start, stop in self._spans)

    def result(self, end: int) -> dict[str, Any]:
        """``usage``, ``usage_reported`` and ``model_calls`` for an exchange
        whose last event is *end*.

        ``usage`` sums the calls that reported usage, ``None`` when none
        did. ``usage_reported`` is true only when at least one call was
        recorded, every recorded call reported usage, and every event up
        to *end* was read, so that no ``TURN_END`` can have gone unseen.
        """
        reported = [counts for counts in self._calls.values() if counts is not None]
        usage: dict[str, int] | None = None
        if reported:
            usage = {key: sum(counts[key] for counts in reported) for key in USAGE_KEYS}
        calls = len(self._calls)
        return {
            "usage": usage,
            "usage_reported": calls > 0
            and len(reported) == calls
            and self.covers(end),
            "model_calls": calls,
        }


@dataclass(frozen=True, slots=True)
class PendingApproval:
    """One approval request a ``permission_request`` card was shown for."""

    session_id: str
    turn_id: str
    request: ApprovalRequest


class DesktopInteractions:
    """Bounded, in-memory interaction state for one Desktop server.

    Every map is bounded, and eviction only ever drops entries that no
    longer matter: an approval that is no longer outstanding, a request
    whose exchange has ended. Live entries are kept even past the bound.
    Session grants and ``full_access`` sessions are dropped
    least-recently-used first, which at worst makes the app ask again.

    Not thread-safe; every method runs on the server's event loop.
    """

    __slots__ = (
        "_app",
        "_full_access",
        "_grants",
        "_max_granted_sessions",
        "_max_pending",
        "_max_requests",
        "_pending",
        "_requests",
        "_usage",
    )

    def __init__(
        self,
        app: AgentApp,
        *,
        max_pending: int = DEFAULT_MAX_PENDING_APPROVALS,
        max_requests: int | None = None,
        max_granted_sessions: int | None = None,
    ) -> None:
        """*max_requests* and *max_granted_sessions* default to
        ``app.config.max_sessions``, the number of exchanges the session
        registry retains. *max_requests* bounds the usage ledgers too;
        *max_granted_sessions* bounds the session grants and the
        ``full_access`` sessions alike."""
        limit = app.config.max_sessions
        self._app = app
        self._max_pending = max_pending
        self._max_requests = limit if max_requests is None else max_requests
        self._max_granted_sessions = (
            limit if max_granted_sessions is None else max_granted_sessions
        )
        self._pending: OrderedDict[str, PendingApproval] = OrderedDict()
        self._grants: OrderedDict[str, set[str]] = OrderedDict()
        self._full_access: OrderedDict[str, None] = OrderedDict()
        self._requests: OrderedDict[tuple[str, str], str] = OrderedDict()
        self._usage: OrderedDict[str, TurnUsage] = OrderedDict()

    # ---- which exchange a request started -------------------------------

    def remember_request(
        self, session_id: str, source_request_id: str, turn_id: str
    ) -> None:
        """Record that *source_request_id* on *session_id* is *turn_id*.

        Past the bound, the oldest entries whose exchange the registry no
        longer retains are dropped. A retained exchange, finished or not,
        can still be resumed, so its entry is kept, as is the one just
        recorded.
        """
        if not source_request_id:
            return
        key = (session_id, source_request_id)
        self._requests[key] = turn_id
        self._requests.move_to_end(key)
        if len(self._requests) <= self._max_requests:
            return
        for held_key, held_turn in tuple(self._requests.items()):
            if len(self._requests) <= self._max_requests:
                break
            if held_key == key or self._handle(held_turn) is not None:
                continue
            del self._requests[held_key]

    def turn_for(self, session_id: str, source_request_id: str) -> str | None:
        """The ``turn_id`` a request started, or ``None`` if unknown."""
        return self._requests.get((session_id, source_request_id))

    # ---- usage per exchange ---------------------------------------------

    def usage_for(self, turn_id: str) -> TurnUsage:
        """The usage ledger of *turn_id*, created on first use.

        Past the bound, the oldest ledgers of exchanges the registry no
        longer retains are dropped; a retained exchange can still be
        resumed, so its ledger is kept.
        """
        ledger = self._usage.get(turn_id)
        if ledger is not None:
            return ledger
        ledger = TurnUsage()
        self._usage[turn_id] = ledger
        if len(self._usage) > self._max_requests:
            for held_turn in tuple(self._usage):
                if len(self._usage) <= self._max_requests:
                    break
                if held_turn != turn_id and self._handle(held_turn) is None:
                    del self._usage[held_turn]
        return ledger

    # ---- session grants -------------------------------------------------

    def grant(self, session_id: str, tool_name: str) -> None:
        """Allow *tool_name* in *session_id* for the life of this process.

        A grant never answers a request marked ``ask_every_time``.
        """
        tools = self._grants.pop(session_id, set())
        tools.add(tool_name)
        self._grants[session_id] = tools
        while len(self._grants) > self._max_granted_sessions:
            self._grants.popitem(last=False)

    def is_granted(self, session_id: str, tool_name: str) -> bool:
        """Whether *session_id* allowed *tool_name* for the session."""
        tools = self._grants.get(session_id)
        if tools is None or tool_name not in tools:
            return False
        self._grants.move_to_end(session_id)
        return True

    # ---- permission profiles --------------------------------------------

    def set_permission_profile(
        self, session_id: str, profile: str
    ) -> tuple[str, ...]:
        """Put *session_id* in *profile*, ``"default"`` or ``"full_access"``.

        Switching to ``full_access`` also allows every outstanding request
        of the session that is not marked ``ask_every_time``, and returns
        their ids; switching to ``default`` settles nothing.

        :raises ValueError: *profile* is not one of
            :data:`PERMISSION_PROFILES`.
        """
        if profile not in PERMISSION_PROFILES:
            raise ValueError(f"unknown permission profile {profile!r}")
        if profile == DEFAULT_PERMISSION_PROFILE:
            self._full_access.pop(session_id, None)
            return ()
        self._full_access[session_id] = None
        self._full_access.move_to_end(session_id)
        while len(self._full_access) > self._max_granted_sessions:
            self._full_access.popitem(last=False)
        return self._settle_outstanding(session_id, tool_name=None)

    def permission_profile(self, session_id: str) -> str:
        """``"full_access"`` or ``"default"`` for *session_id*."""
        if session_id in self._full_access:
            return FULL_ACCESS
        return DEFAULT_PERMISSION_PROFILE

    def _answers_without_a_card(self, session_id: str, request: ApprovalRequest) -> bool:
        if request.ask_every_time:
            return False
        if session_id in self._full_access:
            self._full_access.move_to_end(session_id)
            return True
        return self.is_granted(session_id, request.tool_name)

    def can_remember(self, request: ApprovalRequest | None) -> bool:
        """Whether "always allow" could take effect for *request*.

        ``False`` for no request, and for a call that changes a file the
        permission gate protects (see
        :meth:`~omicsclaw.entry.AgentApp.can_remember_approval`).
        """
        if request is None:
            return False
        return bool(self._app.can_remember_approval(request))

    # ---- approval requests shown on the stream --------------------------

    def admit_approval(self, event: TurnEvent, approvals: ApprovalBroker) -> bool:
        """Decide what one ``APPROVAL_REQUIRED`` frame becomes.

        Returns ``True`` when a ``permission_request`` card must be shown:
        the request is still outstanding and neither a session grant nor
        ``full_access`` answers it. A request that is not marked
        ``ask_every_time``, in a session that granted its tool or is in
        ``full_access``, is allowed here and shows no card. A request
        that is no longer outstanding — answered, or replayed from the
        ring after it was settled — shows nothing.
        """
        request_id = event.request_id
        if request_id not in approvals.pending():
            self._pending.pop(request_id, None)
            return False
        request = event.approval
        if request is None:
            return True
        if self._answers_without_a_card(event.session_id, request):
            approvals.settle(request_id, ApprovalDecision(approved=True))
            self._pending.pop(request_id, None)
            return False
        self._remember_pending(
            request_id, PendingApproval(event.session_id, event.turn_id, request)
        )
        return True

    def pending_approval(self, request_id: str) -> PendingApproval | None:
        """The request a card was shown for, if it is still remembered."""
        return self._pending.get(request_id)

    def forget_approval(self, request_id: str) -> None:
        """Drop one remembered request. Unknown ids are a no-op."""
        self._pending.pop(request_id, None)

    def settle_granted(self, session_id: str, tool_name: str) -> tuple[str, ...]:
        """Allow every outstanding request a new session grant answers.

        Covers the requests of *session_id* for *tool_name* that are not
        marked ``ask_every_time``. Returns the ids that were settled.
        """
        return self._settle_outstanding(session_id, tool_name=tool_name)

    def _settle_outstanding(
        self, session_id: str, *, tool_name: str | None
    ) -> tuple[str, ...]:
        """Allow the remembered requests of *session_id* that are not marked
        ``ask_every_time``, only those for *tool_name* unless it is ``None``."""
        settled: list[str] = []
        for request_id, held in tuple(self._pending.items()):
            if held.session_id != session_id or held.request.ask_every_time:
                continue
            if tool_name is not None and held.request.tool_name != tool_name:
                continue
            handle = self._handle(held.turn_id)
            if handle is not None and handle.approvals.settle(
                request_id, ApprovalDecision(approved=True)
            ):
                settled.append(request_id)
            del self._pending[request_id]
        return tuple(settled)

    def _remember_pending(self, request_id: str, entry: PendingApproval) -> None:
        self._pending[request_id] = entry
        self._pending.move_to_end(request_id)
        if len(self._pending) <= self._max_pending:
            return
        for held_id, held in tuple(self._pending.items()):
            if len(self._pending) <= self._max_pending:
                break
            handle = self._handle(held.turn_id)
            if (
                handle is not None
                and not handle.done
                and held_id in handle.approvals.pending()
            ):
                continue
            del self._pending[held_id]

    def _handle(self, turn_id: str) -> TurnHandle | None:
        registry = self._app.sessions
        if registry is None:
            return None
        try:
            return registry.handle(turn_id)
        except KeyError:
            return None


# ---- POST /chat/permission --------------------------------------------


async def answer_permission(
    app: AgentApp,
    interactions: DesktopInteractions,
    document: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply one decision to one outstanding approval request.

    *document* is ``{request_id, decision: {behavior, scope?, message?}}``
    with ``behavior`` ``"allow"`` or ``"deny"`` and ``scope`` ``"once"``
    (the default), ``"session"`` or ``"always"``. ``"session"`` on an
    allow also grants the tool to the session and allows that session's
    other outstanding requests for it; on a request marked
    ``ask_every_time`` it applies as ``"once"``. ``"always"`` on an allow also
    writes a permission rule allowing exactly this call from now on
    (:meth:`~omicsclaw.entry.AgentApp.remember_approval`); it applies as
    ``"once"`` when the call changes a protected file, when this
    deployment has no rule file, or when the rule cannot be written. A
    deny always applies once. A deny's ``message`` is the reason the
    model is given, :data:`DENIED_REASON` when absent.

    Returns ``{ok: True, request_id, behavior, scope, session_id,
    remembered_pattern}`` where ``scope`` is the scope applied and
    ``remembered_pattern`` the rule written (``None`` unless ``scope`` is
    ``"always"``), or
    ``{ok: False, request_id, status}`` with ``status`` ``"expired"`` (the
    exchange has ended or is no longer retained) or ``"resolved"`` (the
    request was already answered).

    :raises DesktopIngressError: 422 when *document* is malformed.
    """
    request_id, behavior, scope, message = _permission_decision(document)
    turn_id = request_id.partition("#")[0]
    handle = _retained(app, turn_id)
    if handle is None or handle.done:
        interactions.forget_approval(request_id)
        return {"ok": False, "request_id": request_id, "status": "expired"}
    if request_id not in handle.approvals.pending():
        interactions.forget_approval(request_id)
        return {"ok": False, "request_id": request_id, "status": "resolved"}

    pending = interactions.pending_approval(request_id)
    if behavior == "deny":
        decision = ApprovalDecision(approved=False, reason=message or DENIED_REASON)
        scope = "once"
    else:
        decision = ApprovalDecision(approved=True)
        if scope == "session" and (
            pending is None or pending.request.ask_every_time
        ):
            scope = "once"
        if scope == "always" and (
            pending is None or not interactions.can_remember(pending.request)
        ):
            scope = "once"

    if not handle.approvals.settle(request_id, decision):
        interactions.forget_approval(request_id)
        return {"ok": False, "request_id": request_id, "status": "resolved"}
    interactions.forget_approval(request_id)
    remembered: str | None = None
    if scope == "session" and pending is not None:
        interactions.grant(handle.session_id, pending.request.tool_name)
        interactions.settle_granted(handle.session_id, pending.request.tool_name)
    if scope == "always" and pending is not None:
        remembered = _remember(app, pending.request)
        if remembered is None:
            scope = "once"
    return {
        "ok": True,
        "request_id": request_id,
        "behavior": behavior,
        "scope": scope,
        "session_id": handle.session_id,
        "remembered_pattern": remembered,
    }


def _remember(app: AgentApp, request: ApprovalRequest) -> str | None:
    """Write the ``allow`` rule for *request*; ``None`` when none was written.

    A rule file that cannot be written is logged, not raised: the call was
    already allowed, and that answer stands.
    """
    try:
        return app.remember_approval(request)
    except OSError as exc:
        _log.warning("could not write the permission rule: %s", type(exc).__name__)
        return None


def _permission_decision(
    document: Mapping[str, Any],
) -> tuple[str, str, str, str]:
    request_id = document.get("request_id")
    if not isinstance(request_id, str) or _REQUEST_ID.match(request_id) is None:
        raise DesktopIngressError("invalid_request_id")
    decision = document.get("decision")
    if not isinstance(decision, Mapping):
        raise DesktopIngressError("invalid_decision")
    behavior = decision.get("behavior")
    if behavior not in PERMISSION_BEHAVIORS:
        raise DesktopIngressError("invalid_decision")
    scope = decision.get("scope")
    if scope is None:
        scope = "once"
    if not isinstance(scope, str):
        raise DesktopIngressError("invalid_decision")
    if scope not in PERMISSION_SCOPES:
        raise DesktopIngressError("unsupported_scope")
    message = decision.get("message")
    if message is None:
        message = ""
    if not isinstance(message, str):
        raise DesktopIngressError("invalid_decision")
    return request_id, behavior, scope, message.strip()


# ---- POST /chat/session-permission-profile ------------------------------


async def change_permission_profile(
    app: AgentApp,
    interactions: DesktopInteractions,
    document: Mapping[str, Any],
) -> dict[str, Any]:
    """Put one session in the ``default`` or ``full_access`` profile.

    *document* is ``{session_id, permission_profile}``. Switching to
    ``full_access`` allows at once the session's outstanding requests that
    are not marked ``ask_every_time``.

    Returns ``{ok: True, session_id, permission_profile, active,
    auto_approved_requests}``: ``active`` is whether an exchange of the
    session is running now, and ``auto_approved_requests`` how many
    outstanding requests the switch allowed.

    :raises DesktopIngressError: 422 ``invalid_session_id`` or
        ``invalid_permission_profile`` when *document* is malformed.
    """
    session_id = document.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise DesktopIngressError("invalid_session_id")
    profile = document.get("permission_profile")
    if not isinstance(profile, str) or profile not in PERMISSION_PROFILES:
        raise DesktopIngressError("invalid_permission_profile")
    settled = interactions.set_permission_profile(session_id, profile)
    registry = app.sessions
    active = registry is not None and any(
        handle.session_id == session_id for handle in registry.running()
    )
    return {
        "ok": True,
        "session_id": session_id,
        "permission_profile": profile,
        "active": active,
        "auto_approved_requests": len(settled),
    }


# ---- POST /chat/abort -------------------------------------------------


async def abort_chat(
    app: AgentApp,
    interactions: DesktopInteractions,
    document: Mapping[str, Any],
) -> dict[str, Any]:
    """Cancel the exchange a ``/chat/stream`` request started.

    *document* is ``{session_id, source_request_id}``, the pair the
    stream was opened with. Cancelling is idempotent. The stream of a
    cancelled exchange ends with an ``error`` frame whose data is
    ``"cancelled"``, then ``done``; an exchange still queued behind
    another one on its session ends that way when its turn comes, without
    running.

    Returns ``{ok: True, session_id, source_request_id, turn_id, state}``
    where ``state`` is ``"cancelling"``, or ``"terminal"`` when the
    exchange had already ended.

    :raises DesktopIngressError: 422 when *document* is malformed, 404
        ``turn_not_found`` when no retained exchange matches.
    """
    session_id = document.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise DesktopIngressError("invalid_session_id")
    source_request_id = document.get("source_request_id")
    if (
        not isinstance(source_request_id, str)
        or _SOURCE_REQUEST_ID.match(source_request_id) is None
    ):
        raise DesktopIngressError("invalid_source_request_id")

    turn_id = interactions.turn_for(session_id, source_request_id)
    handle = _retained(app, turn_id) if turn_id is not None else None
    if turn_id is None or handle is None:
        raise DesktopIngressError("turn_not_found", status_code=404)
    handle.cancel()
    return {
        "ok": True,
        "session_id": session_id,
        "source_request_id": source_request_id,
        "turn_id": turn_id,
        "state": "terminal" if handle.done else "cancelling",
    }


def _retained(app: AgentApp, turn_id: str) -> TurnHandle | None:
    registry = app.sessions
    if registry is None:
        raise RuntimeError(
            "this AgentApp has no session registry; call attach_sessions(app) "
            "before serving the Desktop routes"
        )
    try:
        return registry.handle(turn_id)
    except KeyError:
        return None
