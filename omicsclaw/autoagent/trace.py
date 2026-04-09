"""RunTrace — standardized execution trace for harness-level evolution.

Every trial produces a RunTrace capturing five signal categories:

1. **Execution trace**: stdout, stderr, traceback, warnings, timing.
2. **Data shape trace**: n_obs/n_vars before and after, layers,
   embeddings, cell retention rate.
3. **Method trace**: requested vs executed method, fallback info.
4. **Parameter trace**: user params, skill defaults, effective params.
5. **Quality trace**: metric values collected by the evaluator.

The Meta-Agent consumes the trace to diagnose root causes rather than
relying solely on a composite score.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omicsclaw.autoagent.result_contract import normalize_result_payload

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Trace data structures
# ---------------------------------------------------------------------------


@dataclass
class ExecutionTrace:
    """Execution-level signals from trial subprocess."""

    stdout: str = ""
    stderr: str = ""
    traceback: str | None = None
    warnings: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    exit_code: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DataShapeTrace:
    """Data shape before and after the skill execution."""

    n_obs_before: int = 0
    n_vars_before: int = 0
    n_obs_after: int = 0
    n_vars_after: int = 0
    n_obs_before_known: bool = False
    layers: list[str] = field(default_factory=list)
    obs_columns: list[str] = field(default_factory=list)
    var_columns: list[str] = field(default_factory=list)
    embedding_keys: list[str] = field(default_factory=list)
    n_batches: int | None = None
    n_clusters: int | None = None
    cell_retention_rate: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MethodTrace:
    """Method selection trace: requested vs executed, fallback info."""

    requested_method: str = ""
    executed_method: str = ""
    fallback_used: bool = False
    fallback_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParameterTrace:
    """Parameter provenance: user input -> defaults -> effective."""

    user_params: dict[str, Any] = field(default_factory=dict)
    skill_defaults: dict[str, Any] = field(default_factory=dict)
    effective_params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QualityTrace:
    """Quality metrics collected by the evaluator."""

    quality_metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunTrace:
    """Complete trace of a single trial execution.

    Designed to be the primary diagnostic input for the Meta-Agent.
    The trace is saved as ``run_trace.json`` in the trial output directory.
    """

    trial_id: int | str = 0
    skill_name: str = ""
    method: str = ""
    timestamp: str = ""

    execution: ExecutionTrace = field(default_factory=ExecutionTrace)
    data_shape: DataShapeTrace = field(default_factory=DataShapeTrace)
    method_trace: MethodTrace = field(default_factory=MethodTrace)
    parameters: ParameterTrace = field(default_factory=ParameterTrace)
    quality: QualityTrace = field(default_factory=QualityTrace)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "trial_id": self.trial_id,
            "skill_name": self.skill_name,
            "method": self.method,
            "timestamp": self.timestamp,
            "execution": self.execution.to_dict(),
            "data_shape": self.data_shape.to_dict(),
            "method_trace": self.method_trace.to_dict(),
            "parameters": self.parameters.to_dict(),
            "quality": self.quality.to_dict(),
        }

    def save(self, output_dir: Path) -> Path:
        """Write the trace to ``run_trace.json`` in *output_dir*."""
        path = Path(output_dir) / "run_trace.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, path: Path) -> RunTrace:
        """Load a RunTrace from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            trial_id=data.get("trial_id", 0),
            skill_name=data.get("skill_name", ""),
            method=data.get("method", ""),
            timestamp=data.get("timestamp", ""),
            execution=ExecutionTrace(**data.get("execution", {})),
            data_shape=DataShapeTrace(**data.get("data_shape", {})),
            method_trace=MethodTrace(**data.get("method_trace", {})),
            parameters=ParameterTrace(**data.get("parameters", {})),
            quality=QualityTrace(**data.get("quality", {})),
        )

    def to_diagnostic_summary(self, max_stderr_lines: int = 20) -> str:
        """Produce a concise text summary for the Meta-Agent directive.

        The summary focuses on actionable signals rather than raw dumps.
        """
        parts: list[str] = []

        # Header
        parts.append(
            f"Trial #{self.trial_id} | {self.skill_name}/{self.method} "
            f"| exit={self.execution.exit_code} "
            f"| {self.execution.duration_seconds:.1f}s"
        )

        # Data shape
        ds = self.data_shape
        if ds.n_obs_before > 0:
            parts.append(
                f"Data: {ds.n_obs_before} cells x {ds.n_vars_before} genes "
                f"-> {ds.n_obs_after} cells x {ds.n_vars_after} genes "
                f"(retention={ds.cell_retention_rate:.1%})"
            )
        if ds.embedding_keys:
            parts.append(f"Embeddings: {', '.join(ds.embedding_keys)}")
        if ds.n_clusters is not None:
            parts.append(f"Clusters: {ds.n_clusters}")
        if ds.n_batches is not None:
            parts.append(f"Batches: {ds.n_batches}")

        # Method trace
        mt = self.method_trace
        if mt.fallback_used:
            parts.append(
                f"FALLBACK: requested={mt.requested_method} "
                f"-> executed={mt.executed_method} "
                f"reason={mt.fallback_reason}"
            )

        # Parameter diff: what differs from defaults
        param_diffs = _param_diff(
            self.parameters.effective_params,
            self.parameters.skill_defaults,
        )
        if param_diffs:
            parts.append("Param diffs from defaults: " + ", ".join(param_diffs))

        # Quality metrics
        if self.quality.quality_metrics:
            metrics_str = ", ".join(
                f"{k}={v:.4f}" for k, v in self.quality.quality_metrics.items()
            )
            parts.append(f"Metrics: {metrics_str}")

        # Warnings
        if self.execution.warnings:
            parts.append(
                f"Warnings ({len(self.execution.warnings)}): "
                + "; ".join(self.execution.warnings[:5])
            )

        # Traceback (abbreviated)
        if self.execution.traceback:
            tb_lines = self.execution.traceback.strip().splitlines()
            tail = tb_lines[-min(5, len(tb_lines)):]
            parts.append("Traceback (tail):\n  " + "\n  ".join(tail))
        elif self.execution.exit_code != 0 and self.execution.stderr:
            stderr_lines = [
                l for l in self.execution.stderr.splitlines() if l.strip()
            ]
            tail = stderr_lines[-min(max_stderr_lines, len(stderr_lines)):]
            parts.append("Stderr (tail):\n  " + "\n  ".join(tail))

        return "\n".join(parts)


