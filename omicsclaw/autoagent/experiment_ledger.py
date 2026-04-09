"""Experiment ledger for autoagent optimization trials.

Mirrors AutoAgent's ``results.tsv`` — each optimization run produces a
JSON Lines (``.jsonl``) file where every line is one :class:`TrialRecord`.
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
class TrialRecord:
    """A single trial (one skill execution with specific parameters)."""

    trial_id: int
    params: dict[str, Any]
    composite_score: float
    raw_metrics: dict[str, float] = field(default_factory=dict)
    status: str = "pending"  # "baseline" | "keep" | "discard" | "crash"
    reasoning: str = ""
    output_dir: str = ""
    duration_seconds: float = 0.0
    timestamp: str = ""
    error_output: str = ""  # stderr/stdout excerpt on crash (for diagnostics)
    evaluation_success: bool | None = None
    missing_metrics: list[str] = field(default_factory=list)
    code_state: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TrialRecord:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class ExperimentLedger:
    """Append-only JSON Lines ledger of optimization trials.

    Designed after AutoAgent's ``results.tsv`` — every trial is logged
    regardless of whether it was kept or discarded, because even discarded
    runs provide learning signal for the meta-agent.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._records: list[TrialRecord] = []
        self._lock = threading.Lock()
        if self.path.exists():
            self._load()

    # ----- core API -----

    def append(self, record: TrialRecord) -> None:
        """Append a trial record to the ledger (in memory + on disk)."""
        with self._lock:
            self._records.append(record)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), default=str) + "\n")

    def all_trials(self) -> list[TrialRecord]:
        """Return all trial records (newest last)."""
        with self._lock:
            return list(self._records)

    def best_trial(self) -> TrialRecord | None:
        """Return the trial with the highest composite score (kept only)."""
        with self._lock:
            kept = [r for r in self._records if r.status in ("baseline", "keep")]
        if not kept:
            return None
        return max(kept, key=lambda r: r.composite_score)

    def kept_trials(self) -> list[TrialRecord]:
        """Return only trials with status ``keep`` or ``baseline``."""
        with self._lock:
            return [r for r in self._records if r.status in ("baseline", "keep")]

    def latest(self) -> TrialRecord | None:
        """Return the most recently appended trial."""
        return self._records[-1] if self._records else None

    def __len__(self) -> int:
        return len(self._records)

    # ----- formatting -----

    def format_table(self) -> str:
        """Format the ledger as a human-readable text table."""
        if not self._records:
            return "(no trials recorded)"

        # Collect all param keys + metric keys seen across trials
        all_param_keys: list[str] = []
        all_metric_keys: list[str] = []
        for r in self._records:
            for k in r.params:
                if k not in all_param_keys:
                    all_param_keys.append(k)
            for k in r.raw_metrics:
                if k not in all_metric_keys:
                    all_metric_keys.append(k)

        # Build rows
        headers = ["#", *all_param_keys, "score", *all_metric_keys, "status"]
        rows: list[list[str]] = []
        for r in self._records:
            row = [str(r.trial_id)]
            for pk in all_param_keys:
                row.append(_fmt_val(r.params.get(pk, "")))
            row.append(_fmt_val(r.composite_score))
            for mk in all_metric_keys:
                row.append(_fmt_val(r.raw_metrics.get(mk, "")))
            row.append(r.status)
            rows.append(row)

        # Compute column widths
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(cell))

        def _fmt_row(cells: list[str]) -> str:
            parts = [c.ljust(w) for c, w in zip(cells, col_widths)]
            return " | ".join(parts)

        lines = [_fmt_row(headers)]
        lines.append("-+-".join("-" * w for w in col_widths))
        for row in rows:
            lines.append(_fmt_row(row))
        return "\n".join(lines)

    def to_history_text(self) -> str:
        """Produce a text summary suitable for inclusion in an LLM directive."""
        if not self._records:
            return "No trials have been run yet."

        lines = [f"Experiment history ({len(self._records)} trials):"]
        lines.append("")
        for r in self._records:
            status_marker = {"keep": "+", "discard": "-", "baseline": "=", "crash": "!"}.get(
                r.status, "?"
            )
            params_str = ", ".join(f"{k}={v}" for k, v in r.params.items())
            metrics_str = ", ".join(f"{k}={v:.4f}" for k, v in r.raw_metrics.items())
            lines.append(
                f"  [{status_marker}] Trial #{r.trial_id}: "
                f"score={r.composite_score:.4f}  params=[{params_str}]  "
                f"metrics=[{metrics_str}]  ({r.duration_seconds:.1f}s)"
            )
            if r.evaluation_success is False:
                lines.append("       Evaluation failed: no declared metrics were readable.")
            if r.missing_metrics:
                lines.append(
                    "       Missing metrics: " + ", ".join(r.missing_metrics)
                )
            if r.reasoning:
                lines.append(f"       Reasoning: {r.reasoning}")
            if r.code_state:
                commit_hash = str(
                    r.code_state.get("commit_hash")
                    or r.code_state.get("sandbox_commit")
                    or ""
                ).strip()
                artifact_path = str(r.code_state.get("artifact_path") or "").strip()
                details: list[str] = []
                if commit_hash:
                    details.append(f"commit={commit_hash}")
                if artifact_path:
                    details.append(f"artifact={artifact_path}")
                if details:
                    lines.append("       Code: " + ", ".join(details))
        return "\n".join(lines)

    # ----- internal -----

    def _load(self) -> None:
        """Load existing records from the JSON Lines file."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError:
            return
        skipped = 0
        for lineno, line in enumerate(text.strip().splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                self._records.append(TrialRecord.from_dict(d))
            except (json.JSONDecodeError, TypeError):
                skipped += 1
                logger.warning(
                    "Skipping corrupted line %d in ledger %s", lineno, self.path,
                )
        if skipped:
            logger.warning(
                "Loaded %d trial(s) from %s, skipped %d corrupted line(s)",
                len(self._records), self.path, skipped,
            )


def _fmt_val(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)
