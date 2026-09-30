"""The probe: which trials give the stability evidence, the reference ranges and the baselines.

Every method with an ``exact`` K control runs once per K of the grid with
its other parameters at their defaults. Every method with a ``calibrate`` K
control runs once per value of the resolution grid on the full input, and
again on each subsample. The design and its constants are fixed; nothing
here depends on the data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from omicsclaw.ensemble.space import TuningSpec

__all__ = [
    "BOOT_A",
    "BOOT_FC",
    "B_SUB",
    "CONSENSUS_SEED",
    "CONSENSUS_SUBSET",
    "K_GRID",
    "MIN_F",
    "PROBE_CONSTANTS",
    "ProbeItem",
    "RESOLUTION_GRID",
    "SEED_A",
    "SEED_FC",
    "SUBSAMPLE_FRACTION",
    "SUBSAMPLE_SEEDS",
    "probe_design",
    "probe_run_id",
    "split_methods",
    "sub_run_id",
]

K_GRID: tuple[int, ...] = tuple(range(3, 17))
RESOLUTION_GRID: tuple[float, ...] = tuple(round(0.10 + 0.05 * i, 2) for i in range(39))
B_SUB = 20
SUBSAMPLE_FRACTION = 0.8
SUBSAMPLE_SEEDS: tuple[int, ...] = tuple(range(5701, 5701 + B_SUB))
CONSENSUS_SEED = 5700
CONSENSUS_SUBSET = 5000
SEED_FC = 5800
SEED_A = 5801
BOOT_FC = 1000
BOOT_A = 200
MIN_F = 0.025

PROBE_CONSTANTS: Mapping[str, Any] = {
    "k_grid": list(K_GRID),
    "resolution_grid": list(RESOLUTION_GRID),
    "b_sub": B_SUB,
    "subsample_fraction": SUBSAMPLE_FRACTION,
    "subsample_seeds": list(SUBSAMPLE_SEEDS),
    "consensus_seed": CONSENSUS_SEED,
    "consensus_subset": CONSENSUS_SUBSET,
    "boot_fc": BOOT_FC,
    "seed_fc": SEED_FC,
    "boot_a": BOOT_A,
    "seed_a": SEED_A,
    "min_f": MIN_F,
}
"""The probe's constants, as recorded in the ledger."""


@dataclass(frozen=True, slots=True)
class ProbeItem:
    """One probe trial.

    ``kind`` is ``exact`` (an exact method at one K), ``full`` (a calibrated
    method at one resolution on the full input) or ``sub`` (the same on
    subsample ``b``, counted from 1).
    """

    method: str
    kind: str
    params: Mapping[str, Any] = field(default_factory=dict)
    requested_k: int | None = None
    resolution: float | None = None
    b: int | None = None


def probe_run_id(base: str) -> str:
    return f"{base}-probe"


def sub_run_id(base: str, b: int) -> str:
    return f"{base}-sub{b:02d}"


def split_methods(spec: TuningSpec, methods: Iterable[str]) -> tuple[list[str], list[str]]:
    """*methods* split into those with an exact and those with a calibrated K control.

    Methods without a K control are left out.
    """
    exact: list[str] = []
    calibrated: list[str] = []
    for name in methods:
        control = spec.method(name).k_control
        if control is None:
            continue
        (exact if control.kind == "exact" else calibrated).append(name)
    return exact, calibrated


def probe_design(
    spec: TuningSpec,
    methods: Sequence[str],
    *,
    grid: Sequence[int] = K_GRID,
    resolutions: Sequence[float] = RESOLUTION_GRID,
    n_sub: int = B_SUB,
    subsample: bool = True,
) -> list[ProbeItem]:
    """Every probe trial of *methods*: exact methods first, then full, then subsample runs.

    A K outside an exact method's parameter range, or a resolution outside a
    calibrated method's, is skipped.
    """
    exact, calibrated = split_methods(spec, methods)
    items: list[ProbeItem] = []
    for name in exact:
        method = spec.method(name)
        control = method.k_control
        param = method.params[control.param]
        for k in grid:
            if not param.low <= k <= param.high:
                continue
            items.append(ProbeItem(method=name, kind="exact", params={**control.pin, control.param: int(k)},
                                   requested_k=int(k)))
    for kind, bs in (("full", [None]), ("sub", list(range(1, n_sub + 1)) if subsample else [])):
        for b in bs:
            for name in calibrated:
                method = spec.method(name)
                control = method.k_control
                param = method.params[control.param]
                for resolution in resolutions:
                    if not param.low <= resolution <= param.high:
                        continue
                    value = int(round(resolution)) if param.type == "int" else float(resolution)
                    items.append(ProbeItem(method=name, kind=kind, params={**control.pin, control.param: value},
                                           resolution=float(resolution), b=b))
    return items
