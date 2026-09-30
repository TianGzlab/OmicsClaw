"""How much a method's fixed-K score moves between seeds, against its standard error (development only).

For each unit and method, the default-parameter trial (K = the method's
default for exact methods, resolution 1.0 for calibrated ones) is run under
seeds 1..N in addition to the probe's seed-0 trial, and the spread of the
fixed-K score (reference: the probe's) is compared with the median single-
partition standard error. Also reports the pairwise ARI between seeds.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import REPO, RUNNABLE, make_pool, make_runner, read_json, write_json  # noqa: E402
from evaluate import read_labels  # noqa: E402

SKILL = "spatial-domains"


async def spread(root: Path, uid: str, seeds: range, pool) -> dict:
    from sklearn.metrics import adjusted_rand_score

    from omicsclaw.ensemble.tuning.scoring import KReference, score_trial

    probe = read_json(root / uid / "probe" / "result.json")
    reference = read_json(root / uid / "probe" / "ws" / "ensemble_runs" / f"{uid}-probe" / "evidence" / "reference.json")
    source = root / uid / "probe" / "ws" / "data" / "input.h5ad"
    out = {}
    jobs = []
    for seed in seeds:
        runner = make_runner(root / uid / "seed_spread" / f"s{seed}", pool, seed=seed)
        for method in RUNNABLE:
            params = {k: v for k, v in probe["a0"][method]["params"].items()}
            spec = runner.prepare(skill=SKILL, method=method, input=source, params=params, run_id=f"{uid}-seed{seed}")
            jobs.append((seed, method, runner.run(spec)))
    results = await asyncio.gather(*(job for _, _, job in jobs))
    by_method: dict[str, list] = {m: [] for m in RUNNABLE}
    for (seed, method, _), result in zip(jobs, results):
        by_method[method].append((seed, result))
    for method in RUNNABLE:
        a0 = probe["a0"][method]
        k = a0["n_labels"]
        labels = [read_labels(a0["labels"])]
        metrics0 = read_json(Path(a0["labels"]).parent / "metrics.json")
        rows = [(0, metrics0)]
        for seed, result in by_method[method]:
            if result.status == "ok":
                rows.append((seed, result.metrics))
                labels.append(read_labels(Path(result.output_dir) / "labels.csv.gz"))
        scores, ses, ks = [], [], []
        for _, metrics in rows:
            ks.append(metrics["n_labels"])
            per_k = reference["per_k"].get(str(metrics["n_labels"]))
            if metrics["n_labels"] == k and per_k:
                scored = score_trial(metrics, KReference.from_json(per_k))
                if scored.score is not None:
                    scores.append(scored.score)
                    ses.append(scored.se)
        aris = []
        for a, b in itertools.combinations(labels, 2):
            common = [key for key in a if key in b]
            aris.append(adjusted_rand_score([a[x] for x in common], [b[x] for x in common]))
        sd = statistics.stdev(scores) if len(scores) > 1 else None
        se = statistics.median(ses) if ses else None
        out[method] = {"n_seeds": len(rows), "n_labels": ks, "scores": scores, "sd": sd, "median_se": se,
                       "sd_over_se": sd / se if sd is not None and se else None,
                       "pairwise_ari_median": statistics.median(aris) if aris else None,
                       "pairwise_ari_min": min(aris) if aris else None}
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--units", nargs="+", required=True)
    parser.add_argument("--seeds", type=int, default=4, help="extra seeds 1..N")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    pool = make_pool()

    async def run():
        return {uid: await spread(args.root, uid, range(1, args.seeds + 1), pool) for uid in args.units}

    document = asyncio.run(run())
    ratios = [m["sd_over_se"] for u in document.values() for m in u.values() if m["sd_over_se"] is not None]
    document["summary"] = {"sd_over_se_median": statistics.median(ratios) if ratios else None, "n": len(ratios)}
    write_json(args.output, document)
    print(json.dumps(document["summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