# ---------------------------------------------------------------------------
# TraceCollector — extracts RunTrace from trial artifacts
# ---------------------------------------------------------------------------


class TraceCollector:
    """Extract a :class:`RunTrace` from trial execution output.

    This reads data from:
    - The subprocess execution result (stdout, stderr, exit code)
    - ``processed.h5ad`` (data shape, embeddings, layers)
    - ``result.json`` (effective params, method info, summary stats)
    """

    @staticmethod
    def collect(
        trial_id: int | str,
        skill_name: str,
        method: str,
        execution: Any,  # TrialExecution from runner.py
        output_dir: Path,
        user_params: dict[str, Any] | None = None,
        skill_defaults: dict[str, Any] | None = None,
    ) -> RunTrace:
        """Build a complete RunTrace from trial artifacts."""
        output_dir = Path(output_dir)
        user_params = user_params or {}
        skill_defaults = skill_defaults or {}

        exec_trace = TraceCollector._extract_execution_trace(execution)
        data_trace = TraceCollector._extract_data_shape_trace(output_dir)
        method_t = TraceCollector._extract_method_trace(output_dir, method)
        param_trace = TraceCollector._extract_parameter_trace(
            output_dir, user_params, skill_defaults
        )
        quality_trace = TraceCollector._extract_quality_trace(output_dir)

        trace = RunTrace(
            trial_id=trial_id,
            skill_name=skill_name,
            method=method,
            execution=exec_trace,
            data_shape=data_trace,
            method_trace=method_t,
            parameters=param_trace,
            quality=quality_trace,
        )
        return trace

    # --- extraction helpers ---

    @staticmethod
    def _extract_execution_trace(execution: Any) -> ExecutionTrace:
        """Extract execution-level signals from TrialExecution."""
        stdout = getattr(execution, "stdout", "") or ""
        stderr = getattr(execution, "stderr", "") or ""

        # Extract Python traceback from stderr
        traceback_text = _extract_traceback(stderr)

        # Extract warnings from stderr
        warnings = _extract_warnings(stderr)

        return ExecutionTrace(
            stdout=stdout,
            stderr=stderr,
            traceback=traceback_text,
            warnings=warnings,
            duration_seconds=getattr(execution, "duration_seconds", 0.0),
            exit_code=getattr(execution, "exit_code", -1),
        )

    @staticmethod
    def _extract_data_shape_trace(output_dir: Path) -> DataShapeTrace:
        """Extract data shape from processed.h5ad or result.json."""
        trace = DataShapeTrace()

        # Try result.json first (cheaper than loading h5ad)
        result_data = _load_result_json(output_dir)
        if result_data:
            summary = result_data.get("summary", {})
            data = result_data.get("data", {})

            # Cell/gene counts from summary
            trace.n_obs_after = _int_or(summary, "n_cells", 0) or _int_or(
                summary, "n_obs", 0
            )
            trace.n_vars_after = _int_or(summary, "n_genes", 0) or _int_or(
                summary, "n_vars", 0
            )
            trace.n_obs_before = _int_or(summary, "n_cells_before", 0) or _int_or(
                summary, "initial_cells", 0
            )
            if "n_cells_before" in summary or "initial_cells" in summary:
                trace.n_obs_before_known = True
            trace.n_vars_before = _int_or(summary, "n_genes_before", 0) or _int_or(
                summary, "initial_genes", 0
            )
            trace.n_clusters = _int_or(summary, "n_clusters", None)
            trace.n_batches = _int_or(summary, "n_batches", None)

            # Effective params may record method/embedding info
            eff = data.get("effective_params", {})
            if "counts_layer" in eff:
                trace.layers = ["counts"]

            # Embeddings
            viz = data.get("visualization", {})
            if "embedding_key" in viz:
                trace.embedding_keys = [viz["embedding_key"]]

        # Try adata for richer info (only if h5ad exists and is small enough)
        adata_path = output_dir / "processed.h5ad"
        if adata_path.exists():
            try:
                adata_info = _read_adata_shape(adata_path)
                if adata_info:
                    trace.n_obs_after = adata_info["n_obs"]
                    trace.n_vars_after = adata_info["n_vars"]
                    trace.layers = adata_info.get("layers", [])
                    trace.obs_columns = adata_info.get("obs_columns", [])
                    trace.var_columns = adata_info.get("var_columns", [])
                    trace.embedding_keys = adata_info.get("embedding_keys", [])
                    if adata_info.get("n_batches") is not None:
                        trace.n_batches = adata_info["n_batches"]
                    if adata_info.get("n_clusters") is not None:
                        trace.n_clusters = adata_info["n_clusters"]
            except Exception as exc:
                logger.debug("Could not read adata for trace: %s", exc)

        # Compute cell retention
        if trace.n_obs_before > 0 and trace.n_obs_after > 0:
            trace.cell_retention_rate = trace.n_obs_after / trace.n_obs_before
        elif trace.n_obs_after > 0:
            trace.cell_retention_rate = 1.0

        return trace

    @staticmethod
    def _extract_method_trace(output_dir: Path, method: str) -> MethodTrace:
        """Extract method selection info from result.json."""
        trace = MethodTrace(requested_method=method, executed_method=method)

        result_data = _load_result_json(output_dir)
        if not result_data:
            return trace

        data = result_data.get("data", {})
        summary = result_data.get("summary", {})

        # Check for fallback fields (as in sc-batch-integration)
        for section in (data, summary):
            if "requested_method" in section:
                trace.requested_method = section["requested_method"]
            if "executed_method" in section:
                trace.executed_method = section["executed_method"]
            if "fallback_used" in section:
                trace.fallback_used = bool(section["fallback_used"])
            if "fallback_reason" in section:
                trace.fallback_reason = section["fallback_reason"]

        # Also check effective_params
        eff = data.get("effective_params", {})
        if "method" in eff:
            trace.executed_method = eff["method"]

        return trace

    @staticmethod
    def _extract_parameter_trace(
        output_dir: Path,
        user_params: dict[str, Any],
        skill_defaults: dict[str, Any],
    ) -> ParameterTrace:
        """Extract parameter provenance from result.json."""
        trace = ParameterTrace(
            user_params=dict(user_params),
            skill_defaults=dict(skill_defaults),
        )

        result_data = _load_result_json(output_dir)
        if result_data:
            data = result_data.get("data", {})
            eff = data.get("effective_params", {})
            if eff:
                trace.effective_params = dict(eff)
            elif data.get("params"):
                trace.effective_params = dict(data["params"])

        # Fill effective from user params if result.json didn't have it
        if not trace.effective_params:
            merged = dict(skill_defaults)
            merged.update(user_params)
            trace.effective_params = merged

        return trace

    @staticmethod
    def _extract_quality_trace(output_dir: Path) -> QualityTrace:
        """Extract quality metrics from result.json summary."""
        trace = QualityTrace()

        result_data = _load_result_json(output_dir)
        if not result_data:
            return trace

        summary = result_data.get("summary", {})
        # Collect any numeric values from summary as potential metrics
        for key, value in summary.items():
            if isinstance(value, (int, float)) and not key.startswith("n_"):
                try:
                    trace.quality_metrics[key] = float(value)
                except (ValueError, TypeError):
                    pass

        return trace


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_RESULT_JSON_CACHE: dict[str, dict[str, Any] | None] = {}


