"""Read-only: where the 0057 parameter search gains ARI on the hold-out, and what the LLM proposals add.

``autoagent_value.py [--root R] [--analysis A] [--output O] [--workers N]``

For every deterministic run (A1, A2, A6) and method it splits the per-method
gain ``D1_m = ARI(tun_m) - ARI(def_m)`` into a K part
``ARI(base_m@K) - ARI(def_m)`` and a within-K search part
``ARI(tun_m) - ARI(base_m@K)``, where ``base_m@K`` is the ledger's baseline
trial (default parameters at the chosen K). It also records the within-K
headroom (best ARI among the run's trials of that method at K minus the
baseline), the source of the chosen trial, the stage-1 proposals of the
two-stage methods (sweep, LLM, random) with their ARI gain and their
normalised distance from the defaults, and the parameters the final choice
changed. A3 runs get the same K / within-K split (baseline from the probe by
the pipeline's own ``default_trial`` rule) and a census of their ``run_skill``
parameters. Truth is read through ``truth_map.json`` only.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from statistics import mean, median

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from evaluate import Truth, read_labels, ari, describe  # noqa: E402
from common import read_json, RUNNABLE  # noqa: E402

REPORT = Path("/workspace/dataset/private/zhouwg_data/0057_runs/holdout_report")

GROUPS = {
    "DLPFC": [f"u{i:02d}" for i in range(1, 11)],
    "slide1": [f"c{i:02d}" for i in range(1, 13)],
    "slide2": [f"c{i:02d}" for i in range(17, 29)],
    "single": [f"c{i:02d}" for i in (13, 14, 15, 16, 29, 30, 31, 32)],
}
GROUP_OF = {u: g for g, us in GROUPS.items() for u in us}

# searched (non-K) parameters: kind, low, high, default
SPACE = {
    "leiden": {"spatial_weight": ("lin", 0.0, 0.9, 0.3)},
    "louvain": {"spatial_weight": ("lin", 0.0, 0.9, 0.3)},
    "cellcharter": {"n_layers": ("lin", 1, 5, 3)},
    "spagcn": {"spagcn_p": ("lin", 0.1, 0.9, 0.5), "epochs": ("log", 50, 400, 100)},
    "graphst": {"epochs": ("log", 50, 600, 100), "dim_output": ("cat", [32, 64, 128], None, 64)},
}
TWO_STAGE = ("spagcn", "graphst")
STAGE_LABEL = {"baseline": "baseline", "grid": "grid", "stage2": "neighbourhood"}
"""Chosen-trial label by stage; a calibration run counts as the point it calibrates, stage 1 keeps its source."""


def norm_dist(method: str, name: str, value) -> float:
    kind, lo, hi, default = SPACE[method][name]
    if value is None:
        value = default
    if kind == "lin":
        return abs(float(value) - default) / (hi - lo)
    if kind == "log":
        return abs(math.log(float(value)) - math.log(default)) / (math.log(hi) - math.log(lo))
    choices = lo
    return abs(choices.index(int(value)) - choices.index(default)) / (len(choices) - 1)


def deviation(method: str, params: dict) -> dict:
    d = {n: norm_dist(method, n, params.get(n)) for n in SPACE[method]}
    return {"per_param": d, "n_changed": sum(1 for v in d.values() if v > 1e-9),
            "linf": max(d.values()), "l1": sum(d.values())}


def spearman(xs, ys):
    from scipy.stats import spearmanr
    if len(xs) < 5 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    r = spearmanr(xs, ys).correlation
    return None if r != r else float(r)


class Scorer:
    def __init__(self, truth: dict):
        self.truth = truth
        self.cache: dict[str, float] = {}

    def __call__(self, path: Path) -> float | None:
        key = str(path)
        if key not in self.cache:
            self.cache[key] = ari(read_labels(path), self.truth) if path.is_file() else None
        return self.cache[key]


def labels_path(root: Path, uid: str, ws: Path, run_id: str, method: str, trial: str) -> Path:
    if run_id.endswith("-probe"):
        return root / uid / "probe" / "ws" / "ensemble_runs" / run_id / method / trial / "labels.csv.gz"
    return ws / "ensemble_runs" / run_id / method / trial / "labels.csv.gz"


def probe_trials(root: Path, uid: str) -> list[dict]:
    out = []
    base = root / uid / "probe" / "ws" / "ensemble_runs" / f"{uid}-probe"
    for tj in base.glob("*/t*/trial.json"):
        t = read_json(tj)
        mf = tj.parent / "metrics.json"
        n = read_json(mf).get("n_labels") if mf.is_file() else None
        out.append({"method": t["method"], "trial": t["trial"], "params": t.get("params", {}),
                    "status": t.get("status"), "n_labels": n, "labels": tj.parent / "labels.csv.gz"})
    return out


def probe_default_at_k(ptrials: list[dict], method: str, k: int) -> dict | None:
    """The pipeline's rule: exact methods, the trial run with K requested; calibrated, median resolution among K-label trials."""
    if method in ("leiden", "louvain"):
        at_k = sorted((t for t in ptrials if t["method"] == method and t["status"] == "ok" and t["n_labels"] == k),
                      key=lambda t: t["params"].get("resolution") or 0.0)
        return at_k[len(at_k) // 2] if at_k else None
    return next((t for t in ptrials if t["method"] == method and t["params"].get("n_domains") == k), None)


def det_run(root: Path, uid: str, arm: str, rep_dir: Path, score: Scorer, defaults: dict, rep_scores: dict) -> dict:
    run_id = f"{uid}-{arm.lower()}-{rep_dir.name}"
    ws = rep_dir / "ws"
    ledger = [json.loads(l) for l in open(ws / "ensemble_runs" / run_id / "tuning" / "ledger.jsonl")]
    selection = read_json(ws / "ensemble_runs" / run_id / "tuning" / "selection.json")
    k = selection["k"]["chosen"]
    trials = [e for e in ledger if e["kind"] == "trial"]
    skipped = {e["method"]: e.get("skipped") for e in ledger if e["kind"] == "stage" and e.get("stage") == "stage2"}
    llm_usage = defaultdict(lambda: Counter())
    for e in ledger:
        if e["kind"] == "llm_call":
            p = e["purpose"].split(":")[0]
            llm_usage[p]["calls"] += 1
            llm_usage[p]["latency_s"] += e.get("latency_s") or 0
            for key, val in (e.get("usage") or {}).items():
                llm_usage[p][key] += val or 0
    out = {"uid": uid, "arm": arm, "rep": rep_dir.name, "k": k, "k_star": None, "methods": {},
           "llm_usage": {p: dict(c) for p, c in llm_usage.items()}}
    for m in defaults:
        sel = selection["methods"].get(m) or {}
        at_k = [t for t in trials if t["method"] == m and t["status"] == "ok" and t.get("n_labels") == k]
        for t in at_k:
            t["_ari"] = score(labels_path(root, uid, ws, t["run_id"], m, t["trial"]))
        base = next((t for t in at_k if t["stage"] == "baseline"), None)
        chosen = next((t for t in at_k if t["run_id"] == sel.get("run_id") and t["trial"] == sel.get("trial")), None)
        tun = rep_scores["tuned_ari"].get(m)
        rec = {"def": defaults[m], "tun": tun, "status": sel.get("status"),
               "base": base["_ari"] if base else None,
               "chosen_source": (STAGE_LABEL.get(chosen["stage"]) or chosen["source"]) if chosen
               else ("fallback" if sel.get("status") == "fallback_default" else None),
               "chosen_stage": chosen["stage"] if chosen else None,
               "n_at_k": len(at_k)}
        if base is not None and tun is not None:
            rec["k_part"] = base["_ari"] - defaults[m]
            rec["within_k"] = tun - base["_ari"]
            valid = [t["_ari"] for t in at_k if t["_ari"] is not None]
            rec["headroom"] = max(valid) - base["_ari"]
            scored = [t for t in at_k if t.get("fixed_k_score") is not None and t["_ari"] is not None]
            if scored:
                top = max(scored, key=lambda t: t["fixed_k_score"])
                rec["argmax_score_gain"] = top["_ari"] - base["_ari"]
            rec["rho"] = spearman([t["fixed_k_score"] for t in scored], [t["_ari"] for t in scored])
        search = [t for t in trials if t["method"] == m and t["new_run"] and t["source"] not in ("baseline", "calibration")]
        rec["n_search"] = len(search)
        rec["n_duplicate"] = sum(1 for t in search if t.get("duplicate_of") is not None)
        if chosen is not None and m in SPACE:
            rec["final_params"] = {n: chosen["params"].get(n) for n in SPACE[m]}
            rec["final_dev"] = deviation(m, chosen["params"])
        if m in TWO_STAGE:
            rec["stage2_skipped"] = skipped.get(m)
            props = []
            for t in trials:
                if t["method"] != m or t["stage"] != "stage1":
                    continue
                a = t.get("_ari") if (t["status"] == "ok" and t.get("n_labels") == k) else None
                se = base.get("se") if base else None
                props.append({"source": t["source"], "params": {n: t["params"].get(n) for n in SPACE[m]},
                              "dev": deviation(m, t["params"]),
                              "d_ari": (a - base["_ari"]) if (a is not None and base and base["_ari"] is not None) else None,
                              "d_score_se": ((t["fixed_k_score"] - base["fixed_k_score"]) / se)
                              if (base and se and t.get("fixed_k_score") is not None and base.get("fixed_k_score") is not None) else None,
                              "duplicate": t.get("duplicate_of") is not None})
            rec["stage1"] = props
            s2 = [t for t in at_k if t["stage"] == "stage2"]
            rec["stage2_best_gain"] = (max(t["_ari"] for t in s2) - base["_ari"]) if (s2 and base) else None
        out["methods"][m] = rec
    return out


def a3_run(root: Path, uid: str, rep_dir: Path, score: Scorer, defaults: dict, rep_scores: dict, ptrials) -> dict:
    run_id = f"{uid}-a3-{rep_dir.name}"
    ws = rep_dir / "ws"
    result = read_json(rep_dir / "result.json")
    selection = read_json(ws / "ensemble_runs" / run_id / "tuning" / "selection.json")
    k = selection["k"]["chosen"]
    out = {"uid": uid, "arm": "A3", "rep": rep_dir.name, "k": k, "tokens": result.get("tokens"), "methods": {}}
    calls = [c for c in result.get("tool_calls", []) if c.get("tool") == "run_skill"]
    out["n_run_skill"] = len(calls)
    out["tool_counts"] = dict(Counter(c.get("tool") for c in result.get("tool_calls", [])))
    for m in defaults:
        rec = {"def": defaults[m], "tun": rep_scores["tuned_ari"].get(m)}
        b = probe_default_at_k(ptrials, m, k)
        if b is not None and b["status"] == "ok":
            rec["base"] = score(b["labels"])
            if rec["base"] is not None and rec["tun"] is not None:
                rec["k_part"] = rec["base"] - rec["def"]
                rec["within_k"] = rec["tun"] - rec["base"]
        own = []
        for tj in (ws / "ensemble_runs" / run_id / m).glob("t*/trial.json"):
            t = read_json(tj)
            mf = tj.parent / "metrics.json"
            n = read_json(mf).get("n_labels") if mf.is_file() else None
            own.append({"params": t.get("params", {}), "n_labels": n, "status": t.get("status")})
        rec["n_runs"] = len(own)
        rec["k_values"] = sorted({t["n_labels"] for t in own if t["n_labels"] is not None})
        if m in SPACE:
            rec["devs"] = [deviation(m, t["params"]) for t in own]
        sel = selection["methods"].get(m) or {}
        if sel.get("params") and m in SPACE:
            rec["final_dev"] = deviation(m, sel["params"])
            rec["final_params"] = {n: sel["params"].get(n) for n in SPACE[m]}
        out["methods"][m] = rec
    return out


def work(args):
    root, uid, truth, unit = args
    score = Scorer(truth)
    defaults = unit["default_ari"]
    runs = []
    for arm in ("A1", "A2", "A6"):
        for i, rep_dir in enumerate(sorted((root / uid / arm).glob("r*"))):
            runs.append(det_run(root, uid, arm, rep_dir, score, defaults, unit["arms"][arm][i]))
    ptrials = probe_trials(root, uid)
    for i, rep_dir in enumerate(sorted((root / uid / "A3").glob("r*"))):
        runs.append(a3_run(root, uid, rep_dir, score, defaults, unit["arms"]["A3"][i], ptrials))
    for r in runs:
        r["k_star"] = unit["k_star"]
    return uid, runs


# ---- summaries -----------------------------------------------------------------------------------


def unit_mean(values):
    v = [x for x in values if x is not None]
    return mean(v) if v else None


def summarise(runs_by_unit: dict) -> dict:
    S: dict = {}
    # 1. D1_m split, per group x arm x method (reps averaged within unit first)
    split = {}
    for g, uids in GROUPS.items():
        for arm in ("A1", "A2", "A6", "A3"):
            for m in RUNNABLE:
                cols = defaultdict(list)
                for u in uids:
                    reps = [r["methods"].get(m) for r in runs_by_unit[u] if r["arm"] == arm and r["methods"].get(m)]
                    if not reps:
                        continue
                    for key in ("k_part", "within_k", "headroom", "argmax_score_gain"):
                        val = unit_mean([x.get(key) for x in reps])
                        if val is not None:
                            cols[key].append(val)
                    val = unit_mean([(x["tun"] - x["def"]) if x.get("tun") is not None else None for x in reps])
                    if val is not None:
                        cols["D1_m"].append(val)
                split[f"{g}|{arm}|{m}"] = {key: describe(v) for key, v in cols.items()}
            # method-averaged per unit
            cols = defaultdict(list)
            for u in uids:
                per_rep = defaultdict(list)
                for r in runs_by_unit[u]:
                    if r["arm"] != arm:
                        continue
                    for key in ("k_part", "within_k", "headroom"):
                        vals = [x.get(key) for x in r["methods"].values() if x.get(key) is not None]
                        if vals:
                            per_rep[key].append(mean(vals))
                for key, vals in per_rep.items():
                    cols[key].append(mean(vals))
            split[f"{g}|{arm}|ALL"] = {key: describe(v) for key, v in cols.items()}
    S["split"] = split

    # 2. chosen-trial sources, stage-2 skip, duplicates, rho
    census = {}
    for g, uids in GROUPS.items():
        for arm in ("A1", "A2", "A6"):
            src = Counter(); skip = Counter(); dup = Counter(); rhos = defaultdict(list); changed = Counter()
            for u in uids:
                for r in runs_by_unit[u]:
                    if r["arm"] != arm:
                        continue
                    for m, x in r["methods"].items():
                        src[(m, x.get("chosen_source"))] += 1
                        if m in TWO_STAGE:
                            skip[(m, bool(x.get("stage2_skipped")))] += 1
                        dup[(m, "dup")] += x.get("n_duplicate", 0)
                        dup[(m, "all")] += x.get("n_search", 0)
                        if x.get("rho") is not None:
                            rhos[m].append(x["rho"])
                        if x.get("final_dev"):
                            changed[(m, x["final_dev"]["n_changed"] > 0)] += 1
            census[f"{g}|{arm}"] = {
                "chosen_source": {f"{m}:{s}": n for (m, s), n in sorted(src.items(), key=str)},
                "stage2_skipped": {f"{m}:{s}": n for (m, s), n in sorted(skip.items(), key=str)},
                "duplicate_share": {m: (dup[(m, "dup")] / dup[(m, "all")]) if dup[(m, "all")] else None for m in RUNNABLE},
                "rho_median": {m: median(v) if v else None for m, v in rhos.items()},
                "final_changed_share": {m: changed[(m, True)] / (changed[(m, True)] + changed[(m, False)])
                                        for m in RUNNABLE if changed[(m, True)] + changed[(m, False)]},
            }
    S["census"] = census
    pooled = {}
    for arm in ("A1", "A2", "A6"):
        src = Counter(); skip = Counter()
        for runs in runs_by_unit.values():
            for r in runs:
                if r["arm"] != arm:
                    continue
                for m in TWO_STAGE:
                    x = r["methods"].get(m)
                    if x:
                        src[x.get("chosen_source")] += 1
                        skip[bool(x.get("stage2_skipped"))] += 1
        pooled[arm] = {"two_stage_chosen_source": dict(src), "stage2_skipped": skip[True], "two_stage_runs": sum(skip.values())}
    S["pooled_two_stage"] = pooled

    # 3. stage-1 proposals: by source, gain and distance
    props = defaultdict(list)
    best_of = defaultdict(list)
    for u, runs in runs_by_unit.items():
        g = GROUP_OF[u]
        for r in runs:
            if r["arm"] == "A3":
                continue
            for m in TWO_STAGE:
                x = r["methods"].get(m)
                if not x or not x.get("stage1"):
                    continue
                by = defaultdict(list)
                for p in x["stage1"]:
                    src = p["source"] if p["source"] == "sweep" else f"{p['source']}@{r['arm']}"
                    props[(g, m, src)].append(p)
                    props[("ALL", m, src)].append(p)
                    if p["d_ari"] is not None:
                        by[p["source"]].append(p["d_ari"])
                if "sweep" in by and len(by) == 2:
                    other = next(s for s in by if s != "sweep")
                    best_of[(g, m, f"{other}@{r['arm']}")].append(max(by[other]) - max(by["sweep"]))
                    best_of[("ALL", m, f"{other}@{r['arm']}")].append(max(by[other]) - max(by["sweep"]))
    prop_sum = {}
    for (g, m, src), ps in props.items():
        d = [p["d_ari"] for p in ps if p["d_ari"] is not None]
        ds = [p["d_score_se"] for p in ps if p["d_score_se"] is not None]
        prop_sum[f"{g}|{m}|{src}"] = {
            "n": len(ps),
            "d_ari_mean": mean(d) if d else None, "d_ari_median": median(d) if d else None,
            "p_ari_up": sum(1 for v in d if v > 0.005) / len(d) if d else None,
            "p_ari_down": sum(1 for v in d if v < -0.005) / len(d) if d else None,
            "p_score_beats_1se": sum(1 for v in ds if v > 1) / len(ds) if ds else None,
            "dup_share": sum(1 for p in ps if p["duplicate"]) / len(ps),
            "linf_mean": mean(p["dev"]["linf"] for p in ps),
            "l1_mean": mean(p["dev"]["l1"] for p in ps),
            "n_changed_mean": mean(p["dev"]["n_changed"] for p in ps),
            "per_param_mean": {n: mean(p["dev"]["per_param"][n] for p in ps) for n in SPACE[m]},
            "per_param_le_0p15": {n: sum(1 for p in ps if p["dev"]["per_param"][n] <= 0.15) / len(ps) for n in SPACE[m]},
            "top_values": Counter(json.dumps(p["params"], sort_keys=True) for p in ps).most_common(6),
        }
    S["stage1"] = prop_sum
    S["best_of3_minus_sweep"] = {f"{g}|{m}|{s}": describe(v) for (g, m, s), v in best_of.items()}

    # 4. same-K matched: LLM (A1) vs random (A6) stage-1 gain, per unit
    matched = defaultdict(list)
    for u, runs in runs_by_unit.items():
        g = GROUP_OF[u]
        for m in TWO_STAGE:
            for arm in ("A1", "A2"):
                llm = [p["d_ari"] for r in runs if r["arm"] == arm for p in (r["methods"].get(m, {}).get("stage1") or [])
                       if p["source"] == "llm" and p["d_ari"] is not None
                       and any(q["k"] == r["k"] for q in runs if q["arm"] == "A6")]
                rnd = [p["d_ari"] for r in runs if r["arm"] == "A6" for p in (r["methods"].get(m, {}).get("stage1") or [])
                       if p["source"] == "random" and p["d_ari"] is not None
                       and any(q["k"] == r["k"] for q in runs if q["arm"] == arm)]
                if llm and rnd:
                    matched[(g, m, arm)].append(mean(llm) - mean(rnd))
                    matched[("ALL", m, arm)].append(mean(llm) - mean(rnd))
    S["same_k_llm_minus_random"] = {f"{g}|{m}|{a}": describe(v) for (g, m, a), v in matched.items()}

    # 5. A3 census
    a3 = {}
    for g, uids in GROUPS.items():
        rs = [r for u in uids for r in runs_by_unit[u] if r["arm"] == "A3"]
        per_m = {}
        for m in RUNNABLE:
            xs = [r["methods"][m] for r in rs if m in r["methods"]]
            devs = [d for x in xs for d in x.get("devs", [])]
            per_m[m] = {
                "runs_mean": mean(x["n_runs"] for x in xs) if xs else None,
                "k_values_mean": mean(len(x["k_values"]) for x in xs) if xs else None,
                "linf_mean": mean(d["linf"] for d in devs) if devs else None,
                "share_all_default": sum(1 for d in devs if d["n_changed"] == 0) / len(devs) if devs else None,
                "final_changed_share": (sum(1 for x in xs if x.get("final_dev") and x["final_dev"]["n_changed"] > 0)
                                        / sum(1 for x in xs if x.get("final_dev"))) if any(x.get("final_dev") for x in xs) else None,
            }
        a3[g] = {"n_runs": len(rs), "run_skill_mean": mean(r["n_run_skill"] for r in rs) if rs else None,
                 "tokens_median": median(r["tokens"] for r in rs if r.get("tokens")) if rs else None,
                 "per_method": per_m}
    S["a3"] = a3

    # 6. LLM token split in deterministic arms
    use = defaultdict(Counter)
    nruns = Counter()
    for runs in runs_by_unit.values():
        for r in runs:
            if r["arm"] in ("A1", "A2"):
                nruns[r["arm"]] += 1
                for p, c in r.get("llm_usage", {}).items():
                    use[(r["arm"], p)].update(c)
    S["llm_usage_per_run"] = {f"{a}|{p}": {k: v / nruns[a] for k, v in c.items()} for (a, p), c in use.items()}
    return S


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=REPORT / "root")
    ap.add_argument("--analysis", type=Path, default=REPORT / "analysis.json")
    ap.add_argument("--output", type=Path, default=REPORT / "posthoc" / "autoagent_value.json")
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args(argv)
    truth = Truth(read_json(a.root / "truth_map.json"))
    scores = read_json(a.analysis)["scores"]
    jobs = []
    for uid in sorted(scores):
        probe = read_json(a.root / uid / "probe" / "result.json")
        unit_obs = next(iter(read_labels(a0["labels"]) for a0 in probe["a0"].values() if a0 and a0.get("status") == "ok"))
        tl = {o: v for o, v in truth.labels(uid).items() if o in unit_obs}
        jobs.append((a.root, uid, tl, scores[uid]))
    runs_by_unit = {}
    with ProcessPoolExecutor(a.workers) as pool:
        for uid, runs in pool.map(work, jobs):
            runs_by_unit[uid] = runs
            print(uid, len(runs), flush=True)
    summary = summarise(runs_by_unit)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps({"summary": summary, "runs": runs_by_unit}, indent=1, default=str))
    print("wrote", a.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
