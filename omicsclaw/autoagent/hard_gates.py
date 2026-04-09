"""Hard gates — must-pass checks before composite scoring.

The acceptance function for harness-level evolution is:

    accept = hard_gates_pass AND composite_score_improved

Hard gates catch catastrophic regressions that a weighted score might
mask.  They run before the soft metric comparison and produce a clear
pass/fail signal with diagnostics.

Gate categories:
1. **no_crash** — exit code must be 0.
2. **artifacts_present** — required output files must exist.
3. **cell_retention** — cell count must not collapse below threshold.
4. **fallback_recorded** — if a fallback occurred it must be logged.
5. **no_empty_output** — processed adata must have >0 cells and >0 genes.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from omicsclaw.autoagent.trace import RunTrace

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Gate result
# ---------------------------------------------------------------------------


@dataclass
class GateResult:
    """Result of a single hard gate check."""

    name: str
    passed: bool
    message: str
    value: Any = None
    threshold: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HardGateVerdict:
    """Aggregated result of all hard gates for one trial."""

    all_passed: bool
    results: list[GateResult] = field(default_factory=list)

    @property
    def failed_gates(self) -> list[GateResult]:
        return [r for r in self.results if not r.passed]

    def summary(self) -> str:
        """One-line pass/fail summary for logging."""
        if self.all_passed:
            return f"All {len(self.results)} hard gates passed."
        failed = self.failed_gates
        names = ", ".join(g.name for g in failed)
        return f"{len(failed)}/{len(self.results)} hard gate(s) FAILED: {names}"

    def to_diagnostic(self) -> str:
        """Multi-line diagnostic for Meta-Agent context."""
        lines: list[str] = []
        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            line = f"  [{status}] {r.name}: {r.message}"
            if r.value is not None:
                line += f" (value={r.value}"
                if r.threshold is not None:
                    line += f", threshold={r.threshold}"
                line += ")"
            lines.append(line)
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "all_passed": self.all_passed,
            "results": [r.to_dict() for r in self.results],
        }


# ---------------------------------------------------------------------------
# Gate definitions
# ---------------------------------------------------------------------------


def gate_no_crash(trace: RunTrace) -> GateResult:
    """Trial must complete without crashing (exit_code == 0)."""
    passed = trace.execution.exit_code == 0
    return GateResult(
        name="no_crash",
        passed=passed,
        message="Process exited cleanly." if passed else (
            f"Process crashed with exit code {trace.execution.exit_code}."
        ),
        value=trace.execution.exit_code,
        threshold=0,
    )


def gate_artifacts_present(
    trace: RunTrace,
    output_dir: Path,
    required_files: list[str] | None = None,
) -> GateResult:
    """Required output files must exist in the output directory.

    Default required files: ``result.json``.  For adata-producing skills,
    ``processed.h5ad`` is also required.
    """
    if required_files is None:
        required_files = ["result.json"]
        # If skill typically produces adata, also require it
        if _is_adata_skill(trace.skill_name):
            required_files.append("processed.h5ad")

    output_dir = Path(output_dir)
    missing = [f for f in required_files if not (output_dir / f).exists()]

    passed = len(missing) == 0
    if passed:
        msg = f"All {len(required_files)} required artifact(s) present."
    else:
        msg = f"Missing artifacts: {', '.join(missing)}"

    return GateResult(
        name="artifacts_present",
        passed=passed,
        message=msg,
        value=required_files if passed else missing,
    )


def gate_cell_retention(
    trace: RunTrace,
    min_retention: float = 0.05,
) -> GateResult:
    """Cell retention rate must not collapse below threshold.

    A retention rate of 0.05 means at least 5% of cells must survive
    filtering.  This catches catastrophic over-filtering.
    """
    rate = trace.data_shape.cell_retention_rate
    n_before = trace.data_shape.n_obs_before
    n_after = trace.data_shape.n_obs_after

    # Skip if the pre-filter count was never recorded (unknown).
    # If it was explicitly recorded as 0, the gate should fail.
    if n_before == 0 and not trace.data_shape.n_obs_before_known:
        return GateResult(
            name="cell_retention",
            passed=True,
            message="Skipped: no pre-filter cell count available.",
        )
    if n_before == 0 and trace.data_shape.n_obs_before_known:
        return GateResult(
            name="cell_retention",
            passed=False,
            message="Input data has 0 cells (n_obs_before=0).",
            value=0.0,
            threshold=min_retention,
        )

    passed = rate >= min_retention
    if passed:
        msg = (
            f"Retained {n_after}/{n_before} cells "
            f"({rate:.1%} >= {min_retention:.0%})."
        )
    else:
        msg = (
            f"Cell retention collapsed: {n_after}/{n_before} cells "
            f"({rate:.1%} < {min_retention:.0%} threshold)."
        )

    return GateResult(
        name="cell_retention",
        passed=passed,
        message=msg,
        value=round(rate, 4),
        threshold=min_retention,
    )


def gate_no_empty_output(trace: RunTrace) -> GateResult:
    """Processed output must have >0 cells and >0 genes."""
    n_obs = trace.data_shape.n_obs_after
    n_vars = trace.data_shape.n_vars_after

    # Skip if data shape is unknown
    if n_obs == 0 and n_vars == 0 and trace.execution.exit_code == 0:
        # Might just not have shape info; don't fail
        return GateResult(
            name="no_empty_output",
            passed=True,
            message="Skipped: data shape not available in trace.",
        )

    passed = n_obs > 0 and n_vars > 0
    if passed:
        msg = f"Output has {n_obs} cells x {n_vars} genes."
    else:
        msg = f"Empty output: {n_obs} cells x {n_vars} genes."

    return GateResult(
        name="no_empty_output",
        passed=passed,
        message=msg,
        value={"n_obs": n_obs, "n_vars": n_vars},
    )


def gate_fallback_recorded(trace: RunTrace) -> GateResult:
    """If a method fallback occurred, it must be recorded with a reason.

    Silent fallbacks (switching methods without logging why) undermine
    reproducibility and make diagnosis impossible.
    """
    mt = trace.method_trace

    # No fallback → pass
    if not mt.fallback_used:
        return GateResult(
            name="fallback_recorded",
            passed=True,
            message="No fallback occurred.",
        )

    # Fallback with reason → pass
    if mt.fallback_reason:
        return GateResult(
            name="fallback_recorded",
            passed=True,
            message=(
                f"Fallback recorded: {mt.requested_method} -> "
                f"{mt.executed_method} ({mt.fallback_reason})"
            ),
        )

    # Fallback without reason → fail
    return GateResult(
        name="fallback_recorded",
        passed=False,
        message=(
            f"Silent fallback: {mt.requested_method} -> "
            f"{mt.executed_method} with no recorded reason."
        ),
    )


# ---------------------------------------------------------------------------
# Run all gates
# ---------------------------------------------------------------------------

# Default gate list in execution order
DEFAULT_GATES = [
    "no_crash",
    "artifacts_present",
    "cell_retention",
    "no_empty_output",
    "fallback_recorded",
]


def run_hard_gates(
    trace: RunTrace,
    output_dir: Path,
    *,
    gates: list[str] | None = None,
    min_cell_retention: float = 0.05,
    required_artifacts: list[str] | None = None,
) -> HardGateVerdict:
    """Run all hard gates against a trial trace.

    Parameters
    ----------
    trace:
        The RunTrace from the completed trial.
    output_dir:
        Path to the trial output directory.
    gates:
        Subset of gate names to run. Defaults to :data:`DEFAULT_GATES`.
    min_cell_retention:
        Minimum cell retention rate (0.0-1.0).
    required_artifacts:
        Override default required artifact list.

    Returns
    -------
    HardGateVerdict
        Aggregated pass/fail with per-gate details.
    """
    output_dir = Path(output_dir)
    active_gates = gates or DEFAULT_GATES

    gate_dispatch = {
        "no_crash": lambda: gate_no_crash(trace),
        "artifacts_present": lambda: gate_artifacts_present(
            trace, output_dir, required_artifacts,
        ),
        "cell_retention": lambda: gate_cell_retention(
            trace, min_cell_retention,
        ),
        "no_empty_output": lambda: gate_no_empty_output(trace),
        "fallback_recorded": lambda: gate_fallback_recorded(trace),
    }

    results: list[GateResult] = []
    for gate_name in active_gates:
        gate_fn = gate_dispatch.get(gate_name)
        if gate_fn is None:
            logger.warning("Unknown hard gate: %s", gate_name)
            continue
        try:
            result = gate_fn()
        except Exception as exc:
            result = GateResult(
                name=gate_name,
                passed=False,
                message=f"Gate raised exception: {exc}",
            )
        results.append(result)

    all_passed = all(r.passed for r in results)
    return HardGateVerdict(all_passed=all_passed, results=results)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ADATA_SKILLS = frozenset({
    "sc-preprocessing", "sc-batch-integration", "sc-cell-annotation",
    "sc-clustering", "sc-doublet-detection", "sc-filter", "sc-qc",
    "sc-ambient-removal", "sc-pseudotime", "sc-velocity", "sc-grn",
    "sc-cell-communication", "sc-de", "sc-markers",
    "spatial-preprocessing", "spatial-domains", "spatial-de",
    "spatial-genes", "spatial-statistics", "spatial-annotate",
    "spatial-deconvolution", "spatial-communication", "spatial-velocity",
    "spatial-trajectory", "spatial-enrichment", "spatial-cnv",
    "spatial-integration", "spatial-registration",
    "spatial-condition-comparison",
})


def _is_adata_skill(skill_name: str) -> bool:
    """Check if a skill typically produces processed.h5ad."""
    return skill_name in _ADATA_SKILLS
