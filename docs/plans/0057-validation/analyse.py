"""All hold-out estimators and descriptive tables of the 0057 report (plan §4.4–§4.7), as one JSON document.

``analyse.py --root <root> --output analysis.json``. Reads ``holdout_map.json``
(dataset, slice / slide, population), ``truth_map.json`` and every unit's
results. Groups: DLPFC (the primary estimators and the stop line), DLPFC by
donor and without Br8100, the DLPFC K* = 5 and K* = 7 groups (J1), CosMx
primary per slide with a slide-stratified mean, CosMx K* = 2 blocks, and the
CosMx subset where K* >= 3 on both definitions.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ARMS, read_json, write_json  # noqa: E402
from evaluate import Truth, ari, describe, read_labels, unit_means, unit_scores  # noqa: E402

DONORS = {"151507": "Br5292", "151508": "Br5292", "151509": "Br5292", "151510": "Br5292",
          "151669": "Br5595", "151670": "Br5595", "151671": "Br5595", "151672": "Br5595",
          "151673": "Br8100", "151674": "Br8100", "151675": "Br8100", "151676": "Br8100"}
ESTIMATORS = ("D1", "D1_excluding_fallback", "D2", "D2_median_fill", "D3", "fin_ari")
BOOT_SEED = 20260926


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def group_estimators(scores: dict[str, Any], uids: Iterable[str]) -> dict[str, Any]:
    uids = [u for u in uids if u in scores]
    out: dict[str, Any] = {"units": uids}
    for arm in ARMS:
        means = [unit_means(scores[u], arm) for u in uids if scores[u]["arms"].get(arm)]
        if means:
            out[arm] = {key: describe([m[key] for m in means if m.get(key) is not None]) for key in ESTIMATORS}
            out[arm]["rep_sd_median"] = {
                key: _median([m.get(key + "_rep_sd") for m in means]) for key in ("D1", "D2")
            }
    for other in ("A2", "A3", "A6"):
        pairs = []
        for u in uids:
            a, b = unit_means(scores[u], "A1")["fin_ari"], unit_means(scores[u], other)["fin_ari"]
            if a is not None and b is not None:
                pairs.append(a - b)
        if pairs:
            out[f"A1-{other}"] = describe(pairs)
    a0k = [(unit_means(scores[u], "A1"), scores[u]) for u in uids]
    diffs = []
    for means, s in a0k:
        reps = s["arms"].get("A1") or []
        tuned = _mean([r["tuned_ari"].get("cellcharter") for r in reps])
        if tuned is not None and (s.get("a0k") or {}).get("ari") is not None:
            diffs.append(tuned - s["a0k"]["ari"])
    if diffs:
        out["A1_cellcharter-A0k"] = describe(diffs)
    return out


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def stop_line(block: dict[str, Any]) -> dict[str, Any] | None:
    a1 = block.get("A1") or {}
    d1, d2 = a1.get("D1") or {}, a1.get("D2") or {}
    if not d1.get("n") or not d2.get("n"):
        return None
    return {"d1_t95": d1["t95"], "d2_t95": d2["t95"], "d1_bca95": d1["bca95"], "d2_bca95": d2["bca95"],
            "triggered": bool(d1["t95"][1] < 0 and d2["t95"][1] < 0)}


def stratified(scores, slides: dict[str, list[str]], arm: str = "A1", key: str = "D2", n_boot: int = 10_000):
    """Slide-weighted mean of *key* and a bootstrap interval resampling units within each slide."""
    import numpy as np

    per = {s: [unit_means(scores[u], arm)[key] for u in us if scores.get(u) and scores[u]["arms"].get(arm)]
           for s, us in slides.items()}
    per = {s: [v for v in vs if v is not None] for s, vs in per.items() if vs}
    if not per:
        return None
    rng = np.random.default_rng(BOOT_SEED)
    point = float(np.mean([np.mean(v) for v in per.values()]))
    draws = [float(np.mean([np.mean(rng.choice(v, size=len(v), replace=True)) for v in per.values()]))
             for _ in range(n_boot)]
    return {"mean": point, "ci95": [float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))],
            "per_slide": {s: float(np.mean(v)) for s, v in per.items()}}


def k_choice(scores, uids, stable: dict[str, list[int]]) -> dict[str, Any]:
    out = {}
    for arm in ("A1", "A2", "A6", "A3"):
        reps = [(u, r) for u in uids for r in (scores[u]["arms"].get(arm) or [])]
        if not reps:
            continue
        chosen = [r["chosen_k"] for _, r in reps if r["chosen_k"] is not None]
        in_peaks = [r["chosen_k"] in stable.get(u, []) for u, r in reps if r["chosen_k"] is not None]
        chance = _mean([len(stable.get(u, [])) / 14 for u, _ in reps])
        out[arm] = {
            "n": len(reps), "share_7": sum(k == 7 for k in chosen) / len(chosen) if chosen else None,
            "distribution": {str(k): chosen.count(k) for k in sorted(set(chosen))},
            "share_in_stable_peaks": sum(in_peaks) / len(in_peaks) if in_peaks else None,
            "chance_share": chance,
            "abs_k_error_mean": _mean([abs(r["chosen_k"] - scores[u]["k_star"]) for u, r in reps if r["chosen_k"]]),
            "D1_given_k7": _mean([r["D1"] for _, r in reps if r["chosen_k"] == 7]),
            "sources": {s: sum(r["k_source"] == s for _, r in reps) for s in {r["k_source"] for _, r in reps}},
        }
    return out


def unit_descriptive(root: Path, uid: str, truth_labels: dict[str, str], chosen_ks: list[int]) -> dict[str, Any]:
    """Regret against the best trial of all arms (and of the probe only), and Spearman rho at the chosen K."""
    from scipy.stats import spearmanr

    from omicsclaw.ensemble.tuning.scoring import KReference, score_trial

    best_all = best_probe = -math.inf
    reference = read_json(root / uid / "probe" / "ws" / "ensemble_runs" / f"{uid}-probe" / "evidence" / "reference.json")
    at_k: dict[int, list[tuple[float, float]]] = {}
    seen = set()
    trials = [*root.glob(f"{uid}/probe/ws/ensemble_runs/{uid}-probe/*/t*/trial.json"),
              *root.glob(f"{uid}/A*/r*/ws/ensemble_runs/{uid}-a*-r*/*/t*/trial.json")]
    for trial_json in trials:
        key = (trial_json.parts[-4], trial_json.parts[-3], trial_json.parts[-2])
        if key in seen:
            continue
        seen.add(key)
        metrics_file = trial_json.parent / "metrics.json"
        labels_file = trial_json.parent / "labels.csv.gz"
        if not metrics_file.is_file() or not labels_file.is_file():
            continue
        value = ari(read_labels(labels_file), truth_labels)
        best_all = max(best_all, value)
        if trial_json.parts[-4].endswith("-probe"):
            best_probe = max(best_probe, value)
        metrics = read_json(metrics_file)
        k = metrics.get("n_labels")
        per_k = reference["per_k"].get(str(k))
        if k in chosen_ks and per_k:
            scored = score_trial(metrics, KReference.from_json(per_k))
            if scored.score is not None:
                at_k.setdefault(k, []).append((scored.score, value))
    rho = {}
    for k, pairs in at_k.items():
        if len(pairs) >= 5:
            rho[str(k)] = {"n": len(pairs), "rho": float(spearmanr([p[0] for p in pairs], [p[1] for p in pairs])[0])}
    return {"oracle": best_all if best_all > -math.inf else None,
            "oracle_probe": best_probe if best_probe > -math.inf else None, "spearman_at_chosen_k": rho}


def search_sources(root: Path, uid: str) -> dict[str, Any]:
    counts: dict[str, int] = {}
    skipped = total = 0
    for arm in ("A1", "A2", "A6"):
        for tuning in root.glob(f"{uid}/{arm}/r*/ws/ensemble_runs/*/tuning/tuning.json"):
            record = read_json(tuning)["tuning_record"]["methods"]
            selection = read_json(tuning.parent / "selection.json")
            for method, entry in record.items():
                if entry.get("strategy") == "two_stage":
                    total += 1
                    skipped += bool(entry.get("stage2_skipped"))
            for method, entry in selection["methods"].items():
                source = entry.get("source") or "failed"
                counts[source] = counts.get(source, 0) + 1
    return {"final_sources": counts, "stage2_skipped": skipped, "two_stage": total}


def analyse(root: Path) -> dict[str, Any]:
    mapping = read_json(root / "holdout_map.json")
    truth = Truth(read_json(root / "truth_map.json"))
    uids = [u for u in read_json(root / "units.json") if (root / u / "probe" / "result.json").exists()]
    scores = {u: unit_scores(root, u, truth) for u in uids}
    dlpfc = [u for u in uids if mapping[u]["dataset"] == "DLPFC"]
    cosmx = [u for u in uids if mapping[u]["dataset"] == "CosMx"]
    stable = {u: read_json(root / u / "probe" / "result.json")["stable_peaks"] for u in uids}
    out: dict[str, Any] = {"scores": scores, "groups": {}}
    groups = out["groups"]
    groups["DLPFC"] = group_estimators(scores, dlpfc)
    groups["DLPFC"]["stop_line"] = stop_line(groups["DLPFC"])
    groups["DLPFC_without_Br8100"] = group_estimators(scores, [u for u in dlpfc if DONORS[mapping[u]["slice"]] != "Br8100"])
    for donor in sorted(set(DONORS.values())):
        groups[f"DLPFC_{donor}"] = group_estimators(scores, [u for u in dlpfc if DONORS[mapping[u]["slice"]] == donor])
    for k in sorted({scores[u]["k_star"] for u in dlpfc}):
        members = [u for u in dlpfc if scores[u]["k_star"] == k]
        groups[f"DLPFC_Kstar{k}"] = group_estimators(scores, members)
        groups[f"DLPFC_Kstar{k}"]["k_choice"] = k_choice(scores, members, stable)
    primary = {s: [u for u in cosmx if mapping[u].get("population") == "primary" and mapping[u]["slide"] == s]
               for s in sorted({mapping[u]["slide"] for u in cosmx})}
    for slide, members in primary.items():
        groups[f"CosMx_slide{slide}_primary"] = group_estimators(scores, members)
        groups[f"CosMx_slide{slide}_primary"]["k_choice"] = k_choice(scores, members, stable)
    groups["CosMx_primary_stratified"] = {key: stratified(scores, primary, key=key) for key in ("D1", "D2")}
    both = [u for u in cosmx if mapping[u].get("population") == "primary" and scores[u]["k_star_5pct"] >= 3]
    groups["CosMx_primary_both_definitions"] = group_estimators(scores, both)
    single = [u for u in cosmx if mapping[u].get("population") == "single"]
    groups["CosMx_single_Kstar2"] = {
        "blocks": {u: {"slide": mapping[u]["slide"], "fov": mapping[u]["fov"],
                       **{arm: unit_means(scores[u], arm) for arm in ARMS}} for u in single},
        "median_D2_A1": _median([unit_means(scores[u], "A1")["D2"] for u in single]),
    }
    for definition in ("k_star", "k_star_5pct"):
        by_k: dict[str, Any] = {}
        for k in sorted({scores[u][definition] for u in cosmx}):
            members = [u for u in cosmx if scores[u][definition] == k]
            by_k[str(k)] = k_choice(scores, members, stable)
        groups[f"CosMx_k_choice_by_{definition}"] = by_k
    k5 = groups.get("DLPFC_Kstar5", {}).get("k_choice", {})
    share = lambda arm: (k5.get(arm) or {}).get("share_7")  # noqa: E731
    out["j1"] = {"A1_share7_Kstar5": share("A1"), "A6_share7_Kstar5": share("A6"),
                 "triggered": share("A1") is not None and share("A6") is not None and share("A1") >= share("A6")}
    descriptive = {}
    for u in uids:
        chosen = [r["chosen_k"] for arm in ARMS for r in (scores[u]["arms"].get(arm) or []) if r["chosen_k"]]
        truth_labels = {o: v for o, v in truth.labels(u).items()}
        d = unit_descriptive(root, u, truth_labels, sorted(set(chosen)))
        fins = [r["fin_ari"] for r in (scores[u]["arms"].get("A1") or []) if r["fin_ari"] is not None]
        d["regret_A1"] = (d["oracle"] - _mean(fins)) if fins and d["oracle"] is not None else None
        d["regret_A1_probe_oracle"] = (d["oracle_probe"] - _mean(fins)) if fins and d["oracle_probe"] is not None else None
        d["search"] = search_sources(root, u)
        descriptive[u] = d
    out["descriptive"] = descriptive
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    document = analyse(args.root)
    write_json(args.output, document)
    print(json.dumps({"stop_line": document["groups"]["DLPFC"].get("stop_line"), "j1": document["j1"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