def _load_result_json(output_dir: Path) -> dict[str, Any] | None:
    """Load and cache result.json from an output directory."""
    key = str(output_dir)
    if key in _RESULT_JSON_CACHE:
        return _RESULT_JSON_CACHE[key]

    path = output_dir / "result.json"
    if not path.exists():
        _RESULT_JSON_CACHE[key] = None
        return None

    try:
        data = normalize_result_payload(
            json.loads(path.read_text(encoding="utf-8"))
        )
        _RESULT_JSON_CACHE[key] = data
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Failed to read result.json in %s: %s", output_dir, exc)
        _RESULT_JSON_CACHE[key] = None
        return None


def clear_result_json_cache() -> None:
    """Clear the result.json cache (useful between test runs)."""
    _RESULT_JSON_CACHE.clear()


def _extract_traceback(stderr: str) -> str | None:
    """Extract the last Python traceback from stderr.

    Captures from "Traceback (most recent call last):" through the
    final exception line (e.g. ``ValueError: ...``).
    """
    if not stderr:
        return None

    # Match from "Traceback" through indented lines + the final error line.
    # The final error line is non-indented and typically contains ": ".
    tb_pattern = (
        r"Traceback \(most recent call last\):\n"
        r"(?:[ \t]+.*\n)*"  # indented lines (file refs, code)
        r"\S[^\n]*"  # final error line (e.g. ValueError: ...)
    )
    matches = re.findall(tb_pattern, stderr)
    if matches:
        return matches[-1].strip()
    return None


