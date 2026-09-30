"""The one development-stage panel comparison (plan §4.6 item 3): N1 range-normalised vs N2 within-group rank.

On each development unit, every ok full-input trial (probe and every
deterministic arm, duplicates by label fingerprint removed) is grouped by its
exact number of labels. In each group of at least two trials, N1 picks the
highest range-normalised fixed-K score (reference from the probe), N2 the
best mean within-group rank of corrected PAS and raw silhouette. Regret is the
group's best ARI minus the picked trial's ARI. N2 replaces N1 only if its mean
regret over all groups is strictly smaller on every unit. Groups of one method
at one K with different parameters are reported separately, for information.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import REPO, read_json, write_json  # noqa: E402
from evaluate import Truth, ari, read_labels  # noqa: E402

sys.path.insert(0, str(REPO))


def _fingerprint(path: Path) -> str:
    labels = read_labels(path)
    names: dict[str, int] = {}
    digest = hashlib.sha256()
    for obs in sorted(labels):
        digest.update(f"{obs}\t{names.setdefault(labels[obs], len(names))}\n".encode())
    return digest.hexdigest()


def trials(root: Path, uid: str) -> list[dict]:
    """Every ok full-input trial of the unit with its metrics, labels and method."""
    out = []
    runs = [root / uid / "probe" / "ws" / "ensemble_runs" / f"{uid}-probe"]
    runs += sorted((root / uid).glob("A[126]/r*/ws/ensemble_runs/*-a*-r*"))
    seen = set()
    for run in runs:
        for trial_json in sorted(run.glob("*/t*/trial.json")):
            record = read_json(trial_json)
            metrics_file = trial_json.parent / "metrics.json"
            if record.get("status") != "ok" or not metrics_file.is_file():
                continue
            labels = trial_json.parent / "labels.csv.gz"
            key = (record["method"], _fingerprint(labels))
            if key in seen:
                continue
            seen.add(key)
            out.append({"method": record["method"], "params": record["params"], "labels": str(labels),
                        "metrics": read_json(metrics_file), "trial": f"{run.name}/{record['method']}/{trial_json.parent.name}"})
    return out


def compare(root: Path, uid: str, truth: Truth) -> dict:
    from omicsclaw.ensemble.tuning.scoring import KReference, member_values, score_trial

    reference = read_json(root / uid / "probe" / "ws" / "ensemble_runs" / f"{uid}-probe" / "evidence" / "reference.json")
    labels_truth = truth.labels(uid)
    items = trials(root, uid)
    for item in items:
        item["ari"] = ari(read_labels(item["labels"]), labels_truth)
        item["k"] = item["metrics"]["n_labels"]
        values = member_values(item["metrics"])
        item["pas"], item["sil"] = values["pas"][0], values["silhouette_pca"][0]
        per_k = reference["per_k"].get(str(item["k"]))
        item["n1"] = score_trial(item["metrics"], KReference.from_json(per_k)).score if per_k else None

    def regret(group, key):
        best = max(t["ari"] for t in group)
        chosen = max(group, key=key)
        return best - chosen["ari"], chosen["ari"] == best

    def n2_key(group):
        def rank(values):
            order = sorted(range(len(values)), key=lambda i: -values[i])
            ranks = [0.0] * len(values)
            for position, index in enumerate(order, start=1):
                ranks[index] = position
            return ranks
        pas = rank([t["pas"] if t["pas"] is not None else -9 for t in group])
        sil = rank([t["sil"] if t["sil"] is not None else -9 for t in group])
        mean = {id(t): (p + s) / 2 for t, p, s in zip(group, pas, sil)}
        return lambda t: -mean[id(t)]

    result = {}
    for scope in ("all", "same_method"):
        groups = {}
        for item in items:
            if item["n1"] is None:
                continue
            key = item["k"] if scope == "all" else (item["k"], item["method"])
            groups.setdefault(key, []).append(item)
        groups = {k: g for k, g in groups.items() if len(g) >= 2}
        n1 = [regret(g, lambda t: t["n1"]) for g in groups.values()]
        n2 = [regret(g, n2_key(g)) for g in groups.values()]
        result[scope] = {
            "groups": len(groups), "sizes": sorted(len(g) for g in groups.values()),
            "n1": {"mean_regret": sum(r for r, _ in n1) / len(n1) if n1 else None, "hits": sum(h for _, h in n1)},
            "n2": {"mean_regret": sum(r for r, _ in n2) / len(n2) if n2 else None, "hits": sum(h for _, h in n2)},
        }
    return {"uid": uid, "trials": len(items), **result}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--truth-map", type=Path, required=True)
    parser.add_argument("--units", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    truth = Truth(read_json(args.truth_map))
    per_unit = [compare(args.root, uid, truth) for uid in args.units]
    replace = all(
        u["all"]["n2"]["mean_regret"] is not None and u["all"]["n2"]["mean_regret"] < u["all"]["n1"]["mean_regret"]
        for u in per_unit
    )
    document = {"units": per_unit, "n2_replaces_n1": replace}
    write_json(args.output, document)
    print(json.dumps(document, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
