"""The run ledger: one JSON-lines file per step run.

The step runner writes ``run_start`` and ``run_end``; the step-code
functions running inside the kernel append ``input``, ``skill_load``,
``skill_call``, ``skill_cli``, ``output`` and ``stub_target_missing``
events to the file named by ``OMICSCLAW_STEP_LEDGER``. Each line carries
``v``, ``event`` and ``at`` besides the event's own fields
(``LEDGER_EVENTS`` in :mod:`skills._sdk.notebook.contract`).
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skills._sdk.notebook.contract import ENVIRONMENT

VERSION = 1


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_run_id(now: datetime | None = None) -> str:
    """A sortable run id such as ``20261001T100203Z-3f2a``."""
    moment = (now or utc_now()).astimezone(timezone.utc)
    return f"{moment:%Y%m%dT%H%M%SZ}-{secrets.token_hex(2)}"


def _json_default(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return repr(value)


class Ledger:
    """Appends events to one run's ledger file."""

    def __init__(self, path: str | os.PathLike, *, clock: Callable[[], datetime] = utc_now) -> None:
        self.path = Path(path)
        self._clock = clock

    def append(self, event: str, **fields: Any) -> dict:
        record = {"v": VERSION, "event": event, "at": iso(self._clock()), **fields}
        line = json.dumps(record, default=_json_default, ensure_ascii=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return record


def read_events(path: str | os.PathLike) -> list[dict]:
    """The events of one ledger file; a line that is not complete JSON is skipped."""
    events: list[dict] = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return events
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and "event" in record:
            events.append(record)
    return events


@dataclass
class RunRecord:
    """What one ledger file says about one run of a step."""

    run_id: str
    path: Path
    start: dict = field(default_factory=dict)
    end: dict | None = None
    inputs: list[dict] = field(default_factory=list)
    outputs: list[dict] = field(default_factory=list)
    skill_loads: list[dict] = field(default_factory=list)
    skill_calls: list[dict] = field(default_factory=list)
    skill_clis: list[dict] = field(default_factory=list)
    stub_missing: list[dict] = field(default_factory=list)
    r_sessions: list[dict] = field(default_factory=list)

    @property
    def status(self) -> str:
        """``ok``, ``failed``, or ``unfinished`` when the run never wrote ``run_end``."""
        if self.end is None:
            return "unfinished"
        return str(self.end.get("status", "failed"))

    @property
    def step_sha256(self) -> str | None:
        return self.start.get("step_sha256")

    @property
    def mode(self) -> str:
        return str(self.start.get("mode", "run"))


def read_run(path: str | os.PathLike) -> RunRecord:
    """Group a ledger file's events into a :class:`RunRecord`."""
    path = Path(path)
    record = RunRecord(run_id=path.stem, path=path)
    buckets = {
        "input": record.inputs,
        "output": record.outputs,
        "skill_load": record.skill_loads,
        "skill_call": record.skill_calls,
        "skill_cli": record.skill_clis,
        "stub_target_missing": record.stub_missing,
        "r_session": record.r_sessions,
    }
    for event in read_events(path):
        kind = event.get("event")
        if kind == "run_start":
            record.start = event
        elif kind == "run_end":
            record.end = event
        elif kind in buckets:
            buckets[kind].append(event)
    return record


def runs_of(runs_dir: Path, step_stem: str) -> list[RunRecord]:
    """Every recorded run of one step, oldest first."""
    folder = runs_dir / step_stem
    if not folder.is_dir():
        return []
    records = [read_run(p) for p in folder.glob("*.jsonl")]

    def order(record: RunRecord) -> tuple[str, int, str]:
        try:
            modified = record.path.stat().st_mtime_ns
        except OSError:
            modified = 0
        return (str(record.start.get("at", "")), modified, record.run_id)

    return sorted(records, key=order)


_SCALARS = (str, int, float, bool, type(None))


def summarize_value(value: Any) -> Any:
    """A scalar as it is; anything else as its type name, with its shape when it has one."""
    if isinstance(value, _SCALARS):
        if isinstance(value, str) and len(value) > 200:
            return value[:200] + "..."
        return value
    if isinstance(value, (list, tuple)) and len(value) <= 20 and all(isinstance(v, _SCALARS) for v in value):
        return [summarize_value(v) for v in value]
    name = type(value).__name__
    shape = getattr(value, "shape", None)
    if shape is not None:
        try:
            return f"{name}{tuple(int(n) for n in shape)}"
        except (TypeError, ValueError):
            return name
    return name


def summarize_args(arguments: Mapping[str, Any]) -> dict[str, Any]:
    return {key: summarize_value(value) for key, value in arguments.items()}


_NOTICE_SHOWN = False


def current(*, notice: bool = True) -> Ledger | None:
    """The ledger of the step run in progress, or ``None`` outside the step runner.

    Outside the runner, the first call with *notice* prints a one-line note to stderr.
    """
    global _NOTICE_SHOWN
    path = os.environ.get(ENVIRONMENT["step_ledger"], "").strip()
    if path:
        return Ledger(path)
    if notice and not _NOTICE_SHOWN:
        _NOTICE_SHOWN = True
        print(
            "note: not running under the step runner; reads, writes and skill calls are not recorded",
            file=sys.stderr,
        )
    return None
