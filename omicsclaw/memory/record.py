"""The session record this layer stores and returns."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Mapping

from omicsclaw.context import CompactionState
from omicsclaw.schema import Message

_EMPTY_VALUES: Mapping[str, object] = {}


@dataclass(slots=True)
class StoredSession:
    """One conversation as it sits in storage.

    Field-for-field compatible with the session type the entry layer
    hands around, so a store returning this satisfies its ``SessionStore``
    protocol structurally and no conversion runs at the seam.

    :param session_id: Identifier the caller addresses the session by.
    :param history: Conversation without any system message.
    :param compaction: Summary and anchors carried between exchanges.
    :param created_at: Wall clock at creation.
    :param values: Session-level facts made available to tools.
    """

    session_id: str
    history: tuple[Message, ...] = ()
    compaction: CompactionState = field(default_factory=CompactionState)
    created_at: float = field(default_factory=time.time)
    values: Mapping[str, object] = field(default_factory=lambda: _EMPTY_VALUES)
