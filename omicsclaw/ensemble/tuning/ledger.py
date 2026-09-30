"""What a tuning run leaves behind: the event ledger, model-call records, ``selection.json``.

::

    <run>/tuning/
      ledger.jsonl      one event per line: seq, at (UTC), kind, fields
      llm/0001.json     every model call in full: prompt, reply, usage, validation
      stability.json    reference.json    markers.json
      selection.json    the answer, read by consensus (:func:`load_selection`)
      tuning.json       the run summary and its ``tuning_record``

Events are appended under a lock and flushed at once, so the ledger of an
interrupted run is complete up to its last event.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from omicsclaw.ensemble.store import write_json

__all__ = [
    "LEDGER_KINDS",
    "Ledger",
    "SELECTION_SCHEMA",
    "SELECTION_STATUSES",
    "Selection",
    "SelectionError",
    "TUNING_RECORD_SCHEMA",
    "load_selection",
    "utc_now",
]

SELECTION_SCHEMA = "omicsclaw.ensemble.selection/1"
TUNING_RECORD_SCHEMA = "omicsclaw.ensemble.tuning_record/1"
SELECTION_STATUSES = ("ok", "partial", "failed")
SELECTION_ARMS = ("det", "free", "random", "user")
K_SOURCES = ("llm", "fallback", "user", "agent")
METHOD_STATUSES = ("ok", "fallback_default", "failed")
LEDGER_KINDS = (
    "start",
    "probe_trial",
    "trial",
    "stability",
    "llm_call",
    "k_decision",
    "stage",
    "select",
    "leak_refused",
    "end",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Ledger:
    """An append-only ``ledger.jsonl`` and the ``llm/`` directory beside it."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "ledger.jsonl"
        self.llm_dir = self.directory / "llm"
        self._lock = threading.Lock()
        self._seq = self._last_seq()
        self._llm_seq = self._last_llm()

    def _last_seq(self) -> int:
        if not self.path.is_file():
            return 0
        last = 0
        with open(self.path, encoding="utf-8") as source:
            for line in source:
                try:
                    last = max(last, int(json.loads(line).get("seq", 0)))
                except (ValueError, AttributeError):
                    continue
        return last

    def _last_llm(self) -> int:
        if not self.llm_dir.is_dir():
            return 0
        numbers = [int(p.stem) for p in self.llm_dir.glob("*.json") if p.stem.isdigit()]
        return max(numbers, default=0)

    def append(self, kind: str, **fields: Any) -> dict[str, Any]:
        """Append one event; returns it with its ``seq`` and ``at``.

        :raises ValueError: *kind* is not one of :data:`LEDGER_KINDS`.
        """
        if kind not in LEDGER_KINDS:
            raise ValueError(f"unknown ledger event kind {kind!r}")
        with self._lock:
            self._seq += 1
            event = {"seq": self._seq, "at": utc_now(), "kind": kind, **fields}
            line = json.dumps(event, sort_keys=True, default=str, ensure_ascii=False)
            with open(self.path, "a", encoding="utf-8") as sink:
                sink.write(line + "\n")
                sink.flush()
                os.fsync(sink.fileno())
            return event

    def record_llm(self, document: Mapping[str, Any]) -> str:
        """Write one model call to ``llm/NNNN.json``; returns the path relative to the ledger directory."""
        with self._lock:
            self._llm_seq += 1
            number = self._llm_seq
        self.llm_dir.mkdir(parents=True, exist_ok=True)
        name = f"{number:04d}.json"
        write_json(self.llm_dir / name, dict(document))
        return f"llm/{name}"

    def events(self, kind: str | None = None) -> list[dict[str, Any]]:
        """Every event in order, or those of one *kind*."""
        if not self.path.is_file():
            return []
        out = []
        with open(self.path, encoding="utf-8") as source:
            for line in source:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                if kind is None or event.get("kind") == kind:
                    out.append(event)
        return out


class SelectionError(ValueError):
    """A ``selection.json`` that does not satisfy its schema."""


