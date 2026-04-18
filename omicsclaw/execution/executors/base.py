"""Executor Protocol + data contracts.

A job lifecycle is: router creates a ``JobContext`` describing the work
→ executor ``run``s it asynchronously → returns a ``JobOutcome`` that
the router maps to queued/running/succeeded/failed. The executor owns
process management and log capture; the router owns persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class JobContext:
    """Everything an executor needs to run a job.

    ``stdout_log`` and ``artifact_root`` are pre-resolved absolute paths
    chosen by the router; the executor must not invent alternative
    locations (otherwise the artifacts router can't discover them).
    """

    job_id: str
    workspace: Path
    skill: str
    inputs: dict[str, Any]
    params: dict[str, Any]
    artifact_root: Path
    stdout_log: Path


@dataclass(frozen=True)
class JobOutcome:
    """Terminal state reported by an executor.

    ``stdout_text`` carries a tail / summary that the router will persist
    verbatim into ``stdout.log`` for the diagnostics artifact bundle.
    """

    exit_code: int
    error: Optional[str] = None
    stdout_text: str = ""


@runtime_checkable
class Executor(Protocol):
    async def run(self, ctx: JobContext) -> JobOutcome: ...
