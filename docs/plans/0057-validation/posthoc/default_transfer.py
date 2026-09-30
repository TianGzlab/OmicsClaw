"""Read-only: would a fixed new default have captured the per-dataset search gain? Hold-out data, post hoc.

``default_transfer.py [--root R] [--analysis A] [--output O] [--workers N]``

Every deterministic run (A1, A2, A6) already evaluated, at its chosen K, the
grid of leiden ``spatial_weight`` and cellcharter ``n_layers`` and the three
single-parameter sweep points of spagcn and graphst. For each such fixed value
this script takes ``ARI(value@K) - ARI(default@K)``, averages it over a unit's
runs and then over the units of a group (DLPFC, CosMx slide 1, slide 2, K*=2
blocks). It then picks, per method, the value with the best mean gain on one
group and reports its gain on the others, next to the search's own within-K
gain (the panel's choice) and the within-K ceiling (best trial by ARI), the
last two on the same runs in which the fixed value reached K.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from autoagent_value import GROUPS, GROUP_OF, REPORT, Scorer, labels_path  # noqa: E402
from evaluate import Truth, read_labels, describe  # noqa: E402
from common import read_json  # noqa: E402

FIXED = {
    "leiden": ("grid", lambda p: f"spatial_weight={p.get('spatial_weight')}"),
    "cellcharter": ("grid", lambda p: f"n_layers={p.get('n_layers')}"),
    "graphst": ("stage1", lambda p: f"epochs={p.get('epochs')},dim_output={p.get('dim_output')}"),
    "spagcn": ("stage1", lambda p: f"spagcn_p={p.get('spagcn_p')},epochs={p.get('epochs')}"),
}


def work(args):
    root, uid, truth, unit = args
    score = Scorer(truth)
    per_value = defaultdict(list)   # (method, value) -> (gain, search gain, ceiling) over the unit's runs with that value at K
    search = defaultdict(list)      # method -> (within_k, ceiling)
    for arm in ("A1", "A2", "A6"):
        for i, rep_dir in enumerate(sorted((root / uid / arm).glob("r*"))):
            run_id = f"{uid}-{arm.lower()}-{rep_dir.name}"
            ws = rep_dir / "ws"
            ledger = [json.loads(l) for l in open(ws / "ensemble_runs" / run_id / "tuning" / "ledger.jsonl")]
            k = read_json(ws / "ensemble_runs" / run_id / "tuning" / "selection.json")["k"]["chosen"]
            trials = [e for e in ledger if e["kind"] == "trial" and e["status"] == "ok" and e.get("n_labels") == k]
            for m, (stage, key) in FIXED.items():
                if m not in unit["default_ari"]:
                    continue
                at_k = [t for t in trials if t["method"] == m]
                base = next((t for t in at_k if t["stage"] == "baseline"), None)
                if base is None:
                    continue
                b = score(labels_path(root, uid, ws, base["run_id"], m, base["trial"]))
                seen = {}
                for t in at_k:
                    if t["stage"] != stage or (stage == "stage1" and t["source"] != "sweep"):
                        continue
                    v = key(t["params"])
                    if v not in seen:
                        seen[v] = score(labels_path(root, uid, ws, t["run_id"], m, t["trial"])) - b
                tun = unit["arms"][arm][i]["tuned_ari"].get(m)
                ceiling = max(score(labels_path(root, uid, ws, t["run_id"], m, t["trial"])) for t in at_k) - b
                if tun is None:
                    continue
                search[m].append((tun - b, ceiling))
                for v, g in seen.items():
                    per_value[(m, v)].append((g, tun - b, ceiling))
    return uid, {f"{m}|{v}": [mean(x[j] for x in xs) for j in range(3)] for (m, v), xs in per_value.items()}, \
        {m: (mean(a for a, _ in xs), mean(c for _, c in xs)) for m, xs in search.items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=REPORT / "root")
    ap.add_argument("--analysis", type=Path, default=REPORT / "analysis.json")
    ap.add_argument("--output", type=Path, default=REPORT / "posthoc" / "default_transfer.json")
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args(argv)
    truth = Truth(read_json(a.root / "truth_map.json"))
    scores = read_json(a.analysis)["scores"]
    jobs = []
    for uid in sorted(scores):
        probe = read_json(a.root / uid / "probe" / "result.json")
        unit_obs = next(iter(read_labels(a0["labels"]) for a0 in probe["a0"].values() if a0 and a0.get("status") == "ok"))
        jobs.append((a.root, uid, {o: v for o, v in truth.labels(uid).items() if o in unit_obs}, scores[uid]))
    values, search = {}, {}
    with ProcessPoolExecutor(a.workers) as pool:
        for uid, v, s in pool.map(work, jobs):
            values[uid], search[uid] = v, s
    groups = ("DLPFC", "slide1", "slide2", "single")
    table = {}
    for m in FIXED:
        keys = sorted({k for u in values.values() for k in u if k.startswith(m + "|")})
        for g in groups:
            for k in keys:
                table.setdefault(k, {})[g] = describe([values[u][k][0] for u in GROUPS[g] if k in values[u]])
            table.setdefault(f"{m}|<search>", {})[g] = describe([search[u][m][0] for u in GROUPS[g] if m in search[u]])
            table.setdefault(f"{m}|<ceiling>", {})[g] = describe([search[u][m][1] for u in GROUPS[g] if m in search[u]])
    transfer = {}
    for m in FIXED:
        keys = [k for k in table if k.startswith(m + "|") and "<" not in k]
        for g_from in groups:
            best = max(keys, key=lambda k: table[k][g_from].get("mean", float("-inf")))
            transfer[f"{m}|from:{g_from}"] = {
                "value": best,
                **{g: table[best][g].get("mean") for g in groups},
                "matched_runs": {g: {"units": len(us), "fixed": mean(values[u][best][0] for u in us),
                                     "search": mean(values[u][best][1] for u in us),
                                     "ceiling": mean(values[u][best][2] for u in us)}
                                 for g in groups for us in [[u for u in GROUPS[g] if best in values[u]]] if us}}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps({"table": table, "transfer": transfer, "per_unit": values, "search": search},
                                   indent=1, default=str))
    for k, row in table.items():
        print(k, {g: (round(row[g]["mean"], 3), row[g]["n"]) if row[g].get("n") else None for g in groups})
    for k, row in transfer.items():
        print(k, row["value"], {g: {kk: round(vv, 3) for kk, vv in r.items()} for g, r in row["matched_runs"].items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
