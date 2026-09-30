"""Read-only: within-K selection loss (probe trials only): best ARI at K minus panel-pick ARI at K."""
import sys, json
from pathlib import Path
from statistics import mean
sys.path.insert(0, "/workspace/dataset/private/zhouwg_data/OmicsClaw/docs/plans/0057-validation")
sys.path.insert(0, "/workspace/dataset/private/zhouwg_data/OmicsClaw")
from evaluate import Truth, read_labels, ari
from common import read_json
from omicsclaw.ensemble.tuning.scoring import KReference, score_trial
root = Path("/workspace/dataset/private/zhouwg_data/0057_runs/holdout_report/root")
truth = Truth(read_json(root / "truth_map.json"))
scores = json.load(open("/workspace/dataset/private/zhouwg_data/0057_runs/holdout_report/analysis.json"))["scores"]
out = {}
for uid in sorted(scores):
    tl = truth.labels(uid)
    ref = read_json(root/uid/"probe"/"ws"/"ensemble_runs"/f"{uid}-probe"/"evidence"/"reference.json")
    byk = {}
    for tj in root.glob(f"{uid}/probe/ws/ensemble_runs/{uid}-probe/*/t*/trial.json"):
        mf, lf = tj.parent/"metrics.json", tj.parent/"labels.csv.gz"
        if not mf.is_file() or not lf.is_file(): continue
        m = read_json(mf); k = m.get("n_labels")
        pk = ref["per_k"].get(str(k)) if k else None
        if not pk: continue
        s = score_trial(m, KReference.from_json(pk)).score
        if s is None: continue
        byk.setdefault(k, []).append((s, ari(read_labels(lf), tl)))
    loss = {k: (max(a for _, a in v) - max(v)[1], len(v)) for k, v in byk.items() if len(v) >= 3 and 3 <= k <= 12}
    out[uid] = {str(k): v for k, v in loss.items()}
    print(uid, {k: (round(l, 3), n) for k, (l, n) in sorted(loss.items())}, flush=True)
Path("/workspace/dataset/private/zhouwg_data/0057_runs/holdout_report/posthoc/withink.json").write_text(json.dumps(out))
