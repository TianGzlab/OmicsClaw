"""Evaluator — computes quality metrics and a composite score per trial.

Two evaluation paths, tried in order:

1. **adata path** (primary): Load ``processed.h5ad`` from the output
   directory and compute metrics directly from the adata object via
   :mod:`metrics_compute`.  This works for all spatial and single-cell
   skills and requires *no* modifications to skill scripts.

2. **result.json path** (fallback): Read pre-computed metrics from the
   skill's ``result.json:summary``.  Used for bulk-RNA skills that do
   not produce adata files, or when the adata path fails.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omicsclaw.autoagent.errors import MetricConfigError
from omicsclaw.autoagent.metrics_registry import MetricDef
from omicsclaw.autoagent.result_contract import normalize_result_payload

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """Result of evaluating a single trial."""

    composite_score: float
    raw_metrics: dict[str, float] = field(default_factory=dict)
    success: bool = True
    missing_metrics: list[str] = field(default_factory=list)


class Evaluator:
    """Score a trial's output by computing or reading quality metrics."""

    def __init__(
        self,
        metrics: dict[str, MetricDef],
        *,
        skill_name: str = "",
        method: str = "",
    ) -> None:
        self.metrics = metrics
        self.skill_name = skill_name
        self.method = method

    def evaluate(
        self,
        output_dir: Path,
        params: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        """Evaluate a trial output directory.

        Tries the adata path first, falls back to result.json.
        """
        output_dir = Path(output_dir)
        params = params or {}

        # --- Path 1: compute from adata (primary) ---
        adata_path = output_dir / "processed.h5ad"
        if adata_path.exists() and self.skill_name:
            adata_metrics = self._evaluate_from_adata(adata_path, params)
            if adata_metrics is not None:
                return adata_metrics

        # --- Path 2: read from result.json (fallback) ---
        return self._evaluate_from_result_json(output_dir)

    # ----- adata path -----

    def _evaluate_from_adata(
        self,
        adata_path: Path,
        params: dict[str, Any],
    ) -> EvaluationResult | None:
        """Compute metrics from the processed adata file.

        The raw metrics dict from ``metrics_compute`` may contain extra
        fields not declared in ``self.metrics``.  We filter to only the
        registered metric names and score using the same direction/weight
        logic as the result.json path — ensuring the optimization target
        matches what the directive tells the LLM.
        """
        try:
            from omicsclaw.autoagent.metrics_compute import compute_metrics_from_adata

            computed = compute_metrics_from_adata(
                adata_path,
                skill_name=self.skill_name,
                method=self.method,
                params=params,
            )
        except Exception as exc:
            logger.warning("adata metrics computation failed: %s", exc)
            return None

        if not computed:
            return None

        # Keep only metrics that are declared in self.metrics (the registry).
        # This prevents undeclared fields (e.g. n_batches, n_clusters) from
        # leaking into the composite score.
        raw: dict[str, float] = {}
        missing: list[str] = []
        for name in self.metrics:
            if name in computed:
                raw[name] = computed[name]
            else:
                missing.append(name)

        if not raw:
            if computed:
                # adata produced metrics but none match the registry — config error
                raise MetricConfigError(
                    f"adata metrics were computed ({list(computed.keys())}) but "
                    f"none match the declared metrics ({list(self.metrics.keys())}). "
                    f"Check metrics_registry for this skill."
                )
            # adata computation itself produced nothing — fall back to result.json
            return None

        # Use the SAME direction/weight scoring as the result.json path.
        score = self._compute_composite_from_metricdefs(raw)
        return EvaluationResult(
            composite_score=score,
            raw_metrics=raw,
            success=True,
            missing_metrics=missing,
        )

    # ----- result.json path -----

    def _evaluate_from_result_json(self, output_dir: Path) -> EvaluationResult:
        """Read metrics from result.json using the declared MetricDef sources."""
        raw: dict[str, float] = {}
        missing: list[str] = []

        for name, mdef in self.metrics.items():
            value = _read_metric(output_dir, mdef.source, mdef.column)
            if value is not None:
                raw[name] = value
            else:
                missing.append(name)

        if not raw:
            # Distinguish "no result.json" from "result.json exists but
            # fields don't match" — the latter is a config error.
            result_path = output_dir / "result.json"
            if result_path.exists():
                raise MetricConfigError(
                    f"result.json exists but none of the declared metrics "
                    f"({list(self.metrics.keys())}) were found. "
                    f"Missing: {missing}. Check that metric source paths in "
                    f"metrics_registry match the skill's result.json structure."
                )
            return EvaluationResult(
                composite_score=float("-inf"),
                raw_metrics=raw,
                success=False,
                missing_metrics=missing,
            )

        score = self._compute_composite_from_metricdefs(raw)
        return EvaluationResult(
            composite_score=score,
            raw_metrics=raw,
            success=True,
            missing_metrics=missing,
        )

    def _compute_composite_from_metricdefs(self, raw: dict[str, float]) -> float:
        """Weighted sum of range-normalized metrics.

        Each raw metric is scaled to [0, 1] using its ``range_min``/``range_max``,
        then ``direction="minimize"`` metrics are flipped (1 - normalized) so that
        higher always means better.  This ensures that the ``weight`` field
        reflects true importance regardless of each metric's native scale.
        """
        total_weight = 0.0
        weighted_sum = 0.0

        for name, mdef in self.metrics.items():
            if name not in raw:
                continue
            value = raw[name]
            # Normalize to [0, 1] using declared range
            span = mdef.range_max - mdef.range_min
            if span > 0:
                normalized = (value - mdef.range_min) / span
                normalized = max(0.0, min(1.0, normalized))
            else:
                normalized = 0.5
            # Flip minimize metrics so higher = better
            if mdef.direction == "minimize":
                normalized = 1.0 - normalized
            weighted_sum += normalized * mdef.weight
            total_weight += mdef.weight

        if total_weight == 0.0:
            return 0.0
        return weighted_sum / total_weight

    def describe_metrics(self) -> str:
        """Human-readable summary for LLM directives."""
        lines = ["Evaluation metrics:"]
        for name, mdef in self.metrics.items():
            lines.append(
                f"  - {name}: {mdef.direction} (weight={mdef.weight})"
                f"  {mdef.description}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# result.json / CSV readers (for fallback path)
# ---------------------------------------------------------------------------


def _read_metric(
    output_dir: Path,
    source: str,
    column: str | None = None,
) -> float | None:
    if source.startswith("result.json:"):
        return _read_from_result_json(output_dir, source)
    return _read_from_csv(output_dir, source, column)


def _read_from_result_json(output_dir: Path, source: str) -> float | None:
    result_path = output_dir / "result.json"
    if not result_path.exists():
        return None
    try:
        data = normalize_result_payload(
            json.loads(result_path.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError):
        return None
    dot_path = source.split(":", 1)[1]
    return _resolve_dot_path(data, dot_path)


def _read_from_csv(
    output_dir: Path, source: str, column: str | None
) -> float | None:
    csv_path = output_dir / source
    if not csv_path.exists() or column is None:
        return None
    try:
        text = csv_path.read_text(encoding="utf-8")
    except OSError:
        return None
    delimiter = "\t" if csv_path.suffix == ".tsv" else ","
    reader = csv.DictReader(text.strip().splitlines(), delimiter=delimiter)
    for row in reader:
        val_str = row.get(column)
        if val_str is not None:
            try:
                return float(val_str)
            except (ValueError, TypeError):
                return None
    return None


def _resolve_dot_path(data: Any, path: str) -> float | None:
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    try:
        return float(current)
    except (ValueError, TypeError):
        return None
