"""Read-only: post-hoc A0s / constant-K / LLM-K-without-search decomposition from probe trials."""
import sys, json
from pathlib import Path
from statistics import median, mean
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
    u = scores[uid]
    tl = truth.labels(uid)
    ref = read_json(root/uid/"probe"/"ws"/"ensemble_runs"/f"{uid}-probe"/"evidence"/"reference.json")
    pick = {}
    for tj in root.glob(f"{uid}/probe/ws/ensemble_runs/{uid}-probe/*/t*/trial.json"):
        mf, lf = tj.parent/"metrics.json", tj.parent/"labels.csv.gz"
        if not mf.is_file() or not lf.is_file(): continue
        m = read_json(mf); k = m.get("n_labels")
        pk = ref["per_k"].get(str(k)) if k else None
        if not pk: continue
        s = score_trial(m, KReference.from_json(pk)).score
        if s is None: continue
        if k not in pick or s > pick[k][0]:
            pick[k] = (s, lf)
    pa = {k: ari(read_labels(lf), tl) for k, (s, lf) in pick.items()}
    arms = u["arms"]
    def at(k): return pa.get(k)
    a6k = [r["chosen_k"] for r in arms.get("A6", [])]
    a1k = [r["chosen_k"] for r in arms.get("A1", [])]
    rec = dict(k_star=u["k_star"], median_def=u["median_def"], max_def=u["max_def"],
               A1_fin=mean([r["fin_ari"] for r in arms["A1"] if r["fin_ari"] is not None]),
               A6_fin=mean([r["fin_ari"] for r in arms["A6"] if r["fin_ari"] is not None]),
               A0s=mean([at(k) for k in a6k if at(k) is not None]) if any(at(k) is not None for k in a6k) else None,
               A1_noSearch=mean([at(k) for k in a1k if at(k) is not None]) if any(at(k) is not None for k in a1k) else None,
               at_kstar=at(u["k_star"]), const={str(k): at(k) for k in (3,4,5,6,7,8)},
               probe_best_k=max(pa, key=pa.get) if pa else None)
    out[uid] = rec
    print(uid, json.dumps({k:(round(v,3) if isinstance(v,float) else v) for k,v in rec.items() if k!='const'}), flush=True)
Path("/workspace/dataset/private/zhouwg_data/0057_runs/holdout_report/posthoc/decomp.json").write_text(json.dumps(out, indent=1))
