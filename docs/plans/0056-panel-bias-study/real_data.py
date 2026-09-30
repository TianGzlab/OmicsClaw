"""Real-data check of the spatial_domains panels (0056 F3).

Development data: Slide-seqV2 mouse hippocampus (41,786 beads). The truth column
``obs['cell_type']`` is read only by ``score``; no candidate-generating step sees it.

Stages (run with the OmicsClaw interpreter, ``PYTHONPATH=<repo>``):

``prepare``   ``X <- layers['counts']``, ``obs`` reduced to ``batch``; ``spatial-preprocess``
              at its defaults (``slide_seq``, ``mouse``); after preprocessing ``obs`` is
              reduced to ``batch`` again (owner ruling E3). Writes ``<work>/input.h5ad``.
``generate``  Candidate partitions. Everything inside the tuning ranges goes through
              ``omicsclaw.ensemble`` (``open_ensemble`` + ``EnsembleRunner.fan_out``);
              Leiden/Louvain resolutions above the tuning range (needed to reach ~40
              clusters) run the same skill script directly, marked ``via=direct``.
``score``     Per candidate: the production panel (``compute_panel``), silhouette on
              ``X_pca`` (sample 5000 at seeds 0/1/2, plus a 20000 sample), and ARI / AMI /
              NMI / homogeneity / majority-vote accuracy on the beads of the four
              included regions. Writes ``<work>/scores.json``.
``analyse``   Tables for the report (markdown on stdout).
``ceiling``   How recoverable the four included classes are at all: spatial kNN agreement of
              the truth, ARI of the spatially kNN-smoothed truth, silhouette of the truth.

Panels compared (adjusted values clipped to [0, 1], as production ``combine``):
current  = CHAOS 0.4 + PAS 0.2 + spatial-Leiden AMI 0.4  (production ``spatial_domains/2``)
candidate = PAS 0.5 + silhouette 0.5     (silhouette raw value clipped to [0, 1])
alternate = kNN agreement 1/3 + PAS 1/6 + silhouette 0.5
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
DATA = Path("/workspace/dataset/private/spFoundation_SpatialCorpus/test/slideseqv2_mouse_hippocampus.h5ad")
PYTHON = "/opt/conda/envs/OmicsClaw/bin/python"
INCLUDED = ("CA1_CA2_CA3_Subiculum", "DentatePyramids", "Subiculum_Entorhinal_cl2", "Subiculum_Entorhinal_cl3")
N_REGIONS = len(INCLUDED)
SIL_SAMPLE = 5000
SIL_SEEDS = (0, 1, 2)
SIL_LARGE = 20000
RUN_ID = "f3"

# Candidate grid. Leiden/Louvain: resolution (the equivalent of n_domains) at the default
# spatial_weight, plus spatial_weight variations at two resolutions. Model methods: n_domains.
RESOLUTIONS = (0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0, 1.4, 2.0)
RESOLUTIONS_BEYOND = (3.0, 4.5, 6.0)  # above the tuning range [0.1, 2.0]; run directly
SPATIAL_WEIGHTS = (0.0, 0.6, 0.9)
SW_RESOLUTIONS = (0.3, 1.0)
N_DOMAINS = (4, 6, 7, 8, 10, 14, 20)  # 7 is each script's default
DEFAULTS = {
    "leiden": {"resolution": 1.0, "spatial_weight": 0.3},
    "louvain": {"resolution": 1.0, "spatial_weight": 0.3},
    "spagcn": {"n_domains": 7},
    "graphst": {"n_domains": 7},
    "cellcharter": {"n_domains": 7},
}


# ---- prepare --------------------------------------------------------------------------------


def prepare(work: Path) -> None:
    import anndata as ad

    work.mkdir(parents=True, exist_ok=True)
    counts_path = work / "data" / "counts.h5ad"
    counts_path.parent.mkdir(exist_ok=True)
    a = ad.read_h5ad(DATA)  # read only; never written back
    b = ad.AnnData(X=a.layers["counts"].astype(np.float32), obs=a.obs[["batch"]].copy(), var=a.var[[]].copy())
    b.obsm["spatial"] = np.asarray(a.obsm["spatial"])
    b.write_h5ad(counts_path)
    del a, b
    out = work / "preprocess"
    began = time.monotonic()
    done = subprocess.run(
        [PYTHON, str(REPO / "skills/spatial/spatial-preprocess/spatial_preprocess.py"),
         "--input", str(counts_path), "--output", str(out), "--data-type", "slide_seq", "--species", "mouse"],
        capture_output=True, text=True, cwd=work,
        env={"PATH": os.environ["PATH"], "HOME": "/tmp", "PYTHONPATH": str(REPO), "MPLBACKEND": "Agg"},
    )
    if done.returncode != 0:
        sys.exit(done.stdout[-3000:] + done.stderr[-3000:])
    p = ad.read_h5ad(out / "processed.h5ad")
    p.obs = p.obs[["batch"]].copy()  # E3: strip after preprocessing
    p.write_h5ad(work / "input.h5ad")
    print(json.dumps({"n_obs": p.n_obs, "obs": list(p.obs.columns), "obsm": list(p.obsm.keys()),
                      "x_pca_dims": int(p.obsm["X_pca"].shape[1]),
                      "preprocess_s": round(time.monotonic() - began, 1)}))


# ---- generate -------------------------------------------------------------------------------


def candidate_grid():
    """(method, params, via) for every candidate."""
    grid = []
    for method in ("leiden", "louvain"):
        for r in RESOLUTIONS:
            grid.append((method, {"resolution": r, "spatial_weight": 0.3}, "runner"))
        for r in SW_RESOLUTIONS:
            for w in SPATIAL_WEIGHTS:
                grid.append((method, {"resolution": r, "spatial_weight": w}, "runner"))
        for r in RESOLUTIONS_BEYOND:
            grid.append((method, {"resolution": r, "spatial_weight": 0.3}, "direct"))
    for method in ("spagcn", "graphst", "cellcharter"):
        for k in N_DOMAINS:
            grid.append((method, {"n_domains": k}, "runner"))
    return grid


async def _run_ensemble(work: Path, items):
    from omicsclaw.entry.config import AppConfig
    from omicsclaw.entry.ensemble import open_ensemble
    from omicsclaw.entry.sandbox import SandboxBinding
    from omicsclaw.skills.loader import load_skills

    config = AppConfig(workspace=work, skills_dir=REPO / "skills", ensemble=True,
                       ensemble_python=PYTHON, memory=False)
    runner = await open_ensemble(config, load_skills(REPO / "skills"), SandboxBinding())
    if runner is None:
        raise SystemExit("the ensemble runner did not start")
    specs = [runner.prepare(skill="spatial-domains", method=m, input=work / "input.h5ad",
                            params={"data_type": "slide_seq", **p}, run_id=RUN_ID) for m, p in items]
    began = time.monotonic()
    results = await runner.fan_out(specs)
    return [r.to_dict() for r in results], time.monotonic() - began, runner.pool.gpu_ids


def _run_direct(args):
    work, method, params, index = args
    out = work / "direct" / f"{method}_r{params['resolution']:g}"
    out.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    done = subprocess.run(
        [PYTHON, str(REPO / "skills/spatial/spatial-domains/spatial_domains.py"), "--input", str(work / "input.h5ad"),
         "--output", str(out), "--method", method, "--data-type", "slide_seq",
         "--resolution", str(params["resolution"]), "--spatial-weight", str(params["spatial_weight"])],
        capture_output=True, text=True, cwd=out,
        env={"PATH": os.environ["PATH"], "HOME": "/tmp", "PYTHONPATH": str(REPO), "MPLBACKEND": "Agg",
             "CUDA_VISIBLE_DEVICES": "", "OMP_NUM_THREADS": "8"},
    )
    import pandas as pd

    status = "ok" if done.returncode == 0 else "failed"
    labels = None
    if status == "ok":
        table = pd.read_csv(out / "tables" / "domain_assignments.csv", dtype=str)
        labels = str(out / "labels.csv.gz")
        table.rename(columns={"observation": "obs_id", "spatial_domain": "label"})[["obs_id", "label"]].to_csv(
            labels, index=False)
    return {"method": method, "params": params, "via": "direct", "status": status,
            "wall_s": round(time.monotonic() - began, 1), "labels": labels,
            "error": "" if status == "ok" else done.stderr[-1500:]}


def generate(work: Path) -> None:
    grid = candidate_grid()
    runner_items = [(m, p) for m, p, via in grid if via == "runner"]
    direct_items = [(work, m, p, i) for i, (m, p, via) in enumerate(grid) if via == "direct"]
    with ProcessPoolExecutor(max_workers=len(direct_items)) as pool:
        direct_future = [pool.submit(_run_direct, item) for item in direct_items]
        results, wall, gpus = asyncio.run(_run_ensemble(work, runner_items))
        direct = [f.result() for f in direct_future]
    rows = []
    for (m, p), r in zip(runner_items, results):
        labels = Path(r["output_dir"]) / "labels.csv.gz"
        rows.append({"method": m, "params": p, "via": "runner", "status": r["status"], "stage": r["stage"],
                     "wall_s": r["wall_s"], "queued_s": r["queued_s"], "peak_mem_gb": r["peak_mem_gb"],
                     "lease_gpu": r["lease_gpu"], "device": r["device"], "degraded": r["degraded"],
                     "runner_score": r["score"], "labels": str(labels) if labels.exists() else None,
                     "error": r["error"][-1500:]})
    rows += direct
    (work / "candidates.json").write_text(json.dumps({"fan_out_wall_s": wall, "gpus": list(gpus), "rows": rows},
                                                     indent=1, default=str))
    ok = sum(r["status"] == "ok" for r in rows)
    print(f"{ok}/{len(rows)} ok; runner fan-out {wall:.0f} s on GPUs {gpus}")
    for r in rows:
        if r["status"] != "ok":
            print("FAILED", r["method"], r["params"], r["error"][-300:])


# ---- score ----------------------------------------------------------------------------------


_REF = {}


def _load_reference(work: Path):
    import anndata as ad

    a = ad.read_h5ad(work / "input.h5ad", backed="r")
    ids = np.asarray(a.obs_names).astype(str)
    ref = {"obs_ids": ids, "coords": np.asarray(a.obsm["spatial"], dtype=np.float64)[:, :2],
           "expression": np.asarray(a.obsm["X_pca"], dtype=np.float64)}
    a.file.close()
    t = ad.read_h5ad(DATA, backed="r")
    truth = t.obs["cell_type"].astype(str).reindex(ids).to_numpy()
    t.file.close()
    ref["truth"] = truth
    return ref


def _score_one(args):
    import pandas as pd
    from sklearn import metrics as M

    from omicsclaw.ensemble.metrics.spatial import ReferenceCache, compute_panel

    work, row = args
    if "ref" not in _REF:
        _REF["ref"] = _load_reference(work)
    ref = _REF["ref"]
    table = pd.read_csv(row["labels"], dtype=str, keep_default_na=False).set_index("obs_id")
    labels = table.loc[list(ref["obs_ids"]), "label"].to_numpy()
    document = compute_panel(labels, {"coords": ref["coords"], "expression": ref["expression"]},
                             ReferenceCache(work / "score_cache"))
    _, first = np.unique(labels, return_index=True)
    canon = np.argsort(np.argsort(first))[np.unique(labels, return_inverse=True)[1]]
    fingerprint = hashlib.sha256(canon.astype(np.int32).tobytes()).hexdigest()[:16]
    _, codes = np.unique(labels, return_inverse=True)
    if codes.max() < 1:  # one label: the panel refuses, silhouette is undefined
        return {**row, "k": 1, "fingerprint": fingerprint, "degenerate": True}
    sil = {}
    for seed in SIL_SEEDS:
        sil[f"s{seed}"] = float(M.silhouette_score(ref["expression"], codes, sample_size=SIL_SAMPLE, random_state=seed))
    sil["large"] = float(M.silhouette_score(ref["expression"], codes, sample_size=SIL_LARGE, random_state=0))
    mask = np.isin(ref["truth"], INCLUDED)
    t, p = ref["truth"][mask], labels[mask]
    majority = pd.crosstab(p, t).max(axis=1).sum() / mask.sum()
    ev = {"ari": M.adjusted_rand_score(t, p), "ami": M.adjusted_mutual_info_score(t, p),
          "nmi": M.normalized_mutual_info_score(t, p), "homogeneity": M.homogeneity_score(t, p),
          "majority_acc": float(majority), "n_labels_included": int(np.unique(p).size)}
    return {**row, "k": document["n_labels"], "fingerprint": fingerprint, "degenerate": False, "panel_doc": {k: document[k] for k in
            ("score", "adjusted", "raw", "expected", "errors", "largest_label_frac")}, "sil": sil, "eval": ev}


def score(work: Path, workers: int) -> None:
    rows = [r for r in json.loads((work / "candidates.json").read_text())["rows"] if r["status"] == "ok"]
    # warm the coordinate cache once before fanning out
    first = _score_one((work, rows[0]))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rest = list(pool.map(_score_one, [(work, r) for r in rows[1:]]))
    scored = [first] + rest
    (work / "scores.json").write_text(json.dumps(scored, indent=1, default=float))
    print(f"scored {len(scored)} candidates")


# ---- analyse --------------------------------------------------------------------------------


def clip(v):
    return 0.0 if v is None or not np.isfinite(v) else float(min(1.0, max(0.0, v)))


def panels(row, sil_key="s0"):
    adj = row["panel_doc"]["adjusted"]
    s = clip(row["sil"][sil_key])
    pas, knn = clip(adj.get("pas")), clip(adj.get("knn_agreement"))
    return {
        "current": row["panel_doc"]["score"],
        "candidate": 0.5 * pas + 0.5 * s,
        "alternate": knn / 3 + pas / 6 + 0.5 * s,
    }


def members(row, sil_key="s0"):
    adj = row["panel_doc"]["adjusted"]
    return {"chaos": adj.get("chaos"), "pas": adj.get("pas"), "spatial_leiden_ami": adj.get("spatial_leiden_ami"),
            "knn_agreement": adj.get("knn_agreement"), "silhouette": row["sil"][sil_key]}


def spearman(x, y):
    from scipy.stats import spearmanr

    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return float("nan")
    return float(spearmanr(x, y).statistic)


def boot_ci(x, y, reps=4000, seed=0):
    rng = np.random.default_rng(seed)
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = len(x)
    vals = []
    for _ in range(reps):
        i = rng.integers(0, n, n)
        v = spearman(x[i], y[i])
        if np.isfinite(v):
            vals.append(v)
    if not vals:
        return (float("nan"), float("nan"))
    return tuple(float(q) for q in np.percentile(vals, [2.5, 97.5]))


def label(row):
    p = row["params"]
    if "resolution" in p:
        s = f"r={p['resolution']:g},w={p['spatial_weight']:g}"
    else:
        s = f"n={p['n_domains']}"
    return f"{row['method']}({s}{'*' if row['via'] == 'direct' else ''})"


def is_default(row):
    return all(row["params"].get(k) == v for k, v in DEFAULTS[row["method"]].items())


def f3(v):
    return "—" if v is None or not np.isfinite(v) else f"{v:+.3f}" if v < 0 else f"{v:.3f}"


def analyse(work: Path) -> None:
    everything = json.loads((work / "scores.json").read_text())
    cand = json.loads((work / "candidates.json").read_text())
    out = []
    degenerate = [r for r in everything if r["degenerate"]]
    rows, seen, duplicates = [], {}, []
    for r in everything:
        if r["degenerate"]:
            continue
        if r["fingerprint"] in seen:  # an identical partition counts once
            duplicates.append((label(r), seen[r["fingerprint"]]))
            continue
        seen[r["fingerprint"]] = label(r)
        rows.append(r)
    out += [f"单一标签（K=1，面板拒绝打分）：{', '.join(label(r) for r in degenerate) or '无'}。",
            f"与已有候选完全相同的划分（只计一次）：{len(duplicates)} 个——"
            + "；".join(f"{a} = {b}" for a, b in duplicates) + "。", ""]
    P = ("current", "candidate", "alternate")
    for r in rows:
        r["panels"] = panels(r)
        r["members"] = members(r)
    ari = [r["eval"]["ari"] for r in rows]
    targets = ("ari", "ami", "nmi", "homogeneity", "majority_acc")
    methods = sorted({r["method"] for r in rows})

    n_ok = sum(c["status"] == "ok" for c in cand["rows"])
    out += [f"试验 {len(cand['rows'])} 个，{n_ok} 个 ok；去掉 K=1 与重复划分后分析 {len(rows)} 个候选；runner fan-out 墙钟 {cand['fan_out_wall_s']:.0f} s，"
            f"GPU {cand['gpus']}。", ""]
    failed = [c for c in cand["rows"] if c["status"] != "ok"]
    for c in failed:
        out.append(f"- 失败：{c['method']} {c['params']}：{c['error'][-200:]!r}")

    # table 1: all candidates
    out += ["", "### 表 1　全部候选", "",
            "| 候选 | K | 现状 | 候选面板 | 备选 | CHAOS | PAS | AMI(空间) | kNN | sil | ARI | AMI | NMI | homog. | 多数投票准确率 |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["method"], r["k"])):
        m, p, e = r["members"], r["panels"], r["eval"]
        out.append(f"| {label(r)}{' (默认)' if is_default(r) else ''} | {r['k']} | {f3(p['current'])} | {f3(p['candidate'])} | "
                   f"{f3(p['alternate'])} | {f3(m['chaos'])} | {f3(m['pas'])} | {f3(m['spatial_leiden_ami'])} | "
                   f"{f3(m['knn_agreement'])} | {f3(m['silhouette'])} | {f3(e['ari'])} | {f3(e['ami'])} | "
                   f"{f3(e['nmi'])} | {f3(e['homogeneity'])} | {f3(e['majority_acc'])} |")

    # table 2: spearman of panels vs targets
    out += ["", "### 表 2　面板与外部指标的 Spearman ρ（全部候选；bootstrap 95% CI，4000 次）", "",
            "| 面板 / 成员 | " + " | ".join(targets) + " | ρ(·, K) |", "|---" * (len(targets) + 2) + "|"]
    ks = [r["k"] for r in rows]
    series = {**{f"面板:{p}": [r["panels"][p] for r in rows] for p in P},
              **{f"成员:{m}": [r["members"][m] for r in rows] for m in rows[0]["members"]},
              "K": ks}
    for name, xs in series.items():
        cells = []
        for t in targets:
            ys = [r["eval"][t] for r in rows]
            lo, hi = boot_ci(xs, ys)
            cells.append(f"{spearman(xs, ys):+.2f} [{lo:+.2f}, {hi:+.2f}]")
        out.append(f"| {name} | " + " | ".join(cells) + f" | {spearman(xs, ks):+.2f} |")

    # table 3: per method
    out += ["", "### 表 3　分方法：面板与 ARI 的 Spearman ρ [95% CI]", "",
            "| 方法 | n | K 范围 | 现状 | 候选面板 | 备选 | silhouette | PAS |", "|---|---|---|---|---|---|---|---|"]
    for meth in methods:
        sub = [r for r in rows if r["method"] == meth]
        a = [r["eval"]["ari"] for r in sub]
        cells = []
        for xs in ([r["panels"][p] for r in sub] for p in P):
            lo, hi = boot_ci(xs, a)
            cells.append(f"{spearman(xs, a):+.2f} [{lo:+.2f}, {hi:+.2f}]")
        for mm in ("silhouette", "pas"):
            xs = [r["members"][mm] for r in sub]
            lo, hi = boot_ci(xs, a)
            cells.append(f"{spearman(xs, a):+.2f} [{lo:+.2f}, {hi:+.2f}]")
        out.append(f"| {meth} | {len(sub)} | {min(r['k'] for r in sub)}–{max(r['k'] for r in sub)} | " + " | ".join(cells) + " |")

    # table 4: selection
    defaults = [r for r in rows if is_default(r)]
    def_ari = [r["eval"]["ari"] for r in defaults]
    oracle = max(rows, key=lambda r: r["eval"]["ari"])
    out += ["", "### 表 4　各面板选中的候选", "",
            f"oracle（ARI 最高）：{label(oracle)}，K={oracle['k']}，ARI {oracle['eval']['ari']:.3f}，"
            f"homogeneity {oracle['eval']['homogeneity']:.3f}，多数投票准确率 {oracle['eval']['majority_acc']:.3f}。",
            "各方法默认参数：" + "；".join(f"{label(r)} K={r['k']} ARI {r['eval']['ari']:.3f}" for r in defaults)
            + f"。默认 ARI 中位数 **{np.median(def_ari):.3f}**。", "",
            "| 面板 | 选中 | K | K−4 | ARI | 相对 oracle | 相对默认中位数 | AMI | NMI | homog. | 多数投票准确率 | ARI 在全部候选中的名次 |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    ari_sorted = sorted(ari, reverse=True)
    for p in P:
        best = max(rows, key=lambda r: r["panels"][p])
        e = best["eval"]
        out.append(f"| {p} | {label(best)} | {best['k']} | {best['k'] - N_REGIONS:+d} | {e['ari']:.3f} | "
                   f"{e['ari'] - oracle['eval']['ari']:+.3f} | {e['ari'] - np.median(def_ari):+.3f} | {e['ami']:.3f} | "
                   f"{e['nmi']:.3f} | {e['homogeneity']:.3f} | {e['majority_acc']:.3f} | "
                   f"{ari_sorted.index(e['ari']) + 1}/{len(rows)} |")
    for t in ("homogeneity", "majority_acc", "ami", "nmi"):
        o = max(rows, key=lambda r: r["eval"][t])
        out.append(f"\n{t} 的 oracle：{label(o)}，K={o['k']}，{o['eval'][t]:.3f}。")
    # top-3 per panel
    out += ["", "各面板前 5 名：", ""]
    for p in P:
        top = sorted(rows, key=lambda r: -r["panels"][p])[:5]
        out.append(f"- {p}：" + "；".join(f"{label(r)} K={r['k']} 分 {r['panels'][p]:.3f} ARI {r['eval']['ari']:.3f}"
                                          for r in top))

    # table 5: silhouette stability
    out += ["", "### 表 5　silhouette 抽样稳定性（样本 5000，种子 0/1/2；另列 20000 样本）", ""]
    sil = np.array([[r["sil"][f"s{s}"] for s in SIL_SEEDS] for r in rows])
    large = np.array([r["sil"]["large"] for r in rows])
    sd = sil.std(axis=1, ddof=1)
    out.append(f"- 每个候选三种子 silhouette 的标准差：中位数 {np.median(sd):.4f}，最大 {sd.max():.4f}；"
               f"silhouette 原值范围 {sil.min():+.3f} 到 {sil.max():+.3f}（20000 样本：{large.min():+.3f} 到 {large.max():+.3f}）；"
               f"原值 > 0 的候选 {int((sil[:, 0] > 0).sum())}/{len(rows)}。")
    out.append(f"- 种子两两之间 silhouette 的 Spearman：" + ", ".join(
        f"{a}-{b} {spearman(sil[:, a], sil[:, b]):+.3f}" for a, b in ((0, 1), (0, 2), (1, 2)))
        + f"；种子 0 对 20000 样本 {spearman(sil[:, 0], large):+.3f}。")
    for p in ("candidate", "alternate"):
        picks, rhos = [], []
        for key in [f"s{s}" for s in SIL_SEEDS] + ["large"]:
            vals = [panels(r, key)[p] for r in rows]
            picks.append(label(rows[int(np.argmax(vals))]))
            rhos.append(spearman(vals, ari))
        out.append(f"- {p}：选中候选随种子（0/1/2/20000）：{' / '.join(picks)}；与 ARI 的 ρ：{' / '.join(f'{x:+.3f}' for x in rhos)}。")

    # table 6: K bins of members, to see PAS/sil vs K
    out += ["", "### 表 6　按 K 分箱的成员指标中位数（全部方法合并）", "",
            "| K 箱 | n | CHAOS | PAS | AMI(空间) | kNN | silhouette | ARI | homog. | 多数投票准确率 |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    bins = ((2, 4), (5, 7), (8, 10), (11, 15), (16, 25), (26, 60))
    for lo, hi in bins:
        sub = [r for r in rows if lo <= r["k"] <= hi]
        if not sub:
            continue
        med = lambda f: float(np.median([f(r) for r in sub]))
        out.append(f"| {lo}–{hi} | {len(sub)} | " + " | ".join(f3(med(lambda r, m=m: r["members"][m])) for m in
                   ("chaos", "pas", "spatial_leiden_ami", "knn_agreement", "silhouette")) + " | "
                   + " | ".join(f3(med(lambda r, t=t: r["eval"][t])) for t in ("ari", "homogeneity", "majority_acc")) + " |")

    # partial correlation-ish: within fixed-K model methods, silhouette vs ARI
    out += ["", "### 表 7　控制 K：同一 K 下（spagcn/graphst/cellcharter 三方法之间）哪个面板把 ARI 最高者排第一", "",
            "| K | ARI 最高 | 现状选 | 候选面板选 | 备选选 |", "|---|---|---|---|---|"]
    hits = {p: 0 for p in P}
    total = 0
    for k in N_DOMAINS:
        sub = [r for r in rows if r["method"] in ("spagcn", "graphst", "cellcharter") and r["params"].get("n_domains") == k]
        if len(sub) < 2:
            continue
        total += 1
        best = max(sub, key=lambda r: r["eval"]["ari"])
        picks = {p: max(sub, key=lambda r: r["panels"][p]) for p in P}
        for p in P:
            hits[p] += picks[p] is best
        out.append(f"| {k} | {best['method']} ({best['eval']['ari']:.3f}) | " + " | ".join(
            f"{picks[p]['method']} ({picks[p]['eval']['ari']:.3f})" for p in P) + " |")
    out.append("\n命中数：" + "，".join(f"{p} {hits[p]}/{total}" for p in P) + "。")

    # table 8: robustness over candidate subsets, and the paired difference candidate - current
    out += ["", "### 表 8　候选子集上的稳健性（面板与 ARI 的 ρ [95% CI]；配对 bootstrap 的 ρ 差）", "",
            "| 子集 | n | 现状 ρ | 候选面板 ρ | 备选 ρ | 候选−现状 Δρ | 现状选中 K / ARI | 候选面板选中 K / ARI |",
            "|---|---|---|---|---|---|---|---|"]
    subsets = {
        "全部": rows,
        "只用 runner（去掉超出调参区间的 r≥3）": [r for r in rows if r["via"] == "runner"],
        "K ≤ 20": [r for r in rows if r["k"] <= 20],
        "3 ≤ K ≤ 20": [r for r in rows if 3 <= r["k"] <= 20],
        "只用 spagcn/graphst/cellcharter": [r for r in rows if r["method"] in ("spagcn", "graphst", "cellcharter")],
    }
    for name, sub in subsets.items():
        a = np.array([r["eval"]["ari"] for r in sub])
        xs = {p: np.array([r["panels"][p] for r in sub]) for p in P}
        cells = []
        for p in P:
            lo, hi = boot_ci(xs[p], a)
            cells.append(f"{spearman(xs[p], a):+.2f} [{lo:+.2f}, {hi:+.2f}]")
        rng = np.random.default_rng(1)
        diffs = []
        for _ in range(4000):
            i = rng.integers(0, len(sub), len(sub))
            d = spearman(xs["candidate"][i], a[i]) - spearman(xs["current"][i], a[i])
            if np.isfinite(d):
                diffs.append(d)
        lo, hi = np.percentile(diffs, [2.5, 97.5])
        d0 = spearman(xs["candidate"], a) - spearman(xs["current"], a)
        pick = {p: sub[int(np.argmax(xs[p]))] for p in ("current", "candidate")}
        out.append(f"| {name} | {len(sub)} | " + " | ".join(cells) + f" | {d0:+.2f} [{lo:+.2f}, {hi:+.2f}] | "
                   + " | ".join(f"{pick[p]['k']} / {pick[p]['eval']['ari']:.3f}" for p in ("current", "candidate")) + " |")
    print("\n".join(out))


def ceiling(work: Path) -> None:
    """How recoverable the four included classes are at all (uses the truth; evaluation only)."""
    import anndata as ad
    import pandas as pd
    from scipy.spatial import cKDTree
    from sklearn import metrics as M

    ref = _load_reference(work)
    mask = np.isin(ref["truth"], INCLUDED)
    t, c, x = ref["truth"][mask], ref["coords"][mask], ref["expression"][mask]
    sizes = pd.Series(t).value_counts()
    p = (sizes / sizes.sum()).to_numpy()
    _, idx = cKDTree(c).query(c, k=11)
    agree = float((t[idx[:, 1:]] == t[:, None]).mean())
    smoothed = {}
    for k in (10, 30, 100):
        _, idx = cKDTree(c).query(c, k=k)
        codes, uniq = pd.factorize(t)
        votes = np.apply_along_axis(lambda r: np.bincount(r, minlength=len(uniq)).argmax(), 1, codes[idx])
        smoothed[k] = float(M.adjusted_rand_score(t, uniq[votes]))
    raw = ad.read_h5ad(DATA, backed="r")
    lib = np.asarray(raw.layers["counts"].sum(axis=1)).ravel() if not hasattr(raw.layers["counts"], "to_memory") else None
    raw.file.close()
    out = {
        "n_included": int(mask.sum()), "sizes": {k: int(v) for k, v in sizes.items()},
        "majority_baseline": float(p.max()),
        "knn10_agreement_truth": agree, "knn10_agreement_chance": float((p ** 2).sum()),
        "ari_truth_spatially_smoothed": smoothed,
        "silhouette_truth_xpca_5000": float(M.silhouette_score(x, t, sample_size=SIL_SAMPLE, random_state=0)),
        "centroid_and_sd": {cl: [c[t == cl].mean(0).round(0).tolist(), c[t == cl].std(0).round(0).tolist()]
                            for cl in INCLUDED},
        "coords_range": [c.min(0).round(0).tolist(), c.max(0).round(0).tolist()],
        "median_umi": float(np.median(lib)) if lib is not None else None,
    }
    print(json.dumps(out, indent=1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("prepare", "generate", "score", "analyse", "ceiling"))
    parser.add_argument("--work", type=Path, default=Path("/tmp/0056_f3"))
    parser.add_argument("--workers", type=int, default=24)
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare(args.work)
    elif args.stage == "generate":
        generate(args.work)
    elif args.stage == "score":
        score(args.work, args.workers)
    elif args.stage == "ceiling":
        ceiling(args.work)
    else:
        analyse(args.work)


if __name__ == "__main__":
    main()
