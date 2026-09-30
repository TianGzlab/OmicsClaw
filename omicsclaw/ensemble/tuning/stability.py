"""Stability curves over a K grid: ``python -m omicsclaw.ensemble.tuning.stability``.

Three curves, each defined on the grid K and each reported with a bootstrap
band and a peak frequency:

``f(K)``
    Share of the subsample runs whose number of labels is K.
``c(K) = 1 - rPAC(K)``
    From the consensus matrix of every subsample run with K labels:
    ``M_ij`` = times i and j share a label / times both were present.
    Over the pairs present together at least once, ``PAC = F(0.9) - F(0.1)``
    for the empirical distribution ``F`` of ``M``, ``prop_zeroes`` the share
    of ``M = 0``, and ``rPAC = PAC / (1 - prop_zeroes)``. Undefined with fewer
    than two runs at K. Above 5000 observations it is computed on a fixed
    random subset of 5000.
``a(K)``
    Mean pairwise adjusted mutual information between the partitions with K
    labels: each exact method's probe trial with K labels, and each
    calibrated method's full-data trial with K labels (the one of median
    resolution when there are several). Undefined with fewer than three.

Bands: ``f`` and ``c`` from resampling the subsample indices with
replacement, ``a`` from resampling observations; 2.5% and 97.5% quantiles.
A peak is a K whose value is not below its neighbours among the K where the
curve is defined (``f`` and ``c`` only where ``f(K) >= min_f``); a K's peak
frequency is the share of resamples in which it is a peak.

Input: ``--spec`` JSON (see :func:`compute`). Output: ``--output`` JSON.
Runs under the skill interpreter.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

__all__ = ["compute", "main", "pac_statistics", "peaks", "rpac_multik"]

PAC_LOW = 0.1
PAC_HIGH = 0.9
PAIR_CHUNK = 25_000

_SHARED: dict[str, Any] = {}


# ---- small pieces ----------------------------------------------------------------------


def peaks(values: Mapping[int, float]) -> list[int]:
    """The K of *values* not below their neighbours in sorted K order (an end has one neighbour)."""
    keys = sorted(k for k, v in values.items() if v is not None and not math.isnan(v))
    found = []
    for index, k in enumerate(keys):
        left = values[keys[index - 1]] if index > 0 else -math.inf
        right = values[keys[index + 1]] if index < len(keys) - 1 else -math.inf
        if values[k] >= left and values[k] >= right:
            found.append(k)
    return found


def pac_statistics(co: np.ndarray, both: np.ndarray) -> dict[str, float]:
    """PAC, the share of zeroes, rPAC and ``1 - rPAC`` over the pairs with ``both > 0``."""
    present = both > 0
    total = int(present.sum())
    if total == 0:
        return {"pac": math.nan, "prop_zeroes": math.nan, "rpac": math.nan, "c": math.nan}
    m = co[present] / both[present]
    zeroes = float((m == 0).sum()) / total
    pac = float(((m > PAC_LOW) & (m <= PAC_HIGH)).sum()) / total
    rpac = pac / (1 - zeroes) if zeroes < 1 else math.nan
    return {"pac": pac, "prop_zeroes": zeroes, "rpac": rpac, "c": 1 - rpac if not math.isnan(rpac) else math.nan}


def rpac_multik(matrix: np.ndarray) -> float:
    """rPAC of a full consensus matrix exactly as MultiK computes it.

    ``Fn`` is the empirical CDF of the lower triangle, ``PAC = Fn(0.9) - Fn(0.1)``
    and ``prop_zeroes`` counts zeroes over the whole matrix.
    """
    lower = matrix[np.tril_indices_from(matrix, k=-1)]
    fn = lambda x: float((lower <= x).mean())  # noqa: E731
    pac = fn(PAC_HIGH) - fn(PAC_LOW)
    prop_zeroes = float((matrix == 0).sum()) / matrix.size
    return pac / (1 - prop_zeroes)


def _codes(labels: Sequence[str]) -> np.ndarray:
    _, codes = np.unique(np.asarray(labels, dtype=str), return_inverse=True)
    return codes.astype(np.int32)


def _read_labels(path: str) -> dict[str, str]:
    import pandas as pd

    table = pd.read_csv(path, dtype=str, keep_default_na=False)
    return dict(zip(table["obs_id"], table["label"]))


def _aligned(labels: Mapping[str, str], position: Mapping[str, int], n: int) -> np.ndarray:
    """Integer codes in input order, ``-1`` for observations without a label."""
    codes = np.full(n, -1, dtype=np.int32)
    names = list(labels)
    values = _codes([labels[name] for name in names])
    for name, code in zip(names, values):
        index = position.get(name)
        if index is not None:
            codes[index] = code
    return codes


# ---- the consensus curve -----------------------------------------------------------------


def _consensus_worker(k: int) -> tuple[int, dict[str, float], list[float]]:
    runs: list[tuple[int, np.ndarray]] = _SHARED["runs_by_k"].get(k, [])
    upper0, upper1 = _SHARED["pairs"]
    together: np.ndarray = _SHARED["together"]
    weights: np.ndarray = _SHARED["weights"]
    n_sub = together.shape[0]
    counts = np.zeros(n_sub, dtype=np.float32)
    co = np.zeros((n_sub, upper0.shape[0]), dtype=np.uint16)
    for b, codes in runs:
        left = codes[upper0]
        co[b] += (left == codes[upper1]) & (left >= 0)
        counts[b] += 1
    if len(runs) < 2:
        full = {"pac": math.nan, "prop_zeroes": math.nan, "rpac": math.nan, "c": math.nan}
    else:
        both = np.zeros(upper0.shape[0], dtype=np.float32)
        total = np.zeros(upper0.shape[0], dtype=np.float32)
        for b in range(n_sub):
            if counts[b]:
                both += counts[b] * together[b]
                total += co[b]
        full = pac_statistics(total, both)
    replicates = weights.shape[0]
    zero = np.zeros(replicates)
    pac = np.zeros(replicates)
    valid = np.zeros(replicates)
    runs_boot = weights @ counts
    active = runs_boot >= 2
    if active.any():
        scaled = (weights * counts[None, :]).astype(np.float32)
        weights32 = weights.astype(np.float32)
        for start in range(0, upper0.shape[0], PAIR_CHUNK):
            stop = start + PAIR_CHUNK
            co_b = weights32 @ co[:, start:stop].astype(np.float32)
            both_b = scaled @ together[:, start:stop].astype(np.float32)
            present = both_b > 0
            with np.errstate(divide="ignore", invalid="ignore"):
                m = np.where(present, co_b / np.where(present, both_b, 1), -1.0)
            valid += present.sum(axis=1)
            zero += (m == 0).sum(axis=1)
            pac += ((m > PAC_LOW) & (m <= PAC_HIGH)).sum(axis=1)
    boot = []
    for r in range(replicates):
        if not active[r] or valid[r] == 0 or zero[r] >= valid[r]:
            boot.append(math.nan)
            continue
        rp = (pac[r] / valid[r]) / (1 - zero[r] / valid[r])
        boot.append(1 - rp)
    return k, full, boot


# ---- the agreement curve --------------------------------------------------------------------


def _agreement_worker(k: int) -> tuple[int, float, list[float]]:
    from sklearn.metrics import adjusted_mutual_info_score

    members: list[np.ndarray] = _SHARED["members_by_k"].get(k, [])
    if len(members) < 3:
        return k, math.nan, [math.nan] * len(_SHARED["obs_draws"])
    pairs = list(itertools.combinations(range(len(members)), 2))
    full = float(np.mean([adjusted_mutual_info_score(members[i], members[j]) for i, j in pairs]))
    boot = []
    for draw in _SHARED["obs_draws"]:
        boot.append(float(np.mean([
            adjusted_mutual_info_score(members[i][draw], members[j][draw]) for i, j in pairs
        ])))
    return k, full, boot


# ---- putting it together ----------------------------------------------------------------------


def _quantiles(values: Sequence[float]) -> tuple[float | None, float | None]:
    finite = [v for v in values if v is not None and not math.isnan(v)]
    if not finite:
        return None, None
    return float(np.quantile(finite, 0.025)), float(np.quantile(finite, 0.975))


def _clean(value: float | None) -> float | None:
    if value is None or math.isnan(value):
        return None
    return round(float(value), 6)


def compute(spec: Mapping[str, Any], *, processes: int | None = None) -> dict[str, Any]:
    """The stability document for *spec*.

    :param spec: ``input`` (the ``.h5ad`` whose observation order is used),
        ``grid`` (list of K), ``n_sub`` (number of subsamples), ``sub``
        (``[{b, method, resolution, labels}]``, ``b`` from 1), ``full``
        (``[{method, resolution, labels}]``), ``exact`` (``[{method,
        requested_k, labels}]``), and the constants ``min_f``,
        ``boot_fc``, ``boot_a``, ``seed_fc``, ``seed_a``,
        ``consensus_subset`` and ``consensus_seed``.
    """
    import anndata

    adata = anndata.read_h5ad(spec["input"], backed="r")
    try:
        obs_ids = [str(x) for x in adata.obs_names]
    finally:
        if getattr(adata, "file", None) is not None:
            adata.file.close()
    n = len(obs_ids)
    grid = [int(k) for k in spec["grid"]]
    n_sub = int(spec["n_sub"])
    min_f = float(spec.get("min_f", 0.025))
    subset_size = int(spec.get("consensus_subset", 5000))
    position_all = {name: i for i, name in enumerate(obs_ids)}

    if n > subset_size:
        rng = np.random.default_rng(int(spec.get("consensus_seed", 5700)))
        subset = np.sort(rng.choice(n, size=subset_size, replace=False))
        consensus_subset: int | None = subset_size
    else:
        subset = np.arange(n)
        consensus_subset = None
    position_sub = {obs_ids[i]: j for j, i in enumerate(subset)}
    m = subset.shape[0]

    runs_by_k: dict[int, list[tuple[int, np.ndarray]]] = {}
    presence = np.zeros((n_sub, m), dtype=bool)
    k_of_run: list[tuple[int, int]] = []
    for item in spec.get("sub", []):
        labels = _read_labels(item["labels"])
        b = int(item["b"]) - 1
        codes = _aligned(labels, position_sub, m)
        presence[b] |= codes >= 0
        k = len(set(labels.values()))
        k_of_run.append((b, k))
        if k in grid:
            runs_by_k.setdefault(k, []).append((b, codes))
    per_b_total = np.zeros(n_sub)
    per_b_at = {k: np.zeros(n_sub) for k in grid}
    for b, k in k_of_run:
        per_b_total[b] += 1
        if k in per_b_at:
            per_b_at[k][b] += 1

    upper0, upper1 = np.triu_indices(m, k=1)
    upper0 = upper0.astype(np.int32)
    upper1 = upper1.astype(np.int32)
    together = presence[:, upper0] & presence[:, upper1]

    boot_fc = int(spec.get("boot_fc", 1000))
    rng_fc = np.random.default_rng(int(spec.get("seed_fc", 5800)))
    weights = np.zeros((boot_fc, n_sub))
    for r in range(boot_fc):
        picks = rng_fc.integers(0, n_sub, size=n_sub)
        np.add.at(weights[r], picks, 1)

    members_by_k: dict[int, list[np.ndarray]] = {}
    member_names: dict[int, list[str]] = {}
    exact_by_k: dict[tuple[str, int], tuple[int, np.ndarray]] = {}
    for item in spec.get("exact", []):
        labels = _read_labels(item["labels"])
        k = len(set(labels.values()))
        if k not in grid:
            continue
        codes = _aligned(labels, position_all, n)
        requested = int(item.get("requested_k", -1))
        key = (item["method"], k)
        rank = 0 if requested == k else 1
        if key not in exact_by_k or rank < exact_by_k[key][0]:
            exact_by_k[key] = (rank, codes)
    for (method, k), (_, codes) in sorted(exact_by_k.items()):
        members_by_k.setdefault(k, []).append(codes)
        member_names.setdefault(k, []).append(method)
    full_by: dict[tuple[str, int], list[tuple[float, np.ndarray]]] = {}
    for item in spec.get("full", []):
        labels = _read_labels(item["labels"])
        k = len(set(labels.values()))
        if k not in grid:
            continue
        full_by.setdefault((item["method"], k), []).append(
            (float(item["resolution"]), _aligned(labels, position_all, n))
        )
    for (method, k), entries in sorted(full_by.items()):
        entries.sort(key=lambda entry: entry[0])
        members_by_k.setdefault(k, []).append(entries[len(entries) // 2][1])
        member_names.setdefault(k, []).append(method)

    boot_a = int(spec.get("boot_a", 200))
    rng_a = np.random.default_rng(int(spec.get("seed_a", 5801)))
    obs_draws = [rng_a.integers(0, n, size=n) for _ in range(boot_a)]

    _SHARED.clear()
    _SHARED.update(
        runs_by_k=runs_by_k, pairs=(upper0, upper1), together=together, weights=weights,
        members_by_k=members_by_k, obs_draws=obs_draws,
    )
    workers = processes or min(len(grid) * 2, os.cpu_count() or 1, 32)
    try:
        if workers > 1:
            import multiprocessing

            with multiprocessing.get_context("fork").Pool(workers) as pool:
                consensus = pool.map(_consensus_worker, grid)
                agreement = pool.map(_agreement_worker, grid)
        else:
            consensus = [_consensus_worker(k) for k in grid]
            agreement = [_agreement_worker(k) for k in grid]
    finally:
        _SHARED.clear()
    c_full = {k: full["c"] for k, full, _ in consensus}
    c_detail = {k: full for k, full, _ in consensus}
    c_boot = {k: boot for k, _, boot in consensus}
    a_full = {k: full for k, full, _ in agreement}
    a_boot = {k: boot for k, _, boot in agreement}

    total_runs = float(per_b_total.sum())
    f_full = {k: (per_b_at[k].sum() / total_runs if total_runs else math.nan) for k in grid}
    totals_boot = weights @ per_b_total
    f_boot: dict[int, list[float]] = {}
    for k in grid:
        at_k = weights @ per_b_at[k]
        f_boot[k] = [float(at / total) if total > 0 else math.nan for at, total in zip(at_k, totals_boot)]

    peak_counts = {name: {k: 0 for k in grid} for name in ("f", "c", "a")}
    for r in range(boot_fc):
        f_r = {k: f_boot[k][r] for k in grid}
        gated = {k: v for k, v in f_r.items() if not math.isnan(v) and v >= min_f}
        for k in peaks(gated):
            peak_counts["f"][k] += 1
        c_r = {k: c_boot[k][r] for k in gated if not math.isnan(c_boot[k][r])}
        for k in peaks(c_r):
            peak_counts["c"][k] += 1
    for r in range(boot_a):
        a_r = {k: a_boot[k][r] for k in grid if not math.isnan(a_boot[k][r])}
        for k in peaks(a_r):
            peak_counts["a"][k] += 1

    rows = {}
    for k in grid:
        f_lo, f_hi = _quantiles(f_boot[k])
        c_lo, c_hi = _quantiles(c_boot[k])
        a_lo, a_hi = _quantiles(a_boot[k])
        rows[str(k)] = {
            "k": k,
            "f": _clean(f_full[k]), "f_lo": _clean(f_lo), "f_hi": _clean(f_hi),
            "c": _clean(c_full[k]), "c_lo": _clean(c_lo), "c_hi": _clean(c_hi),
            "a": _clean(a_full[k]), "a_lo": _clean(a_lo), "a_hi": _clean(a_hi),
            "runs": len(runs_by_k.get(k, [])),
            "pac": _clean(c_detail[k]["pac"]),
            "prop_zeroes": _clean(c_detail[k]["prop_zeroes"]),
            "a_members": member_names.get(k, []),
            "peak_frequency": {
                "f": round(peak_counts["f"][k] / boot_fc, 6) if boot_fc else None,
                "c": round(peak_counts["c"][k] / boot_fc, 6) if boot_fc else None,
                "a": round(peak_counts["a"][k] / boot_a, 6) if boot_a else None,
            },
        }
    return {
        "schema": "omicsclaw.ensemble.stability/1",
        "grid": grid,
        "n_obs": n,
        "n_sub": n_sub,
        "sub_runs": int(total_runs),
        "min_f": min_f,
        "boot_fc": boot_fc,
        "boot_a": boot_a,
        "seeds": {"fc": int(spec.get("seed_fc", 5800)), "a": int(spec.get("seed_a", 5801)),
                  "consensus": int(spec.get("consensus_seed", 5700))},
        "consensus_subset": consensus_subset,
        "pac_bounds": [PAC_LOW, PAC_HIGH],
        "per_k": rows,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stability curves over a K grid.")
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--processes", type=int, default=None)
    args = parser.parse_args(argv)
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    document = compute(spec, processes=args.processes)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(temporary, args.output)
    print("STABILITY=" + json.dumps({"path": str(args.output)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
