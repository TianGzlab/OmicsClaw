"""Where a plan survives a crash, a restart, and the end of a session.

Plan 0039 §2.3. The reference harness stores a plan in its session
database (``sqlite_session.go:185`` and ``:206``).
This layer writes files under the workspace instead, and the reason is
not convenience: the equivalent database change would put a ``plan``
column on ``memory.StoredSession`` and a ``PlanItem`` import inside
:mod:`omicsclaw.memory`, which is a layer that has no business knowing
what a plan is. Files under ``<workspace>/.omicsclaw/`` is the shape
this rebuild already uses for per-session state the conversation does not
carry — offloaded tool results and compaction records both live there
(``entry/compaction.py``).

Two files per session, and they are not redundant::

    <dir>/<session>.json   the machine's copy — the only restore source
    <dir>/<session>.md     the person's copy — never read back

Standard library only.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol, Sequence, runtime_checkable

from .plan import PlanItem, PlanStatus
from .render import render_document

__all__ = [
    "FilePlanArchive",
    "PlanArchive",
    "PlanArchiveError",
    "dump_items",
    "load_items",
    "safe_name",
]

_FILE_MODE = 0o600
"""Owner-only. A plan names what is being analysed, and on a shared
machine that is the same class of hint a ``bash`` command line is.

