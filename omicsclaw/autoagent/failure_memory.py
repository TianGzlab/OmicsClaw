"""Failure memory — persistent record of failed patches.

Failed patches are written to ``failure_bank.jsonl`` so the Meta-Agent
can learn from past mistakes.  Each entry captures:
- The patch plan (diff summary, reasoning)
- Why it failed (gate failures, error summary)
- Iteration context

The failure bank is consumed by the harness directive builder to
populate the "Failure History" section.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FailureRecord:
    """One failed patch attempt."""

    iteration: int
    reasoning: str = ""
    diff_summary: str = ""
    description: str = ""
    gate_failures: list[str] = field(default_factory=list)
    error_summary: str = ""
    target_files: list[str] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FailureRecord:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class FailureBank:
    """Append-only JSON Lines store of failed patches.

    Thread-safe.  Records are loaded from disk on construction
    and new records are appended atomically.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._records: list[FailureRecord] = []
        self._lock = threading.Lock()
        if self.path.exists():
            self._load()

    def append(self, record: FailureRecord) -> None:
        """Append a failure record (in memory + on disk)."""
        with self._lock:
            self._records.append(record)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), default=str) + "\n")

    def all_failures(self) -> list[FailureRecord]:
        """Return all failure records."""
        with self._lock:
            return list(self._records)

    def recent(self, n: int = 5) -> list[FailureRecord]:
        """Return the N most recent failures."""
        with self._lock:
            return list(self._records[-n:])

    def to_directive_context(self, n: int = 5) -> list[dict[str, Any]]:
        """Format recent failures for the harness directive.

        Returns a list of dicts suitable for ``build_harness_directive``'s
        ``failure_history`` parameter.
        """
        recent = self.recent(n)
        return [
            {
                "reasoning": r.reasoning,
                "diff_summary": r.diff_summary,
                "gate_failures": r.gate_failures,
                "error_summary": r.error_summary,
            }
            for r in recent
        ]

    def __len__(self) -> int:
        return len(self._records)

    # ----- internal -----

    def _load(self) -> None:
        """Load records from the JSON Lines file."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError:
            return
        for line in text.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                self._records.append(FailureRecord.from_dict(d))
            except (json.JSONDecodeError, TypeError):
                logger.warning("Skipping corrupted line in failure bank")
