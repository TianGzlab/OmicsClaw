"""The two texts a plan turns into: one for the model, one for a person.

Plan 0039 §3. Kept out of :class:`~omicsclaw.planning.plan.PlanStore`
even though the reference harness puts the first of them on its store
(``plan.go:110``). The store holds state; this renders it; neither needs
the other to be testable. It also keeps the store's dependency list at
"nothing", which is what lets :mod:`omicsclaw.planning.plan` stay a
standard-library module.

Pure functions over a sequence of items. No I/O — :mod:`.archive` owns
the files, and it calls :func:`render_document` for the readable half.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from .plan import PlanItem, PlanStatus

__all__ = [
    "DOCUMENT_TITLE",
    "INJECTION_HEADER",
    "format_plan",
    "render_document",
]


INJECTION_HEADER = (
    "## Current execution plan — authoritative. After a context "
    "compaction or a resumed session, continue from this list, not from "
    "what the conversation above appears to say."
)
"""The first line of every injected block.

**Translated, not ported, and that is the point.** The reference
harness's header is Chinese (``plan.go:107``) because that project's
prompt is; every section of *this* prompt is English — ``SOUL.md``,
``CLAUDE.md``, :data:`~omicsclaw.entry.assembly.SAFETY_RULES`,
:data:`~omicsclaw.entry.assembly.TOOL_GUIDANCE` — and ``SOUL.md``'s first
operating rule is "reply in the user's language; default to English when
unclear". A Chinese instruction arriving after an English prompt is a
language switch nobody asked for, in the one message whose whole job is
to be obeyed. This is plan 0027's rule about borrowed literals, on a
literal that looks like prose.

What survives the translation is what earns the length. The block arrives
as an ordinary user message at the end of the conversation, so nothing
about its *position* says it outranks the summary above it — the sentence
has to say so, and it has to name compaction and resumption specifically,
because those are the two moments when the history the model is reading
disagrees with this list.
"""

DOCUMENT_TITLE = "# Execution plan"
"""Heading of the human-readable plan file."""

_INJECTED_MARKERS = {
    PlanStatus.PENDING: "[ ]",
    PlanStatus.IN_PROGRESS: "[>]",
}
"""Markers for the two statuses that reach an injected block.

``completed`` and ``cancelled`` have none because they never appear
there; a lookup failure would be a bug in :func:`format_plan`'s filter
rather than a marker worth inventing.
"""

_DOCUMENT_MARKERS = {
    PlanStatus.PENDING: "[ ]",
    PlanStatus.IN_PROGRESS: "[>]",
    PlanStatus.COMPLETED: "[x]",
    PlanStatus.CANCELLED: "[-]",
}
"""Markers for the file a person reads, where all four statuses appear.

The document's whole value over the injected block is that it keeps the
finished and the abandoned steps, so this table is complete where the one
above it is deliberately not.
"""


def format_plan(items: Sequence[PlanItem]) -> str:
    """The block re-injected before every model call, or ``""``.

    Only :attr:`~omicsclaw.planning.plan.PlanItem.is_active` items are
    rendered. That is the reference harness's filter (``plan.go:116``)
    and its reason holds here: re-sending a completed step every turn
    spends tokens telling the model something it can already see it did,
    and — worse — pads the list the model is meant to read as "what is
    left".

    An empty result means **do not inject anything**, and the caller is
    expected to test for it rather than append an empty message. A
    conversation ending in a blank user turn is a wasted call at best and
    a 400 at worst.
    """
    lines = [
        f"{_INJECTED_MARKERS[item.status]} {item.content}"
        for item in items
        if item.is_active
    ]
    if not lines:
        return ""
    return "\n".join([INJECTION_HEADER, *lines])


def render_document(
    session_id: str,
    items: Sequence[PlanItem],
    *,
    now: datetime | None = None,
) -> str:
    """The Markdown file a person opens to see what the agent is doing.

    :param session_id: Recorded in the file, because the file's *name*
        may have been made safe for a filesystem and so is not reliably
        the id itself — see :func:`~omicsclaw.planning.archive.safe_name`.
    :param now: The timestamp to stamp it with; defaults to now, in UTC.
        A parameter because a test that cannot fix the clock can only
        assert that the line exists, not what it says.

    Every item appears, in plan order, with its status as a marker —
    unlike :func:`format_plan`. This file is a record, and a record that
    dropped the finished steps would answer "what is left" twice and
    "what happened" never.

    Written with an explicit UTC offset rather than a local one: the
    file outlives the process, is read beside a log, and a bare local
    timestamp from a container is a time nobody can place.
    """
    stamp = (now if now is not None else datetime.now(timezone.utc)).isoformat()
    lines = [
        DOCUMENT_TITLE,
        "",
        f"session: {session_id}" if session_id else "session: -",
        f"updated: {stamp}",
        "",
        "## Items",
        "",
    ]
    if not items:
        lines.append("_(no items yet)_")
    else:
        lines.extend(
            f"- {_DOCUMENT_MARKERS[item.status]} {item.content}" for item in items
        )
    return "\n".join(lines) + "\n"