Note what this does **not** claim: the directories above the file are
created with the process umask, because :meth:`Path.mkdir` applies its
``mode`` to the leaf only and a docstring promising an owner-only *tree*
would be false for every intermediate level — plan 0038 §8.2 paid for
that sentence once already.
"""


class PlanArchiveError(RuntimeError):
    """A stored plan exists and could not be used.

    Deliberately **not** raised for an absent file. The distinction is
    the one :mod:`omicsclaw.skills` draws between configuration and
    discovery: no file means no plan yet, which is the ordinary state of
    every new session, while a file that cannot be parsed means somebody
    — a half-finished write, a hand edit, a future format — left
    something here that this code would otherwise silently discard. The
    first is silence; the second is loud, and whoever catches it is in a
    layer that can say so in a log.
    """


@runtime_checkable
class PlanArchive(Protocol):
    """Where :class:`~omicsclaw.planning.book.PlanBook` keeps plans.

    A Protocol so a deployment that already has somewhere to put session
    state — a database, an object store — satisfies it without
    inheriting anything, and so the book can be exercised against an
    in-memory double that has no filesystem at all.

    Synchronous, unlike :class:`~omicsclaw.entry.session.SessionStore`,
    and the asymmetry is deliberate. Saving happens inside
    :data:`~omicsclaw.planning.plan.PlanWriteSink`, which is called from
    :meth:`~omicsclaw.planning.plan.PlanStore.write` — a synchronous
    method reachable from a tool that may itself be running on a worker
    thread. An ``async`` signature here would have to be bridged back at
    that seam, and every bridge over a running event loop is a way to
    deadlock a tool call.
    """

    def load(self, session_id: str) -> tuple[PlanItem, ...]:
        """The stored plan, or ``()`` when there is not one yet.

        :raises PlanArchiveError: something is stored and unusable.
        """
        ...

    def save(self, session_id: str, items: Sequence[PlanItem]) -> None:
        """Replace what is stored for *session_id*.

        :raises PlanArchiveError: the plan could not be stored.
        """
        ...


def dump_items(items: Sequence[PlanItem]) -> str:
    """Serialise *items* to the JSON text an archive stores.

    ``ensure_ascii=False``: plan contents are written in the
    conversation's language, and escaping every non-ASCII character
    would quadruple a Chinese plan's size and make the file unreadable
    to the person it is partly written for.
    """
    payload = [
        {"id": item.id, "content": item.content, "status": item.status.value}
        for item in items
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def load_items(text: str) -> tuple[PlanItem, ...]:
    """Parse what :func:`dump_items` wrote.

    :raises PlanArchiveError: the text is not a list of well-formed
        items. **Every** defect refuses the whole file rather than
        skipping the item that caused it: the anti-cheat rule in
        :mod:`omicsclaw.planning.rules` decides by comparing a write
        against prior status, so a plan restored with items silently
        missing is a plan whose history is wrong in exactly the direction
        that lets a completion through unexamined.

    An unrecognised status is such a defect, and that includes a status
    this version has not heard of. A newer format is not a corrupt file,
    but it is not one this code can reason about either.
    """
    try:
        payload: Any = json.loads(text)
    except ValueError as exc:
        raise PlanArchiveError(f"stored plan is not valid JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise PlanArchiveError(
            f"stored plan is a {type(payload).__name__}, not a list of items"
        )
    items: list[PlanItem] = []
    for position, entry in enumerate(payload):
        if not isinstance(entry, dict):
            raise PlanArchiveError(
                f"stored plan item {position} is a {type(entry).__name__}, "
                "not an object"
            )
        missing = [key for key in ("id", "content", "status") if key not in entry]
        if missing:
            raise PlanArchiveError(
                f"stored plan item {position} is missing {', '.join(missing)}"
            )
        try:
            status = PlanStatus(entry["status"])
        except ValueError as exc:
            known = ", ".join(value.value for value in PlanStatus)
            raise PlanArchiveError(
                f"stored plan item {position} has status "
                f"{entry['status']!r}; known statuses are {known}"
            ) from exc
        items.append(
            PlanItem(id=str(entry["id"]), content=str(entry["content"]), status=status)
        )
    return tuple(items)


def safe_name(session_id: str) -> str:
    """A filename that is only ever one file, inside the given directory.

    Session ids come from :func:`~omicsclaw.entry.session.new_turn_id`
    and are hex, but this function does not get to assume that: a
    channel adapter is free to key a session on a chat id, and an id
    containing ``/`` or ``..`` would otherwise write a plan wherever it
    liked. Everything outside ``[A-Za-z0-9._-]`` becomes ``_``, and a
    name that empties out becomes ``session``.

    **Two different ids can collide here**, and that is accepted rather
    than solved: the pair ``a/b`` and ``a_b`` share a file. Solving it
    means hashing, which makes the directory unreadable to the person
    the ``.md`` half exists for. Real ids in this repository are hex.
    """
    cleaned = "".join(
        char if char.isalnum() or char in "._-" else "_" for char in session_id
    )
    cleaned = cleaned.strip("._")
    return cleaned or "session"


class FilePlanArchive:
    """Two files per session under one directory.

    :param directory: Created on first save, not on construction —
        building an archive for a deployment that never writes a plan
        should leave no trace.
    """

    __slots__ = ("directory",)

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)

    def paths(self, session_id: str) -> tuple[Path, Path]:
        """``(json, markdown)`` for *session_id*, whether or not they exist."""
        stem = safe_name(session_id)
        return self.directory / f"{stem}.json", self.directory / f"{stem}.md"

    def load(self, session_id: str) -> tuple[PlanItem, ...]:
        """Read the JSON half. The Markdown half is never read back.

        A file that is not there is an empty plan. A file that is there
        and unreadable raises, including for an :exc:`OSError` — a
        permissions problem on a plan file is a fact about the machine,
        and treating it as "no plan" would start the session over
        silently every time.
        """
        path, _ = self.paths(session_id)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ()
        except OSError as exc:
            raise PlanArchiveError(f"could not read {path}: {exc}") from exc
        return load_items(text)

    def save(self, session_id: str, items: Sequence[PlanItem]) -> None:
        """Write both halves, the JSON one atomically.

        The JSON file goes through a temporary file and :func:`os.replace`
        rather than being opened for truncation. Plan 0029's finding #4
        is the reason and it was found the expensive way: ``O_TRUNC``
        empties a file before the first byte of the replacement is
        written, so a failure between the two leaves an empty plan where
        a valid one was — and an empty plan reads as "no plan", which is
        indistinguishable from a new session.

        The Markdown half is written plainly. It is a rendering of the
        JSON, nothing reads it back, and a torn one costs a person one
        confusing glance rather than a session its state. It is also
        written **second**, so a crash between the two leaves the record
        stale rather than leaving the state unrecoverable.
        """
        json_path, markdown_path = self.paths(session_id)
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self._replace(json_path, dump_items(items))
            markdown_path.write_text(
                render_document(session_id, items), encoding="utf-8"
            )
            os.chmod(markdown_path, _FILE_MODE)
        except OSError as exc:
            raise PlanArchiveError(
                f"could not save plan to {json_path}: {exc}"
            ) from exc

    def _replace(self, path: Path, text: str) -> None:
        """Write *text* to *path* atomically, at :data:`_FILE_MODE`.

        The temporary file is made in the destination's own directory
        because :func:`os.replace` is only atomic within one filesystem,
        and ``/tmp`` is routinely a different one — under a container it
        is routinely a tmpfs.
        """
        handle, temporary = tempfile.mkstemp(
            dir=str(self.directory), prefix=path.name, suffix=".tmp"
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(text)
            os.chmod(temporary, _FILE_MODE)
            os.replace(temporary, path)
        except BaseException:
            # Best effort: the write failed, and failing to clean up after
            # it must not replace that error with this one.
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
