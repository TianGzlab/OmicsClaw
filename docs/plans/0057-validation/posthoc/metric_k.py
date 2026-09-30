"""Read-only: per-K metric optima on DLPFC hold-out trials (probe-only and all)."""
import sys, json, gzip
from pathlib import Path
from collections import defaultdict
import numpy as np
sys.path.insert(0, "/workspace/dataset/private/zhouwg_data/OmicsClaw/docs/plans/0057-validation")
sys.path.insert(0, "/workspace/dataset/private/zhouwg_data/OmicsClaw")
from evaluate import Truth, read_labels
from common import read_json
from omicsclaw.ensemble.tuning.scoring import KReference, score_trial
from sklearn.metrics import adjusted_rand_score as ARI, adjusted_mutual_info_score as AMI, normalized_mutual_info_score as NMI, homogeneity_completeness_v_measure as HCV

root = Path("/workspace/dataset/private/zhouwg_data/0057_runs/holdout_report/root")
truth = Truth(read_json(root / "truth_map.json"))

def macro_f1(pred, true):
    # for each truth class: best F1 over predicted clusters; macro average
    pc = defaultdict(set); tc = defaultdict(set)
    for i,(p,t) in enumerate(zip(pred,true)): pc[p].add(i); tc[t].add(i)
    f=[]
    for t,ts in tc.items():
        best=0
        for p,ps in pc.items():
            inter=len(ts&ps)
            if inter==0: continue
            prec=inter/len(ps); rec=inter/len(ts); best=max(best,2*prec*rec/(prec+rec))
        f.append(best)
    return float(np.mean(f))

out={}
for uid in [f"u{i:02d}" for i in range(1,11)]:
    tl = truth.labels(uid)
    ref = read_json(root/uid/"probe"/"ws"/"ensemble_runs"/f"{uid}-probe"/"evidence"/"reference.json")
    groups = {"probe": list(root.glob(f"{uid}/probe/ws/ensemble_runs/{uid}-probe/*/t*/trial.json")),
              "all": [*root.glob(f"{uid}/probe/ws/ensemble_runs/{uid}-probe/*/t*/trial.json"),
                      *root.glob(f"{uid}/A*/r*/ws/ensemble_runs/{uid}-a*-r*/*/t*/trial.json")]}
    res={}
    cache={}
    for gname, trials in groups.items():
        best=defaultdict(lambda: defaultdict(lambda:-9)); pick={}; ntr=defaultdict(int)
        seen=set()
        for tj in trials:
            key=(tj.parts[-4],tj.parts[-3],tj.parts[-2])
            if key in seen: continue
            seen.add(key)
            mf, lf = tj.parent/"metrics.json", tj.parent/"labels.csv.gz"
            if not mf.is_file() or not lf.is_file(): continue
            m=read_json(mf); k=m.get("n_labels")
            if not k or not (3<=k<=14): continue
            if lf not in cache:
                lab=read_labels(lf)
                obs=[o for o in lab if o in tl]
                p=[lab[o] for o in obs]; t=[tl[o] for o in obs]
                h,c,v=HCV(t,p)
                cache[lf]=dict(ari=ARI(t,p), ami=AMI(t,p), nmi=NMI(t,p), hom=h, com=c, mf1=macro_f1(p,t))
            sc=cache[lf]; ntr[k]+=1
            for mname,val in sc.items(): best[mname][k]=max(best[mname][k],val)
            pk=ref["per_k"].get(str(k))
            if pk:
                s=score_trial(m, KReference.from_json(pk)).score
                if s is not None and (k not in pick or s>pick[k][0]): pick[k]=(s,sc)
        res[gname]=dict(
            argmax_k={mn:max(bk,key=bk.get) for mn,bk in best.items()},
            pick_by_k={k:{mn:round(v,3) for mn,v in pick[k][1].items()} for k in sorted(pick)},
            n_trials={k:ntr[k] for k in sorted(ntr)})
    k_star=len(set(tl.values()))
    out[uid]=dict(k_star=k_star, **res)
    print(uid, k_star, "probe argmax", res["probe"]["argmax_k"], "all argmax", res["all"]["argmax_k"], flush=True)
Path("/workspace/dataset/private/zhouwg_data/0057_runs/holdout_report/posthoc/metric_k.json").write_text(json.dumps(out,indent=1))