def _extract_warnings(stderr: str) -> list[str]:
    """Extract Python warning lines from stderr."""
    if not stderr:
        return []

    warnings: list[str] = []
    for line in stderr.splitlines():
        stripped = line.strip()
        if (
            "Warning:" in stripped
            or "UserWarning:" in stripped
            or "FutureWarning:" in stripped
            or "DeprecationWarning:" in stripped
            or stripped.startswith("WARNING")
        ):
            warnings.append(stripped)
    return warnings


def _read_adata_shape(adata_path: Path) -> dict[str, Any] | None:
    """Read shape info from an h5ad file without loading the full matrix.

    Uses anndata's backed mode or h5py for minimal memory usage.
    """
    try:
        import anndata as ad

        adata = ad.read_h5ad(adata_path, backed="r")
        info: dict[str, Any] = {
            "n_obs": adata.n_obs,
            "n_vars": adata.n_vars,
            "layers": list(adata.layers.keys()),
            "obs_columns": list(adata.obs.columns),
            "var_columns": list(adata.var.columns),
            "embedding_keys": [
                k for k in adata.obsm.keys() if k.startswith("X_")
            ],
        }

        # Cluster count
        for col in ("leiden", "louvain", "cell_type", "cluster", "domain"):
            if col in adata.obs.columns:
                try:
                    info["n_clusters"] = int(adata.obs[col].nunique())
                except Exception:
                    pass
                break

        # Batch count
        for col in ("batch", "sample", "batch_key"):
            if col in adata.obs.columns:
                try:
                    info["n_batches"] = int(adata.obs[col].nunique())
                except Exception:
                    pass
                break

        adata.file.close()
        return info
    except Exception as exc:
        logger.debug("Failed to read adata shape from %s: %s", adata_path, exc)
        return None


def _int_or(d: dict, key: str, default: int | None) -> int | None:
    """Safely extract an integer from a dict."""
    val = d.get(key)
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _param_diff(
    effective: dict[str, Any],
    defaults: dict[str, Any],
) -> list[str]:
    """Compute human-readable diffs between effective and default params."""
    diffs: list[str] = []
    for key in sorted(set(effective) | set(defaults)):
        eff_val = effective.get(key)
        def_val = defaults.get(key)
        if eff_val != def_val and eff_val is not None and def_val is not None:
            diffs.append(f"{key}: {def_val} -> {eff_val}")
    return diffs
