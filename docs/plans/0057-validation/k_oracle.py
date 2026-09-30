"""Per-K ARI ceiling on the DLPFC hold-out units: ``k_oracle.py --root <report root> --analysis analysis.json --output k_oracle.json``.

For every unit and every K it reports the best ARI over all trials (probe and
arms) and the ARI of the trial the fixed-K panel ranks first. ``--root`` is the
report root that holds ``truth_map.json`` and the unit directories.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate import Truth, read_labels, ari
from common import read_json
from omicsclaw.ensemble.tuning.scoring import KReference, score_trial

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--analysis", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = args.root
truth = Truth(read_json(root / "truth_map.json"))
scores = json.load(open(args.analysis))["scores"]
out = {}
for uid in [f"u{i:02d}" for i in range(1, 11)]:
    tl = truth.labels(uid)
    ref = read_json(root / uid / "probe" / "ws" / "ensemble_runs" / f"{uid}-probe" / "evidence" / "reference.json")
    trials = [*root.glob(f"{uid}/probe/ws/ensemble_runs/{uid}-probe/*/t*/trial.json"),
              *root.glob(f"{uid}/A*/r*/ws/ensemble_runs/{uid}-a*-r*/*/t*/trial.json")]
    best = defaultdict(lambda: -1.0); pick = {}
    seen = set()
    for tj in trials:
        key = (tj.parts[-4], tj.parts[-3], tj.parts[-2])
        if key in seen: continue
        seen.add(key)
        mf, lf = tj.parent / "metrics.json", tj.parent / "labels.csv.gz"
        if not mf.is_file() or not lf.is_file(): continue
        m = read_json(mf); k = m.get("n_labels")
        if not k: continue
        v = ari(read_labels(lf), tl)
        best[k] = max(best[k], v)
        pk = ref["per_k"].get(str(k))
        if pk:
            s = score_trial(m, KReference.from_json(pk)).score
            if s is not None and (k not in pick or s > pick[k][0]):
                pick[k] = (s, v)
    u = scores[uid]
    a1 = [r["chosen_k"] for r in u["arms"].get("A1", [])]
    a1fin = [r["fin_ari"] for r in u["arms"].get("A1", []) if r["fin_ari"] is not None]
    a6 = [r["chosen_k"] for r in u["arms"].get("A6", [])]
    ks = sorted(k for k in best if 3 <= k <= 14)
    kbest = max(ks, key=lambda k: best[k])
    kpick = max((k for k in ks if k in pick), key=lambda k: pick[k][1])
    out[uid] = dict(k_star=u["k_star"], A1_k=a1, A6_k=a6, A1_fin=round(sum(a1fin)/len(a1fin),3),
                    oracle_k=kbest, oracle_ari=round(best[kbest],3),
                    panelpick_best_k=kpick, panelpick_best_ari=round(pick[kpick][1],3),
                    panelpick_at_kstar=round(pick.get(u["k_star"], (0, float('nan')))[1],3),
                    panelpick_by_k={k: round(pick[k][1],3) for k in ks if k in pick})
    print(uid, json.dumps(out[uid]), flush=True)
args.output.write_text(json.dumps(out, indent=1))