@dataclass
class Selection:
    """The answer of one tuning run: K, each method's trial and the single final trial.

    Serialised as ``selection.json`` (schema :data:`SELECTION_SCHEMA`).
    ``methods.*.labels`` is the path of the chosen trial's ``labels.csv.gz``
    (``obs_id,label``) and ``methods.*.h5ad`` its kept ``.h5ad`` or ``None``;
    the pipeline and ``select_result`` write both as absolute paths. The trial
    may belong to another run on the same input (a probe's default trial), which
    ``run_id`` names. ``k.stability``, ``k.decision`` and ``reference`` are file
    names relative to the ``selection.json`` directory. :func:`load_selection`
    resolves any relative label path against that directory.
    """

    status: str
    arm: str
    skill: str
    input: str
    input_sha256: str
    panel_version: str
    k: dict[str, Any]
    methods: dict[str, dict[str, Any]]
    final: dict[str, Any] | None
    reference: str = "reference.json"
    budget: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    written_at: str = ""
    path: Path | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": SELECTION_SCHEMA,
            "status": self.status,
            "arm": self.arm,
            "skill": self.skill,
            "input": self.input,
            "input_sha256": self.input_sha256,
            "panel_version": self.panel_version,
            "k": self.k,
            "reference": self.reference,
            "methods": self.methods,
            "final": self.final,
            "budget": self.budget,
            "provenance": self.provenance,
            "written_at": self.written_at or utc_now(),
        }

    def write(self, path: Path) -> Path:
        """Validate and write to *path*; returns *path*.

        :raises SelectionError: The selection breaks the schema.
        """
        document = self.to_json()
        _check(document)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, document)
        self.path = path
        return path

    def member_labels(self, method: str) -> Path | None:
        """Absolute path of *method*'s label table, or ``None``."""
        entry = self.methods.get(method) or {}
        raw = entry.get("labels")
        if not raw:
            return None
        candidate = Path(raw)
        if not candidate.is_absolute() and self.path is not None:
            candidate = self.path.parent / candidate
        return candidate


def _check(document: Mapping[str, Any]) -> None:
    if document.get("schema") != SELECTION_SCHEMA:
        raise SelectionError(f"schema must be {SELECTION_SCHEMA!r}, got {document.get('schema')!r}")
    for key in ("status", "arm", "skill", "input", "input_sha256", "panel_version", "k", "methods"):
        if key not in document:
            raise SelectionError(f"selection is missing {key!r}")
    if document["status"] not in SELECTION_STATUSES:
        raise SelectionError(f"status must be one of {SELECTION_STATUSES}, got {document['status']!r}")
    if document["arm"] not in SELECTION_ARMS:
        raise SelectionError(f"arm must be one of {SELECTION_ARMS}, got {document['arm']!r}")
    k = document["k"]
    if not isinstance(k, Mapping) or "chosen" not in k or "source" not in k:
        raise SelectionError("k must have 'chosen' and 'source'")
    if k["source"] not in K_SOURCES:
        raise SelectionError(f"k.source must be one of {K_SOURCES}, got {k['source']!r}")
    methods = document["methods"]
    if not isinstance(methods, Mapping):
        raise SelectionError("methods must be an object")
    for name, entry in methods.items():
        if not isinstance(entry, Mapping) or entry.get("status") not in METHOD_STATUSES:
            raise SelectionError(f"methods.{name}.status must be one of {METHOD_STATUSES}")
        if entry["status"] != "failed":
            for key in ("run_id", "trial", "params", "n_labels", "labels"):
                if key not in entry:
                    raise SelectionError(f"methods.{name} is missing {key!r}")
    final = document.get("final")
    if final is not None:
        if not isinstance(final, Mapping) or {"method", "run_id", "trial"} - set(final):
            raise SelectionError("final must have method, run_id and trial")
        if final["method"] not in methods:
            raise SelectionError(f"final names {final['method']!r}, which is not among the methods")
    if document["status"] == "ok" and final is None:
        raise SelectionError("an ok selection must have a final trial")


def load_selection(path: str | Path) -> Selection:
    """Read and check a ``selection.json``.

    :raises SelectionError: The file is unreadable, breaks the schema, or names
        a label table that does not exist.
    """
    file = Path(path)
    try:
        document = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SelectionError(f"{file}: cannot be read: {exc}") from exc
    _check(document)
    selection = Selection(
        status=document["status"],
        arm=document["arm"],
        skill=document["skill"],
        input=document["input"],
        input_sha256=document["input_sha256"],
        panel_version=document["panel_version"],
        k=dict(document["k"]),
        methods={name: dict(entry) for name, entry in document["methods"].items()},
        final=dict(document["final"]) if document.get("final") else None,
        reference=document.get("reference", "reference.json"),
        budget=dict(document.get("budget") or {}),
        provenance=dict(document.get("provenance") or {}),
        written_at=document.get("written_at", ""),
        path=file,
    )
    for name, entry in selection.methods.items():
        if entry.get("status") == "failed":
            continue
        labels = selection.member_labels(name)
        if labels is None or not labels.is_file():
            raise SelectionError(f"{file}: methods.{name}.labels ({entry.get('labels')}) does not exist")
    return selection
