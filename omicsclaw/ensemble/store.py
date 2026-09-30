"""The ``<workspace>/ensemble_runs/`` layout, and what a finished trial keeps.

::

    ensemble_runs/
      _cache/<input_sha256>/        coordinate-only panel intermediates
      <run_id>/
        run.json    trials.jsonl
        <method>/
          best.json                 {"trial": ..., "score": ...}
          t0001/
            trial.json  labels.csv.gz  metrics.json  supervisor.json  run.log
            tmp/                    the trial's temporary directory; removed at the end
            output/                 the skill's output; only result.json survives,
                                    plus the processed h5ad of the best trial

Every write here happens in this process under an asyncio lock per run or per
``(run, method)``; the store is not safe across processes.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from omicsclaw.ensemble.space import SpecError

__all__ = [
    "CACHE_DIRNAME",
    "LOG_LIMIT_BYTES",
    "RUN_ID_PATTERN",
    "RunStore",
    "new_run_id",
    "read_json",
    "write_json",
]

RUN_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
"""A run id, matched with :meth:`re.Pattern.fullmatch` so no trailing newline slips through."""
CACHE_DIRNAME = "_cache"
LOG_LIMIT_BYTES = 256 * 1024
_TRIAL = re.compile(r"^t(\d{4,})$")


def new_run_id(now: datetime | None = None) -> str:
    """``rYYYYMMDD-HHMMSS-xxxx``."""
    moment = now or datetime.now()
    return f"r{moment:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def write_json(path: Path, document: Mapping[str, Any]) -> None:
    """Write *document* to *path* atomically."""
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as sink:
            json.dump(document, sink, indent=1, sort_keys=True, default=str)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def read_json(path: Path) -> dict[str, Any] | None:
    """The JSON object in *path*, or ``None`` when it is missing or unreadable."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class RunStore:
    """Directories, bindings, numbering and retention under one ``ensemble_runs`` root."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._locks: dict[tuple[str, ...], asyncio.Lock] = {}

    def lock(self, *key: str) -> asyncio.Lock:
        """The lock for a run (``lock(run_id)``) or a method in it (``lock(run_id, method)``)."""
        return self._locks.setdefault(key, asyncio.Lock())

    def run_dir(self, run_id: str) -> Path:
        return self.root / run_id

    def method_dir(self, run_id: str, method: str) -> Path:
        return self.root / run_id / method

    def cache_dir(self, input_sha256: str) -> Path:
        return self.root / CACHE_DIRNAME / input_sha256

    def existing_run(self, run_id: str) -> dict[str, Any] | None:
        """``run.json`` of *run_id*, if the run exists."""
        return read_json(self.run_dir(run_id) / "run.json")

    def check_run(self, run_id: str, *, skill: str, input_sha256: str) -> None:
        """Refuse reusing *run_id* for another skill or another input.

        :raises SpecError: The run exists and names a different skill or input.
        """
        existing = self.existing_run(run_id)
        if existing is None:
            return
        if existing.get("skill") != skill:
            raise SpecError(
                f"run_id {run_id!r} belongs to skill {existing.get('skill')!r}, not {skill!r}; "
                "use a new run_id"
            )
        if existing.get("input_sha256") != input_sha256:
            raise SpecError(
                f"run_id {run_id!r} was started on another input ({existing.get('input')}); "
                "use a new run_id"
            )

    async def bind_run(self, run_id: str, record: Mapping[str, Any]) -> None:
        """Write ``run.json`` the first time *run_id* is used; check it every other time.

        :raises SpecError: The run exists for another skill or input.
        """
        async with self.lock(run_id):
            self.check_run(run_id, skill=record["skill"], input_sha256=record["input_sha256"])
            path = self.run_dir(run_id) / "run.json"
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                write_json(path, record)

    async def allocate_trial(self, run_id: str, method: str) -> Path:
        """Create and return the next ``tNNNN`` directory of ``(run_id, method)``."""
        async with self.lock(run_id, method):
            directory = self.method_dir(run_id, method)
            directory.mkdir(parents=True, exist_ok=True)
            numbers = [
                int(match.group(1))
                for entry in directory.iterdir()
                if (match := _TRIAL.match(entry.name))
            ]
            trial = directory / f"t{max(numbers, default=0) + 1:04d}"
            trial.mkdir(exist_ok=False)
            (trial / "tmp").mkdir()
            (trial / "output").mkdir()
            return trial

    async def record_trial(self, run_id: str, trial_dir: Path, record: Mapping[str, Any]) -> None:
        """Write ``trial.json`` and append the record to the run's ``trials.jsonl``."""
        write_json(trial_dir / "trial.json", record)
        async with self.lock(run_id):
            line = json.dumps(record, sort_keys=True, default=str)
            with open(self.run_dir(run_id) / "trials.jsonl", "a", encoding="utf-8") as sink:
                sink.write(line + "\n")

    async def retain(
        self,
        run_id: str,
        method: str,
        trial_dir: Path,
        *,
        score: float | None,
        h5ad: str | None,
        keep_all: bool,
    ) -> Path | None:
        """Apply the retention policy to one finished trial.

        Everything under ``output/`` except ``result.json`` is deleted, and
        ``tmp/`` is removed, unless *keep_all*. The processed h5ad is kept
        only for the best-scoring trial of ``(run_id, method)``: a trial that
        beats the current best takes its place and the previous best's h5ad
        is deleted; a tie keeps the earlier trial. A trial with no score keeps
        no h5ad.

        :returns: The kept h5ad of this trial, or ``None``.
        """
        output = trial_dir / "output"
        own_h5ad = output / h5ad if h5ad else None
        kept: Path | None = None
        async with self.lock(run_id, method):
            best_path = self.method_dir(run_id, method) / "best.json"
            best = read_json(best_path)
            better = score is not None and (best is None or best.get("score") is None or score > best["score"])
            if better:
                previous = best.get("trial") if best else None
                write_json(best_path, {"trial": trial_dir.name, "score": score})
                if previous and not keep_all and h5ad:
                    stale = self.method_dir(run_id, method) / previous / "output" / h5ad
                    _unlink(stale)
                if own_h5ad is not None and own_h5ad.exists():
                    kept = own_h5ad
            elif keep_all and own_h5ad is not None and own_h5ad.exists():
                kept = own_h5ad
            if not keep_all:
                for entry in list(output.iterdir()) if output.is_dir() else []:
                    if entry.name == "result.json" or (kept is not None and entry == kept):
                        continue
                    _remove(entry)
        if not keep_all:
            shutil.rmtree(trial_dir / "tmp", ignore_errors=True)
        return kept


def truncate_log(path: Path, limit: int = LOG_LIMIT_BYTES) -> None:
    """Keep the last *limit* bytes of *path*, marking the cut."""
    try:
        size = path.stat().st_size
    except OSError:
        return
    if size <= limit:
        return
    with open(path, "rb") as source:
        source.seek(size - limit)
        tail = source.read()
    marker = f"[... {size - limit} earlier bytes removed ...]\n".encode()
    with open(path, "wb") as sink:
        sink.write(marker + tail)


def log_tail(path: Path, limit: int = 2048) -> str:
    """The last *limit* bytes of *path* as text."""
    try:
        with open(path, "rb") as source:
            source.seek(0, os.SEEK_END)
            size = source.tell()
            source.seek(max(0, size - limit))
            return source.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        _unlink(path)
