"""What the step runner's ledgers say a run did with skills.

The step runner in ``skills/_sdk/notebook/`` writes one JSON-lines ledger per
step run under ``results/<NN_slug>/provenance/runs/<step>/``. An eval reads
those files after the run; it never imports ``skills.*``. The event, field and
environment names below are literals pinned equal to the runner's
``contract.py`` by ``tests/sdk/notebook/test_contract.py``.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from omicsclaw.skills import SkillIndex

from .case import SkillRun

__all__ = [
    "LEDGER_GLOB",
    "SKILL_STUBS_ENV",
    "LedgerSummary",
    "read_ledgers",
]

SKILL_STUBS_ENV = "OMICSCLAW_SKILL_STUBS"
"""The variable naming the folder of stub modules and stub results a step run uses."""

LEDGER_GLOB = "results/*/provenance/runs/*/*.jsonl"
"""Every ledger under a workspace."""

EVENT_FIELDS: dict[str, tuple[str, ...]] = {
    "skill_load": ("skill", "stub"),
    "skill_call": ("skill", "function", "args", "stub"),
    "skill_cli": ("skill", "script", "argv", "exit_code", "stub"),
    "stub_target_missing": ("skill", "names", "reason"),
}
"""The ledger events an eval reads, and the fields it reads from each."""


@dataclass(frozen=True)
class LedgerSummary:
    """Skill activity found in a workspace's ledgers.

    :param runs: One :class:`~omicsclaw.evals.case.SkillRun` per
        ``skill_call`` and ``skill_cli`` event, in ledger order.
    :param missing: One line per ``stub_target_missing`` event.
    :param unstubbed: Skills loaded without a stub (``skill_load`` with
        ``stub`` false).
    :param first_skill: The skill of the first ``skill_load`` or
        ``skill_cli`` event, or ``None``.
    """

    runs: tuple[SkillRun, ...]
    missing: tuple[str, ...]
    unstubbed: tuple[str, ...]
    first_skill: str | None


def _events(paths: Iterable[Path]) -> list[dict[str, Any]]:
    events: list[tuple[str, int, dict[str, Any]]] = []
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines):
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict) and record.get("event") in EVENT_FIELDS:
                events.append((str(record.get("at", "")), number, record))
    events.sort(key=lambda item: (item[0], item[1]))
    return [record for _at, _n, record in events]


def _domain(index: SkillIndex | None, skill: str) -> str:
    entry = index.get(skill) if index is not None else None
    return entry.domain if entry is not None else ""


def read_ledgers(workspace: Path, index: SkillIndex | None = None) -> LedgerSummary:
    """Read every ledger under *workspace*.

    :param index: Gives each skill's domain; without it the domain is empty.
    """
    events = _events(sorted(Path(workspace).glob(LEDGER_GLOB)))
    runs: list[SkillRun] = []
    missing: list[str] = []
    unstubbed: list[str] = []
    first: str | None = None
    for event in events:
        kind = event["event"]
        skill = str(event.get("skill", ""))
        if kind in {"skill_load", "skill_cli"} and first is None:
            first = skill
        if kind == "skill_load" and not event.get("stub"):
            unstubbed.append(skill)
        elif kind == "skill_call":
            args = event.get("args") or {}
            runs.append(SkillRun(
                skill=skill,
                domain=_domain(index, skill),
                command=f"{skill}.{event.get('function')}({json.dumps(args, sort_keys=True)})",
                stubbed=bool(event.get("stub")),
                function=str(event.get("function")),
                source="ledger",
                args=args if isinstance(args, dict) else {},
            ))
        elif kind == "skill_cli":
            argv = [str(a) for a in event.get("argv") or ()]
            runs.append(SkillRun(
                skill=skill,
                domain=_domain(index, skill),
                command=shlex.join([str(event.get("script", "")), *argv]),
                stubbed=bool(event.get("stub")),
                source="ledger",
            ))
        elif kind == "stub_target_missing":
            names = ", ".join(str(n) for n in event.get("names") or ())
            missing.append(f"{skill}: {event.get('reason')}" + (f" ({names})" if names else ""))
    return LedgerSummary(tuple(runs), tuple(missing), tuple(dict.fromkeys(unstubbed)), first)
