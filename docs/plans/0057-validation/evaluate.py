"""Ground-truth evaluation of the 0057 arms: ARI per trial, the estimators D1/D2/D3, statistics.

Reads truth only through ``truth_map.json`` (uid -> file and column), which is
kept outside every workspace. On the hold-out it is run after the runs.

Estimators (per unit ``u``, over the methods whose default trial ended ok):

- ``D1(u) = mean_m [ARI(tun_m) - ARI(def_m)]``; a method whose tuned answer is
  ``fallback_default`` or failed contributes 0 (its default is its answer).
- ``D2(u) = ARI(fin) - median_m ARI(def_m)``; ``fin`` missing scores 0.
- ``D3(u) = ARI(fin) - max_m ARI(def_m)``.

Repetitions of an arm are averaged per unit before any statistic. Statistics:
mean, median, 95% t interval, 95% BCa bootstrap interval (10,000 resamples,
seed 20260926) and the exact two-sided sign-flip p value.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ARMS, RUNNABLE, read_json, write_json  # noqa: E402

BOOT_SEED = 20260926
BOOT_N = 10_000


# ---- truth and ARI --------------------------------------------------------------------------


class Truth:
    """Ground-truth labels of the units, loaded lazily from ``truth_map.json``."""

    def __init__(self, table: Mapping[str, Mapping[str, str]]):
        self.table = dict(table)
        self._cache: dict[tuple[str, str], dict[str, str]] = {}

    def labels(self, uid: str) -> dict[str, str]:
        """Truth labels by observation id; for a whole-dataset file, every observation of it."""
        entry = self.table[uid]
        key = (entry["path"], entry.get("column", ""))
        if key not in self._cache:
            if entry.get("format") == "csv":
                self._cache[key] = read_labels(entry["path"])
            else:
                import anndata

                adata = anndata.read_h5ad(entry["path"], backed="r")
                try:
                    column = adata.obs[entry["column"]]
                    self._cache[key] = {str(k): str(v) for k, v in column.items()
                                        if v == v and str(v) not in ("", "nan")}
                finally:
                    adata.file.close()
        return self._cache[key]

    def k_star(self, uid: str, observations: Iterable[str] | None = None, *, min_share: float = 0.0) -> int:
        """Number of truth classes among *observations* (all of the unit's truth when ``None``),
        counting only classes with at least *min_share* of them."""
        labels = self.labels(uid)
        values = [labels[o] for o in observations if o in labels] if observations is not None else list(labels.values())
        counts: dict[str, int] = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        total = sum(counts.values()) or 1
        return sum(1 for c in counts.values() if c / total >= min_share and c > 0)


def read_labels(path: str | Path) -> dict[str, str]:
    import pandas as pd

    table = pd.read_csv(path, dtype=str, keep_default_na=False)
    return dict(zip(table["obs_id"], table["label"]))


def ari(labels: Mapping[str, str], truth: Mapping[str, str]) -> float:
    from sklearn.metrics import adjusted_rand_score

    common = [k for k in labels if k in truth]
    return float(adjusted_rand_score([truth[k] for k in common], [labels[k] for k in common]))


# ---- statistics --------------------------------------------------------------------------------


def t_interval(values: Sequence[float], level: float = 0.95) -> tuple[float, float]:
    from scipy import stats

    n = len(values)
    if n < 2:
        return (math.nan, math.nan)
    mean = sum(values) / n
    sd = stats.tstd(values)
    half = stats.t.ppf(0.5 + level / 2, n - 1) * sd / math.sqrt(n)
    return (mean - half, mean + half)


def bca_interval(values: Sequence[float], level: float = 0.95) -> tuple[float, float]:
    import numpy as np
    from scipy import stats

    if len(values) < 3 or len(set(values)) < 2:
        return (math.nan, math.nan)
    result = stats.bootstrap((np.asarray(values),), np.mean, n_resamples=BOOT_N, confidence_level=level,
                             method="BCa", random_state=np.random.default_rng(BOOT_SEED))
    return (float(result.confidence_interval.low), float(result.confidence_interval.high))


def sign_flip_p(values: Sequence[float], *, one_sided: bool = False, draws: int = 0) -> float:
    """Exact sign-flip p value of the mean (two-sided unless *one_sided*: H1 mean > 0)."""
    n = len(values)
    if n == 0:
        return math.nan
    observed = sum(values) / n
    count = total = 0
    for signs in itertools.product((1, -1), repeat=n):
        mean = sum(s * v for s, v in zip(signs, values)) / n
        total += 1
        if one_sided:
            count += mean >= observed - 1e-12
        else:
            count += abs(mean) >= abs(observed) - 1e-12
    return count / total


def describe(values: Sequence[float]) -> dict[str, Any]:
    values = [v for v in values if v is not None and not math.isnan(v)]
    if not values:
        return {"n": 0}
    import statistics

    return {
        "n": len(values),
        "mean": sum(values) / len(values),
        "median": median(values),
        "sd": statistics.stdev(values) if len(values) > 1 else None,
        "t95": t_interval(values),
        "bca95": bca_interval(values),
        "sign_flip_p": sign_flip_p(values) if len(values) <= 16 else None,
    }


# ---- per unit ----------------------------------------------------------------------------------------


def _method_labels(entry: Mapping[str, Any] | None) -> str | None:
    if not entry or entry.get("status") == "failed":
        return None
    return entry.get("labels")


def unit_scores(root: Path, uid: str, truth: Truth) -> dict[str, Any]:
    """ARI of every default trial, of A0k, and of each arm repetition's answers, with D1/D2/D3."""
    probe = read_json(root / uid / "probe" / "result.json")
    unit_obs = next(iter(read_labels(a0["labels"]) for a0 in probe["a0"].values() if a0 and a0.get("status") == "ok"))
    labels_truth = {o: v for o, v in truth.labels(uid).items() if o in unit_obs}
    defaults: dict[str, float] = {}
    for method in RUNNABLE:
        a0 = probe["a0"].get(method)
        if a0 and a0.get("status") == "ok":
            defaults[method] = ari(read_labels(a0["labels"]), labels_truth)
    methods = sorted(defaults)
    out: dict[str, Any] = {"uid": uid, "k_star": truth.k_star(uid, unit_obs),
                           "k_star_5pct": truth.k_star(uid, unit_obs, min_share=0.05),
                           "n_obs": len(unit_obs), "n_truth": len(labels_truth), "default_ari": defaults,
                           "median_def": median(defaults.values()) if defaults else None,
                           "max_def": max(defaults.values()) if defaults else None}
    a0k_file = root / uid / "a0k" / "result.json"
    if a0k_file.exists():
        a0k = read_json(a0k_file)
        out["a0k"] = {"n_labels": a0k.get("n_labels"),
                      "ari": ari(read_labels(a0k["labels"]), labels_truth) if a0k.get("status") == "ok" else None}
    arms: dict[str, list[dict[str, Any]]] = {}
    for arm in ARMS:
        for result_file in sorted((root / uid / arm).glob("r*/result.json")):
            result = read_json(result_file)
            arms.setdefault(arm, []).append(_rep_scores(result, methods, defaults, labels_truth))
    out["arms"] = arms
    return out


def _rep_scores(result: Mapping[str, Any], methods, defaults, labels_truth) -> dict[str, Any]:
    selection_path = result.get("selection")
    selection = read_json(selection_path) if selection_path and Path(selection_path).exists() else None
    tuned: dict[str, float] = {}
    fallback: list[str] = []
    for method in methods:
        entry = (selection or {}).get("methods", {}).get(method)
        path = _method_labels(entry)
        if path is None or entry.get("status") == "fallback_default":
            tuned[method] = defaults[method]
            fallback.append(method)
        else:
            tuned[method] = ari(read_labels(path), labels_truth)
    final = (selection or {}).get("final")
    fin = None
    if final:
        entry = selection["methods"].get(final["method"])
        fin = ari(read_labels(entry["labels"]), labels_truth)
    d1_terms = {m: tuned[m] - defaults[m] for m in methods}
    kept = [m for m in methods if m not in fallback]
    med = median(defaults.values()) if defaults else 0.0
    return {
        "status": result.get("status"),
        "chosen_k": (selection or {}).get("k", {}).get("chosen"),
        "k_source": (selection or {}).get("k", {}).get("source"),
        "in_stable_peaks": (selection or {}).get("k", {}).get("in_stable_peaks"),
        "final_method": final["method"] if final else None,
        "fin_ari": fin,
        "tuned_ari": tuned,
        "fallback_default": fallback,
        "D1": sum(d1_terms.values()) / len(d1_terms) if d1_terms else None,
        "D1_excluding_fallback": (sum(d1_terms[m] for m in kept) / len(kept)) if kept else None,
        "D1_m": d1_terms,
        "D2": (fin if fin is not None else 0.0) - med,
        "D2_median_fill": (fin if fin is not None else med) - med,
        "D3": (fin if fin is not None else 0.0) - (max(defaults.values()) if defaults else 0.0),
    }


def unit_means(scores: Mapping[str, Any], arm: str) -> dict[str, float | None]:
    """The arm's estimators averaged over its repetitions, and their spread."""
    reps = scores["arms"].get(arm) or []
    out: dict[str, float | None] = {}
    for key in ("D1", "D1_excluding_fallback", "D2", "D2_median_fill", "D3", "fin_ari"):
        values = [r[key] for r in reps if r.get(key) is not None]
        out[key] = sum(values) / len(values) if values else None
        out[key + "_rep_sd"] = (
            (sum((v - out[key]) ** 2 for v in values) / (len(values) - 1)) ** 0.5 if len(values) > 1 else None
        )
    return out


def evaluate(root: Path, uids: Iterable[str], truth: Truth) -> dict[str, Any]:
    per_unit = {uid: unit_scores(root, uid, truth) for uid in uids}
    summary: dict[str, Any] = {"units": per_unit, "estimators": {}}
    for arm in ARMS:
        means = {uid: unit_means(s, arm) for uid, s in per_unit.items() if s["arms"].get(arm)}
        if not means:
            continue
        summary["estimators"][arm] = {
            key: describe([m[key] for m in means.values() if m.get(key) is not None])
            for key in ("D1", "D1_excluding_fallback", "D2", "D2_median_fill", "D3", "fin_ari")
        }
    a1 = {uid: unit_means(s, "A1") for uid, s in per_unit.items() if s["arms"].get("A1")}
    for other in ("A2", "A3", "A6"):
        pairs = [a1[u]["fin_ari"] - unit_means(per_unit[u], other)["fin_ari"]
                 for u in a1 if per_unit[u]["arms"].get(other) and a1[u]["fin_ari"] is not None
                 and unit_means(per_unit[u], other)["fin_ari"] is not None]
        if pairs:
            summary["estimators"][f"A1-{other}"] = describe(pairs)
    d1 = summary["estimators"].get("A1", {}).get("D1", {})
    d2 = summary["estimators"].get("A1", {}).get("D2", {})
    if d1.get("n") and d2.get("n"):
        summary["stop_line"] = {
            "d1_t_upper": d1["t95"][1], "d2_t_upper": d2["t95"][1],
            "triggered": bool(d1["t95"][1] < 0 and d2["t95"][1] < 0),
        }
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--truth-map", type=Path, required=True)
    parser.add_argument("--units", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    truth = Truth(read_json(args.truth_map))
    document = evaluate(args.root, args.units, truth)
    write_json(args.output, document)
    print(json.dumps(document.get("estimators"), indent=1, default=str)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
