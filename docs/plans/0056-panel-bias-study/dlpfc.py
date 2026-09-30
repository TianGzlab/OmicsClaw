"""DLPFC quick check of the spatial_domains panels (0056 G2, step one).

Data: two human DLPFC Visium sections, 151673 and 151674 (read only). The truth column
``obs['sce.layer_guess']`` (Layer1-6 and WM, K*=7) is read only by ``score`` and ``ceiling``;
no candidate-generating step sees it. Spots whose truth is NaN are clustered but not evaluated.

Stages (run with the OmicsClaw interpreter, ``PYTHONPATH=<repo>``), each per section:

``prepare``   ``X`` = raw integer counts (checked); ``obs`` reduced to ``in_tissue``/``array_row``/
              ``array_col``; ``spatial-preprocess --data-type visium --species human`` at its
              defaults; after preprocessing ``obs`` is stripped to the same columns again.
``generate``  Candidates through ``omicsclaw.ensemble`` (``open_ensemble`` + ``fan_out``);
              Leiden/Louvain resolutions above the tuning range run the skill script directly.
``score``     Production panel (``compute_panel``), silhouette on ``X_pca`` (all spots: fewer
              than the 5000 sample), Calinski-Harabasz and Davies-Bouldin on ``X_pca``, and
              ARI/AMI/NMI/homogeneity/majority accuracy on spots with a layer.
``analyse``   Tables for the report. ``--slices 151673 151674`` for the combined view and the
              leave-one-section-out search (step 5).
``ceiling``   Sanity numbers of the truth itself (spatial kNN agreement, silhouette on X_pca).

Panel definitions, statistics and the pass criteria are those of ``real_data.py``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import itertools
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from real_data import boot_ci, clip, f3, spearman  # noqa: E402  (same statistics as F3)

REPO = Path(__file__).resolve().parents[3]
DATA_DIR = Path("/workspace/algorithm/zhouwg_project/data_external/DLPFC")
PYTHON = "/opt/conda/envs/OmicsClaw/bin/python"
TRUTH = "sce.layer_guess"
KEEP_OBS = ["in_tissue", "array_row", "array_col"]
K_STAR = 7
RUN_ID = "g2"

RESOLUTIONS = (0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0, 1.4, 2.0)
RESOLUTIONS_BEYOND = (3.0, 4.5, 6.0)  # above the tuning range [0.1, 2.0]; run directly
SPATIAL_WEIGHTS = (0.0, 0.6, 0.9)
SW_RESOLUTIONS = (0.3, 1.0)
N_DOMAINS = (3, 5, 7, 9, 12, 16)  # 7 is each script's default
DEFAULTS = {
    "leiden": {"resolution": 1.0, "spatial_weight": 0.3},
    "louvain": {"resolution": 1.0, "spatial_weight": 0.3},
    "spagcn": {"n_domains": 7},
    "graphst": {"n_domains": 7},
    "cellcharter": {"n_domains": 7},
}
P = ("current", "candidate", "alternate")
MEMBERS = ("chaos", "pas", "spatial_leiden_ami", "knn_agreement", "silhouette", "calinski_harabasz", "davies_bouldin")


def env():
    return {"PATH": os.environ["PATH"], "HOME": "/tmp", "PYTHONPATH": str(REPO), "MPLBACKEND": "Agg"}


# ---- prepare --------------------------------------------------------------------------------


def prepare(work: Path, section: str, max_mt_pct: float | None = None) -> None:
    import anndata as ad
    import scipy.sparse as sp

    work.mkdir(parents=True, exist_ok=True)
    counts_path = work / "data" / "counts.h5ad"
    counts_path.parent.mkdir(exist_ok=True)
    a = ad.read_h5ad(DATA_DIR / f"{section}.h5ad")  # read only
    x = a.X if sp.issparse(a.X) else sp.csr_matrix(a.X)
    values = x.data
    integer = bool(np.all(values >= 0) and np.all(np.mod(values, 1) == 0))
    if not integer:
        sys.exit("X is not raw integer counts")
    b = ad.AnnData(X=x.astype(np.float32), obs=a.obs[KEEP_OBS].copy(), var=a.var[[]].copy())
    b.var_names_make_unique()
    b.obsm["spatial"] = np.asarray(a.obsm["spatial"])
    b.uns["spatial"] = a.uns["spatial"]  # Visium image metadata; no annotation
    b.write_h5ad(counts_path)
    out = work / "preprocess"
    began = time.monotonic()
    done = subprocess.run(
        [PYTHON, str(REPO / "skills/spatial/spatial-preprocess/spatial_preprocess.py"),
         "--input", str(counts_path), "--output", str(out), "--data-type", "visium", "--species", "human"]
        + ([] if max_mt_pct is None else ["--max-mt-pct", str(max_mt_pct)]),
        capture_output=True, text=True, cwd=work, env=env(),
    )
    if done.returncode != 0:
        sys.exit(done.stdout[-3000:] + done.stderr[-3000:])
    p = ad.read_h5ad(out / "processed.h5ad")
    p.obs = p.obs[[c for c in KEEP_OBS if c in p.obs]].copy()
    p.write_h5ad(work / "input.h5ad")
    print(json.dumps({"section": section, "integer_counts": integer, "n_obs_before": int(a.n_obs),
                      "n_obs": p.n_obs, "n_vars": p.n_vars, "obs": list(p.obs.columns), "obsm": list(p.obsm.keys()),
                      "x_pca_dims": int(p.obsm["X_pca"].shape[1]), "median_umi": float(np.median(np.asarray(x.sum(1)))),
                      "preprocess_s": round(time.monotonic() - began, 1)}))


# ---- generate -------------------------------------------------------------------------------


def candidate_grid():
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
                            params={"data_type": "visium", **p}, run_id=RUN_ID) for m, p in items]
    began = time.monotonic()
    results = await runner.fan_out(specs)
    return [r.to_dict() for r in results], time.monotonic() - began, runner.pool.gpu_ids


def _run_direct(args):
    import pandas as pd

    work, method, params = args
    out = work / "direct" / f"{method}_r{params['resolution']:g}"
    out.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    done = subprocess.run(
        [PYTHON, str(REPO / "skills/spatial/spatial-domains/spatial_domains.py"), "--input", str(work / "input.h5ad"),
         "--output", str(out), "--method", method, "--data-type", "visium",
         "--resolution", str(params["resolution"]), "--spatial-weight", str(params["spatial_weight"])],
        capture_output=True, text=True, cwd=out,
        env={**env(), "CUDA_VISIBLE_DEVICES": "", "OMP_NUM_THREADS": "8"},
    )
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
    direct_items = [(work, m, p) for m, p, via in grid if via == "direct"]
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


def _load_reference(work: Path, section: str):
    import anndata as ad

    a = ad.read_h5ad(work / "input.h5ad", backed="r")
    ids = np.asarray(a.obs_names).astype(str)
    ref = {"obs_ids": ids, "coords": np.asarray(a.obsm["spatial"], dtype=np.float64)[:, :2],
           "expression": np.asarray(a.obsm["X_pca"], dtype=np.float64)}
    a.file.close()
    t = ad.read_h5ad(DATA_DIR / f"{section}.h5ad", backed="r")
    truth = t.obs[TRUTH].astype(object).reindex(ids)
    t.file.close()
    ref["truth"] = np.asarray([str(v) if isinstance(v, str) else "" for v in truth], dtype=object)
    return ref


def _score_one(args):
    import pandas as pd
    from sklearn import metrics as M

    from omicsclaw.ensemble.metrics.spatial import ReferenceCache, compute_panel

    work, section, row = args
    if str(work) not in _REF:  # keyed by section: one process may score several
        _REF[str(work)] = _load_reference(work, section)
    ref = _REF[str(work)]
    table = pd.read_csv(row["labels"], dtype=str, keep_default_na=False).set_index("obs_id")
    labels = table.loc[list(ref["obs_ids"]), "label"].to_numpy()
    document = compute_panel(labels, {"coords": ref["coords"], "expression": ref["expression"]},
                             ReferenceCache(work / "score_cache"))
    _, first = np.unique(labels, return_index=True)
    canon = np.argsort(np.argsort(first))[np.unique(labels, return_inverse=True)[1]]
    fingerprint = hashlib.sha256(canon.astype(np.int32).tobytes()).hexdigest()[:16]
    _, codes = np.unique(labels, return_inverse=True)
    if codes.max() < 1:
        return {**row, "k": 1, "fingerprint": fingerprint, "degenerate": True}
    x = ref["expression"]
    s = float(M.silhouette_score(x, codes))  # all spots (n < the production sample of 5000)
    sil = {"s0": s, "s1": s, "s2": s, "large": s}
    extra = {"calinski_harabasz": float(M.calinski_harabasz_score(x, codes)),
             "davies_bouldin": float(M.davies_bouldin_score(x, codes))}
    mask = ref["truth"] != ""
    t, p = ref["truth"][mask], labels[mask]
    majority = pd.crosstab(p, t).max(axis=1).sum() / mask.sum()
    ev = {"ari": M.adjusted_rand_score(t, p), "ami": M.adjusted_mutual_info_score(t, p),
          "nmi": M.normalized_mutual_info_score(t, p), "homogeneity": M.homogeneity_score(t, p),
          "majority_acc": float(majority), "n_labels_included": int(np.unique(p).size)}
    return {**row, "k": document["n_labels"], "fingerprint": fingerprint, "degenerate": False,
            "panel_doc": {k: document[k] for k in ("score", "adjusted", "raw", "expected", "errors", "largest_label_frac")},
            "sil": sil, "extra": extra, "eval": ev}


def score(work: Path, section: str, workers: int) -> None:
    rows = [r for r in json.loads((work / "candidates.json").read_text())["rows"] if r["status"] == "ok"]
    first = _score_one((work, section, rows[0]))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rest = list(pool.map(_score_one, [(work, section, r) for r in rows[1:]]))
    scored = [first] + rest
    (work / "scores.json").write_text(json.dumps(scored, indent=1, default=float))
    print(f"scored {len(scored)} candidates")


# ---- analyse --------------------------------------------------------------------------------


def panels(row):
    adj = row["panel_doc"]["adjusted"]
    s = clip(row["sil"]["s0"])
    pas, knn = clip(adj.get("pas")), clip(adj.get("knn_agreement"))
    return {"current": row["panel_doc"]["score"], "candidate": 0.5 * pas + 0.5 * s,
            "alternate": knn / 3 + pas / 6 + 0.5 * s}


def members(row):
    adj = row["panel_doc"]["adjusted"]
    return {"chaos": adj.get("chaos"), "pas": adj.get("pas"), "spatial_leiden_ami": adj.get("spatial_leiden_ami"),
            "knn_agreement": adj.get("knn_agreement"), "silhouette": row["sil"]["s0"],
            "calinski_harabasz": row["extra"]["calinski_harabasz"],
            "davies_bouldin": -row["extra"]["davies_bouldin"]}  # sign flipped: higher is better


def label(row):
    p = row["params"]
    s = f"r={p['resolution']:g},w={p['spatial_weight']:g}" if "resolution" in p else f"n={p['n_domains']}"
    return f"{row['method']}({s}{'*' if row['via'] == 'direct' else ''})"


def is_default(row):
    return all(row["params"].get(k) == v for k, v in DEFAULTS[row["method"]].items())


def load_rows(work: Path):
    everything = json.loads((work / "scores.json").read_text())
    rows, seen, duplicates, degenerate = [], {}, [], []
    for r in everything:
        if r["degenerate"]:
            degenerate.append(r)
            continue
        if r["fingerprint"] in seen:
            duplicates.append((label(r), seen[r["fingerprint"]]))
            continue
        seen[r["fingerprint"]] = label(r)
        r["panels"] = panels(r)
        r["members"] = members(r)
        rows.append(r)
    return rows, duplicates, degenerate


def paired_delta(a, b, y, seed=1, reps=4000):
    """Spearman(a, y) - Spearman(b, y), with a paired bootstrap 95% interval."""
    a, b, y = (np.asarray(v, float) for v in (a, b, y))
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(reps):
        i = rng.integers(0, len(y), len(y))
        d = spearman(a[i], y[i]) - spearman(b[i], y[i])
        if np.isfinite(d):
            diffs.append(d)
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return spearman(a, y) - spearman(b, y), float(lo), float(hi)


def analyse_one(work: Path, section: str) -> list[str]:
    rows, duplicates, degenerate = load_rows(work)
    cand = json.loads((work / "candidates.json").read_text())
    out = [f"#### 切片 {section}", ""]
    n_ok = sum(c["status"] == "ok" for c in cand["rows"])
    out += [f"试验 {len(cand['rows'])} 个，{n_ok} 个 ok；runner fan-out 墙钟 {cand['fan_out_wall_s']:.0f} s，GPU {cand['gpus']}。"
            f"K=1 排除：{', '.join(label(r) for r in degenerate) or '无'}；重复划分 {len(duplicates)} 个"
            + (("（" + "；".join(f"{a} = {b}" for a, b in duplicates) + "）") if duplicates else "")
            + f"。分析 {len(rows)} 个候选，K 从 {min(r['k'] for r in rows)} 到 {max(r['k'] for r in rows)}。", ""]
    for c in cand["rows"]:
        if c["status"] != "ok":
            out.append(f"- 失败：{c['method']} {c['params']}：{c['error'][-200:]!r}")

    out += ["", f"全部候选（{section}）：", "",
            "| 候选 | K | 现状 | 候选面板 | 备选 | CHAOS | PAS | AMI(空间) | kNN | sil | CH | −DB | ARI | AMI | NMI |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["method"], r["k"])):
        m, p, e = r["members"], r["panels"], r["eval"]
        out.append(f"| {label(r)}{' (默认)' if is_default(r) else ''} | {r['k']} | {f3(p['current'])} | {f3(p['candidate'])} | "
                   f"{f3(p['alternate'])} | {f3(m['chaos'])} | {f3(m['pas'])} | {f3(m['spatial_leiden_ami'])} | "
                   f"{f3(m['knn_agreement'])} | {f3(m['silhouette'])} | {m['calinski_harabasz']:.0f} | {f3(m['davies_bouldin'])} | "
                   f"{f3(e['ari'])} | {f3(e['ami'])} | {f3(e['nmi'])} |")

    ari = [r["eval"]["ari"] for r in rows]
    ks = [r["k"] for r in rows]
    out += ["", f"面板、成员与外部指标的 Spearman ρ（{section}；bootstrap 95% CI，4000 次）：", "",
            "| 面板 / 成员 | ARI | AMI | NMI | ρ(·, K) |", "|---|---|---|---|---|"]
    series = {**{f"面板:{p}": [r["panels"][p] for r in rows] for p in P},
              **{f"成员:{m}": [r["members"][m] for r in rows] for m in MEMBERS}, "K": ks}
    for name, xs in series.items():
        cells = []
        for t in ("ari", "ami", "nmi"):
            ys = [r["eval"][t] for r in rows]
            lo, hi = boot_ci(xs, ys)
            cells.append(f"{spearman(xs, ys):+.2f} [{lo:+.2f}, {hi:+.2f}]")
        out.append(f"| {name} | " + " | ".join(cells) + f" | {spearman(xs, ks):+.2f} |")

    defaults = [r for r in rows if is_default(r)]
    def_ari = float(np.median([r["eval"]["ari"] for r in defaults]))
    oracle = max(rows, key=lambda r: r["eval"]["ari"])
    ari_sorted = sorted(ari, reverse=True)
    out += ["", f"选中的候选（{section}）：oracle {label(oracle)}，K={oracle['k']}，ARI **{oracle['eval']['ari']:.3f}**。默认参数："
            + "；".join(f"{label(r)} K={r['k']} ARI {r['eval']['ari']:.3f}" for r in defaults)
            + f"；中位数 **{def_ari:.3f}**。", "",
            "| 面板 | 选中 | K | K−7 | ARI | 相对 oracle | 相对默认中位数 | AMI | NMI | ARI 名次 |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for p in P:
        best = max(rows, key=lambda r: r["panels"][p])
        e = best["eval"]
        out.append(f"| {p} | {label(best)} | {best['k']} | {best['k'] - K_STAR:+d} | {e['ari']:.3f} | "
                   f"{e['ari'] - oracle['eval']['ari']:+.3f} | {e['ari'] - def_ari:+.3f} | {e['ami']:.3f} | {e['nmi']:.3f} | "
                   f"{ari_sorted.index(e['ari']) + 1}/{len(rows)} |")
    for m in MEMBERS:
        best = max(rows, key=lambda r: r["members"][m] if r["members"][m] is not None else -np.inf)
        out.append(f"| 成员 {m} 单独 | {label(best)} | {best['k']} | {best['k'] - K_STAR:+d} | {best['eval']['ari']:.3f} | "
                   f"{best['eval']['ari'] - oracle['eval']['ari']:+.3f} | {best['eval']['ari'] - def_ari:+.3f} | "
                   f"{best['eval']['ami']:.3f} | {best['eval']['nmi']:.3f} | {ari_sorted.index(best['eval']['ari']) + 1}/{len(rows)} |")
    out += ["", "各面板前 5 名：", ""]
    for p in P:
        top = sorted(rows, key=lambda r: -r["panels"][p])[:5]
        out.append(f"- {p}：" + "；".join(f"{label(r)} K={r['k']} 分 {r['panels'][p]:.3f} ARI {r['eval']['ari']:.3f}"
                                          for r in top))

    out += ["", f"子集稳健性与配对比较（{section}）：", "",
            "| 子集 | n | 现状 ρ | 候选面板 ρ | 备选 ρ | 候选−现状 Δρ | 备选−现状 Δρ | 现状选中 K / ARI | 候选选中 K / ARI | 备选选中 K / ARI |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    subsets = {
        "全部": rows,
        "只用 runner": [r for r in rows if r["via"] == "runner"],
        "3 ≤ K ≤ 20": [r for r in rows if 3 <= r["k"] <= 20],
        "只用 spagcn/graphst/cellcharter": [r for r in rows if r["method"] in ("spagcn", "graphst", "cellcharter")],
    }
    for name, sub in subsets.items():
        a = [r["eval"]["ari"] for r in sub]
        xs = {p: [r["panels"][p] for r in sub] for p in P}
        cells = []
        for p in P:
            lo, hi = boot_ci(xs[p], a)
            cells.append(f"{spearman(xs[p], a):+.2f} [{lo:+.2f}, {hi:+.2f}]")
        for p in ("candidate", "alternate"):
            d, lo, hi = paired_delta(xs[p], xs["current"], a)
            cells.append(f"{d:+.2f} [{lo:+.2f}, {hi:+.2f}]")
        picks = [sub[int(np.argmax(xs[p]))] for p in P]
        out.append(f"| {name} | {len(sub)} | " + " | ".join(cells) + " | "
                   + " | ".join(f"{r['k']} / {r['eval']['ari']:.3f}" for r in picks) + " |")

    out += ["", f"控制 K：同一 n_domains 下 spagcn/graphst/cellcharter 之间（{section}）", "",
            "| n | ARI 最高 | 现状选 | 候选选 | 备选选 |", "|---|---|---|---|---|"]
    hits, total = {p: 0 for p in P}, 0
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

    out += ["", f"按 K 分箱的中位数（{section}）", "",
            "| K 箱 | n | CHAOS | PAS | AMI(空间) | kNN | silhouette | ARI |", "|---|---|---|---|---|---|---|---|"]
    for lo, hi in ((2, 4), (5, 6), (7, 8), (9, 12), (13, 20), (21, 200)):
        sub = [r for r in rows if lo <= r["k"] <= hi]
        if not sub:
            continue
        med = lambda f: float(np.median([f(r) for r in sub]))  # noqa: E731
        out.append(f"| {lo}–{hi} | {len(sub)} | " + " | ".join(
            f3(med(lambda r, m=m: r["members"][m])) for m in ("chaos", "pas", "spatial_leiden_ami", "knn_agreement", "silhouette"))
            + f" | {f3(med(lambda r: r['eval']['ari']))} |")
    return out


# ---- step 5: which member combination tracks ARI, leave one section out ----------------------

COMBO_MEMBERS = ("chaos", "pas", "spatial_leiden_ami", "knn_agreement", "silhouette", "davies_bouldin")
WEIGHT_GRID = np.round(np.arange(0, 1.0001, 0.1), 2)


def _normalised(rows, m):
    """Member values on a common [0, 1] scale: panel members clipped; DB rank-free min-max within section."""
    vals = np.array([np.nan if r["members"][m] is None else r["members"][m] for r in rows], float)
    if m in ("chaos", "pas", "spatial_leiden_ami", "knn_agreement", "silhouette"):
        return np.clip(np.nan_to_num(vals, nan=0.0), 0, 1)
    lo, hi = np.nanmin(vals), np.nanmax(vals)
    return (vals - lo) / (hi - lo) if hi > lo else np.zeros_like(vals)


def _combos():
    for size in (1, 2, 3):
        for names in itertools.combinations(COMBO_MEMBERS, size):
            if size == 1:
                yield names, (1.0,)
                continue
            for w in itertools.product(WEIGHT_GRID, repeat=size):
                if abs(sum(w) - 1) < 1e-9 and min(w) > 0:
                    yield names, w


def _evaluate(rows, names, w):
    s = sum(wi * _normalised(rows, n) for n, wi in zip(names, w))
    a = np.array([r["eval"]["ari"] for r in rows])
    pick = rows[int(np.argmax(s))]
    return spearman(s, a), pick


def loso(works: dict[str, Path]) -> list[str]:
    data = {s: load_rows(w)[0] for s, w in works.items()}
    combos = list(_combos())
    out = ["", "#### 第 5 步：成员组合的留一切片检验（只报告，不定案）", "",
           f"成员：{', '.join(COMBO_MEMBERS)}（前五个按面板的校正值/原值裁到 [0,1]；Davies-Bouldin 取负后在切片内 min-max 缩放）。"
           f"组合为 1–3 个成员，权重在 0.1 网格上、和为 1，共 {len(combos)} 个。训练切片上按与 ARI 的 Spearman ρ 选最优，"
           "在另一切片上报告 ρ（bootstrap CI）、选中候选的 K 与 ARI。", "",
           "| 训练 → 检验 | 训练上最优组合 | 训练 ρ | 检验 ρ [95% CI] | 检验选中 | K | ARI | 检验 oracle ARI | 检验默认中位数 |",
           "|---|---|---|---|---|---|---|---|---|"]
    sections = list(works)
    for objective in ("rho", "pick"):
        if objective == "pick":
            out += ["", "同上，但训练目标换成\"训练切片上 argmax 候选的 ARI\"（平手取 ρ 更高者）：", "",
                    "| 训练 → 检验 | 训练上最优组合 | 训练选中 ARI | 检验 ρ [95% CI] | 检验选中 | K | ARI | 检验 oracle ARI | 检验默认中位数 |",
                    "|---|---|---|---|---|---|---|---|---|"]
        for train, test in itertools.permutations(sections, 2):
            scored = []
            for names, w in combos:
                rho, pick = _evaluate(data[train], names, w)
                key = (rho,) if objective == "rho" else (pick["eval"]["ari"], rho)
                scored.append((key, names, w))
            key, names, w = max(scored, key=lambda t: t[0])
            rho = key[0]
            rows = data[test]
            s = sum(wi * _normalised(rows, n) for n, wi in zip(names, w))
            a = [r["eval"]["ari"] for r in rows]
            lo, hi = boot_ci(s, a)
            pick = rows[int(np.argmax(s))]
            oracle = max(a)
            dmed = float(np.median([r["eval"]["ari"] for r in rows if is_default(r)]))
            desc = " + ".join(f"{wi:g}·{n}" for n, wi in zip(names, w))
            out.append(f"| {train} → {test} | {desc} | {rho:+.2f}{'' if objective == 'rho' else f' (ρ {key[1]:+.2f})'} | {spearman(s, a):+.2f} [{lo:+.2f}, {hi:+.2f}] | {label(pick)} | "
                       f"{pick['k']} | {pick['eval']['ari']:.3f} | {oracle:.3f} | {dmed:.3f} |")
    # the ten best combinations averaged over both sections, for context
    both = []
    for names, w in combos:
        rhos, picks = [], []
        for s_ in sections:
            rho, pick = _evaluate(data[s_], names, w)
            rhos.append(rho)
            picks.append(pick)
        both.append((min(rhos), rhos, names, w, picks))
    both.sort(key=lambda t: -t[0])
    out += ["", "两张切片上 ρ 的较小值最高的 10 个组合（描述性，同时用了两张切片，不是检验）：", "",
            "| 组合 | ρ 151673 | ρ 151674 | 选中 K / ARI（151673） | 选中 K / ARI（151674） |", "|---|---|---|---|---|"]
    for _, rhos, names, w, picks in both[:10]:
        out.append(f"| {' + '.join(f'{wi:g}·{n}' for n, wi in zip(names, w))} | {rhos[0]:+.2f} | {rhos[1]:+.2f} | "
                   + " | ".join(f"{p['k']} / {p['eval']['ari']:.3f}" for p in picks) + " |")
    return out


def combined(works: dict[str, Path]) -> list[str]:
    """Pooled view: per-section rank-transformed ARI so sections are comparable."""
    out = ["", "#### 合并两张切片", "", "| 面板 | 各切片 ρ | 平均 ρ | 选中 ARI（各切片） | K−7（各切片） |", "|---|---|---|---|---|"]
    data = {s: load_rows(w)[0] for s, w in works.items()}
    for p in P:
        rhos, aris, dks = [], [], []
        for s, rows in data.items():
            rhos.append(spearman([r["panels"][p] for r in rows], [r["eval"]["ari"] for r in rows]))
            best = max(rows, key=lambda r: r["panels"][p])
            aris.append(best["eval"]["ari"])
            dks.append(best["k"] - K_STAR)
        out.append(f"| {p} | {' / '.join(f'{x:+.2f}' for x in rhos)} | {np.mean(rhos):+.2f} | "
                   f"{' / '.join(f'{x:.3f}' for x in aris)} | {' / '.join(f'{x:+d}' for x in dks)} |")
    return out


def ceiling(work: Path, section: str) -> None:
    import pandas as pd
    from scipy.spatial import cKDTree
    from sklearn import metrics as M

    ref = _load_reference(work, section)
    mask = ref["truth"] != ""
    t, c, x = ref["truth"][mask], ref["coords"][mask], ref["expression"][mask]
    sizes = pd.Series(t).value_counts()
    p = (sizes / sizes.sum()).to_numpy()
    _, idx = cKDTree(c).query(c, k=11)
    from omicsclaw.ensemble.metrics.spatial import compute_panel

    doc = compute_panel(t, {"coords": c, "expression": x})
    adj = doc["adjusted"]
    truth_panels = {"current": doc["score"],
                    "candidate": 0.5 * clip(adj.get("pas")) + 0.5 * clip(M.silhouette_score(x, t)),
                    "alternate": clip(adj.get("knn_agreement")) / 3 + clip(adj.get("pas")) / 6
                    + 0.5 * clip(M.silhouette_score(x, t)), "adjusted": adj}
    print(json.dumps({
        "truth_as_candidate_on_labelled_spots": truth_panels,
        "section": section, "n_obs_input": int(len(ref["truth"])), "n_evaluated": int(mask.sum()),
        "sizes": {k: int(v) for k, v in sizes.items()},
        "knn10_agreement_truth": float((t[idx[:, 1:]] == t[:, None]).mean()),
        "knn10_agreement_chance": float((p ** 2).sum()),
        "silhouette_truth_xpca": float(M.silhouette_score(x, t)),
    }, indent=1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("prepare", "generate", "score", "analyse", "ceiling"))
    parser.add_argument("--slices", nargs="+", default=["151673"])
    parser.add_argument("--root", type=Path, default=Path("/tmp/0056_dlpfc"))
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--max-mt-pct", type=float, default=None,
                        help="sensitivity arm only; the main run keeps the skill default")
    args = parser.parse_args()
    works = {s: args.root / s for s in args.slices}
    if args.stage == "analyse":
        out = []
        for s, w in works.items():
            out += analyse_one(w, s) + [""]
        if len(works) > 1:
            out += combined(works) + loso(works)
        print("\n".join(out))
        return
    for s, w in works.items():
        if args.stage == "prepare":
            prepare(w, s, args.max_mt_pct)
        elif args.stage == "generate":
            generate(w)
        elif args.stage == "score":
            score(w, s, args.workers)
        else:
            ceiling(w, s)


if __name__ == "__main__":
    main()
