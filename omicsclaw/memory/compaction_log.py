"""An append-only record of the compactions each conversation went through."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from omicsclaw.context import Anchors, CompactionRecord, OffloadEntry, Pressure

from .offload import safe_name

__all__ = ["JsonlCompactionLog", "LoggedCompaction", "record_from_dict"]


@dataclass(frozen=True, slots=True)
class LoggedCompaction:
    """One compaction as it was logged.

    :param id: Unique identifier of the entry.
    :param session_id: The conversation it happened in.
    :param timestamp: Wall clock when it was logged, in seconds.
    :param record: What the compaction did.
    """

    id: str
    session_id: str
    timestamp: float
    record: CompactionRecord


def _record_to_dict(record: CompactionRecord) -> dict[str, Any]:
    data = asdict(record)
    data["compression_ratio"] = record.compression_ratio
    return data


def record_from_dict(data: dict[str, Any]) -> CompactionRecord:
    """Rebuild a :class:`~omicsclaw.context.CompactionRecord` from its JSON.

    Unknown keys are ignored and missing optional ones take their
    defaults, so entries written by an older or newer version still load.

    :raises KeyError: A required field is missing.
    :raises ValueError: A tier name is not one of :class:`Pressure`.
    """
    known = CompactionRecord.__dataclass_fields__
    values = {key: value for key, value in data.items() if key in known}
    values["pressure"] = Pressure(values["pressure"])
    if "trigger" in values:
        values["trigger"] = Pressure(values["trigger"])
    if isinstance(values.get("anchors"), dict):
        values["anchors"] = Anchors(**values["anchors"])
    values["offloaded"] = tuple(
        OffloadEntry(**entry) for entry in values.get("offloaded", ())
    )
    values["advisories"] = tuple(values.get("advisories", ()))
    return CompactionRecord(**values)


class JsonlCompactionLog:
    """Compaction records as JSON Lines, one file per conversation.

    ``<directory>/<session>.jsonl``, appended to and never rewritten. The
    directory is created ``0700`` and files ``0600``.

    :param directory: Where the files live.
    """

    def __init__(self, directory: Path) -> None:
        self._directory = Path(directory)
        self._lock = threading.Lock()

    def path_for(self, session_id: str) -> Path:
        """The file holding *session_id*'s records."""
        return self._directory / f"{safe_name(session_id)}.jsonl"

    async def append(
        self,
        session_id: str,
        record: CompactionRecord,
        *,
        timestamp: float | None = None,
    ) -> LoggedCompaction:
        """Add *record* to the end of *session_id*'s file.

        :raises OSError: The file could not be written.
        """
        logged = LoggedCompaction(
            id=uuid.uuid4().hex,
            session_id=session_id,
            timestamp=time.time() if timestamp is None else timestamp,
            record=record,
        )
        line = json.dumps(
            {
                "id": logged.id,
                "session_id": logged.session_id,
                "timestamp": logged.timestamp,
                **_record_to_dict(record),
            },
            ensure_ascii=False,
        )
        await asyncio.to_thread(self._append_line, self.path_for(session_id), line)
        return logged

    async def list(self, session_id: str) -> tuple[LoggedCompaction, ...]:
        """Every record logged for *session_id*, oldest first.

        A missing file is an empty log. A line that cannot be read back is
        skipped.
        """
        return await asyncio.to_thread(self._read, session_id)

    async def purge(self, session_id: str) -> None:
        """Delete *session_id*'s file, if there is one."""
        await asyncio.to_thread(self.path_for(session_id).unlink, missing_ok=True)

    def _append_line(self, path: Path, line: str) -> None:
        with self._lock:
            self._directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            handle = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(handle, "a", encoding="utf-8") as stream:
                stream.write(line + "\n")

    def _read(self, session_id: str) -> tuple[LoggedCompaction, ...]:
        path = self.path_for(session_id)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ()
        entries: list[LoggedCompaction] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                entries.append(
                    LoggedCompaction(
                        id=data.pop("id"),
                        session_id=data.pop("session_id"),
                        timestamp=float(data.pop("timestamp")),
                        record=record_from_dict(data),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return tuple(entries)
