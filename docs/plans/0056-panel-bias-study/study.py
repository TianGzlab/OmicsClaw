"""Extended-K panel bias study (0056 E1).

Stage 1 (``compute``): for every configuration (layout x geometry x K* x noise)
build contiguous candidates K = 2 .. K_max, with K_max = max(largest reference
Leiden cluster count, 3K*, 40), apply label noise to every candidate, and store
the raw ingredients of every metric (CHAOS raw / E_rand / d_min, PAS raw / E,
spatial-Leiden AMI, kNN agreement raw / E, silhouette at several expression
signal strengths). Production code is only imported, never modified.

Stage 2 (``analyse``): recombine the stored ingredients into the current panel
and a set of candidate fixes, report per-member argmax K, and the deviation of
each panel's argmax from K* on training and held-out configuration subsets.

Run with the OmicsClaw interpreter (igraph is needed for the Leiden reference):

    PYTHONPATH=<repo> /opt/conda/envs/OmicsClaw/bin/python study.py compute --out rows.json
    PYTHONPATH=<repo> /opt/conda/envs/OmicsClaw/bin/python study.py analyse --rows rows.json --k-main 40 > tables.md

Main tables use K <= 40 (the task's floor); the shape table uses every computed K
(default up to 60) to see whether the preference stops or keeps rising.

The synthetic generators are the ones of ``tests/ensemble/test_panel_bias.py``
(copied here so the study does not depend on the test module's import path).
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

N_OBS = 5000
NOISE_LEVELS = (0.0, 0.05, 0.15)
K_TRUE = (4, 7, 10)
LAYOUTS = ("grid", "poisson")
GEOMETRIES = ("stripes", "voronoi")
SIGNALS = (1.0, 2.0, 4.0)  # expression signal strength; 2.0 is the original study's
K_FLOOR = 40
TIE = 1e-9


# ---- synthetic tissue (identical to tests/ensemble/test_panel_bias.py) ---------------------


def layout(kind, n=N_OBS, seed=0):
    if kind == "grid":
        side = int(round(np.sqrt(n)))
        axis = (np.arange(side) + 0.5) / side
        xx, yy = np.meshgrid(axis, axis)
        return np.c_[xx.ravel(), yy.ravel()]
    return np.random.default_rng(seed).uniform(size=(n, 2))


def regions(coords, geometry, k, seed=0):
    if geometry == "stripes":
        return np.minimum((coords[:, 0] * k).astype(int), k - 1)
    rng = np.random.default_rng(seed + 100 * k)
    seeds = rng.uniform(0.05, 0.95, size=(k, 2))
    distance = ((coords[:, None, :] - seeds[None, :, :]) ** 2).sum(-1)
    return distance.argmin(axis=1)


def _relabel(labels):
    return np.unique(labels, return_inverse=True)[1]


def merged(labels, knn, k):
    labels = _relabel(labels.copy())
    while np.unique(labels).size > k:
        sizes = np.bincount(labels)
        present = np.flatnonzero(sizes)
        smallest = present[np.argmin(sizes[present])]
        members = labels == smallest
        neighbours = labels[knn[members]].ravel()
        neighbours = neighbours[neighbours != smallest]
        labels[members] = np.bincount(neighbours).argmax()
        labels = _relabel(labels)
    return labels


def resplit(labels, coords, k):
    labels = _relabel(labels.copy())
    while np.unique(labels).size < k:
        largest = np.bincount(labels).argmax()
        members = np.flatnonzero(labels == largest)
        span = coords[members].max(axis=0) - coords[members].min(axis=0)
        axis = int(np.argmax(span))
        cut = np.median(coords[members, axis])
        labels[members[coords[members, axis] > cut]] = labels.max() + 1
    return _relabel(labels)


def noisy(labels, rate, seed):
    if rate == 0:
        return labels.copy()
    rng = np.random.default_rng(seed)
    out = labels.copy()
    k = np.unique(labels).size
    chosen = rng.choice(labels.size, size=int(round(rate * labels.size)), replace=False)
    shift = rng.integers(1, k, size=chosen.size)
    out[chosen] = (labels[chosen] + shift) % k
    return out


def expression_for(truth, signal):
    expression = np.random.default_rng(5).normal(size=(truth.size, 10))
    return expression + signal * np.eye(10)[truth % 10]


# ---- stage 1: compute ---------------------------------------------------------------------


def _cache_root():
    return Path(os.environ.get("STUDY_CACHE", "/tmp/panel_bias_study/cache"))


def reference_counts(layout_kind):
    from omicsclaw.ensemble.metrics.spatial import LEIDEN_NEIGHBORS, LEIDEN_RESOLUTIONS, LEIDEN_SEED
    from omicsclaw.ensemble.metrics.spatial import ReferenceCache, _cached, reference_partitions

    coords = layout(layout_kind)
    cache = ReferenceCache(_cache_root() / layout_kind)
    params = {"n_neighbors": LEIDEN_NEIGHBORS, "resolutions": list(LEIDEN_RESOLUTIONS), "seed": LEIDEN_SEED}
    arrays = _cached(cache, "spatial_leiden", params,
                     lambda: {f"p{i}": p for i, p in enumerate(reference_partitions(coords))})
    return [int(np.unique(arrays[f"p{i}"]).size) for i in range(len(LEIDEN_RESOLUTIONS))]


def one_task(task):
    """All metric ingredients for one (layout, geometry, K*, K) over every noise level."""
    from sklearn.metrics import silhouette_score

    from omicsclaw.ensemble.metrics.spatial import ReferenceCache, compute_panel, spatial_knn

    layout_kind, geometry, k_star, k = task
    coords = layout(layout_kind)
    knn = spatial_knn(coords, 10)
    truth = regions(coords, geometry, k_star)
    if k < k_star:
        kind, clean = "merge", merged(truth, knn, k)
    elif k == k_star:
        kind, clean = "truth", _relabel(truth)
    else:
        kind, clean = "resplit", resplit(truth, coords, k)
    cache = ReferenceCache(_cache_root() / layout_kind)
    expressions = {s: expression_for(truth, s) for s in SIGNALS}
    rows = []
    for noise in NOISE_LEVELS:
        labels = noisy(clean, noise, 7)
        doc = compute_panel(labels, {"coords": coords, "expression": expressions[2.0]}, cache)
        chaos = doc["diagnostics"]["chaos"]
        row = {
            "layout": layout_kind, "geometry": geometry, "k_star": k_star, "noise": noise,
            "k": k, "kind": kind, "n_labels": doc["n_labels"],
            "score_current": doc["score"],
            "chaos_raw": doc["raw"]["chaos"], "chaos_E": doc["expected"]["chaos"],
            "chaos_dmin": chaos["lower_bound"], "chaos_adj": doc["adjusted"]["chaos"],
            "pas_raw": doc["raw"]["pas"], "pas_E": doc["expected"]["pas"], "pas_adj": doc["adjusted"]["pas"],
            "ami": doc["adjusted"]["spatial_leiden_ami"],
            "ami_per_resolution": doc["diagnostics"]["spatial_leiden_ami"]["ami_per_resolution"],
            "knn_adj": doc["adjusted"]["knn_agreement"],
            "errors": doc["errors"],
        }
        for s in SIGNALS:
            row[f"sil_{s:g}"] = float(silhouette_score(expressions[s], labels, sample_size=min(5000, labels.size),
                                                        random_state=0))
        rows.append(row)
    return rows


def compute(out: Path, workers: int, k_cap: int):
    counts = {kind: reference_counts(kind) for kind in LAYOUTS}
    tasks = []
    k_max = {}
    for layout_kind, geometry, k_star in itertools.product(LAYOUTS, GEOMETRIES, K_TRUE):
        top = max(max(counts[layout_kind]), 3 * k_star, k_cap)
        k_max[f"{layout_kind}/{geometry}/{k_star}"] = top
        tasks += [(layout_kind, geometry, k_star, k) for k in range(2, top + 1)]
    print(f"reference Leiden cluster counts: {counts}; {len(tasks)} tasks", file=sys.stderr)
    rows = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, part in enumerate(pool.map(one_task, tasks, chunksize=1)):
            rows += part
            if i % 100 == 0:
                print(f"{i}/{len(tasks)}", file=sys.stderr)
    out.write_text(json.dumps({"reference_counts": counts, "k_max": k_max, "rows": rows}))


# ---- stage 2: panels ----------------------------------------------------------------------


def clip(v):
    return min(1.0, max(0.0, v))


def chaos_current(r):
    d = r["chaos_E"] - r["chaos_dmin"]
    return None if d <= 0 else (r["chaos_E"] - r["chaos_raw"]) / d


def chaos_floor(r, tau=1.0):
    """Denominator floored at tau times the mean global nearest-neighbour distance."""
    d = max(r["chaos_E"] - r["chaos_dmin"], tau * r["chaos_dmin"])
    return (r["chaos_E"] - r["chaos_raw"]) / d


def chaos_reliability(r, tau=1.0):
    """Weight multiplier: dynamic range E - d_min in units of tau * d_min, capped at 1."""
    return min(1.0, max(0.0, (r["chaos_E"] - r["chaos_dmin"]) / (tau * r["chaos_dmin"])))


def sil_mapped(r, s=2.0):  # production diagnostic: (s + 1) / 2, chance level 0.5
    return (r[f"sil_{s:g}"] + 1) / 2


def sil_zero(r, s=2.0):  # chance level 0, the panel's own convention
    return r[f"sil_{s:g}"]


def weighted(parts):
    """Weighted mean of clipped values; parts = [(weight, value)]; None values are dropped."""
    usable = [(w, v) for w, v in parts if v is not None and w > 0]
    total = sum(w for w, _ in usable)
    return sum(w * clip(v) for w, v in usable) / total


SIL_WEIGHTS = (0.2, 0.33, 0.5, 0.67)


def _families(s):
    """Panel families parameterised by the silhouette weight w (w = 0: no silhouette)."""
    ch, fl, rb = chaos_current, chaos_floor, chaos_reliability
    sil = lambda r: sil_zero(r, s)
    return {
        "c_silmap": ("现状三项按 0.4:0.2:0.4 分 1−w，silhouette 用生产映射 (s+1)/2",
                     lambda r, w: weighted([((1 - w) * 0.4, ch(r)), ((1 - w) * 0.2, r["pas_adj"]),
                                            ((1 - w) * 0.4, r["ami"]), (w, sil_mapped(r, s))])),
        "c_sil0": ("现状三项按 0.4:0.2:0.4 分 1−w，silhouette 用原值（0=随机水平）",
                   lambda r, w: weighted([((1 - w) * 0.4, ch(r)), ((1 - w) * 0.2, r["pas_adj"]),
                                          ((1 - w) * 0.4, r["ami"]), (w, sil(r))])),
        "e_ami01": ("CHAOS 0.4 / PAS 0.2 / AMI 0.1 按比例分 1−w，+ silhouette 原值",
                    lambda r, w: weighted([((1 - w) * 4 / 7, ch(r)), ((1 - w) * 2 / 7, r["pas_adj"]),
                                           ((1 - w) / 7, r["ami"]), (w, sil(r))])),
        "e_chaos": ("去 AMI；CHAOS(现状):PAS = 2:1 分 1−w，+ silhouette 原值",
                    lambda r, w: weighted([((1 - w) * 2 / 3, ch(r)), ((1 - w) / 3, r["pas_adj"]), (w, sil(r))])),
        "e_floor": ("去 AMI；CHAOS(分母下限):PAS = 2:1 分 1−w，+ silhouette 原值",
                    lambda r, w: weighted([((1 - w) * 2 / 3, fl(r)), ((1 - w) / 3, r["pas_adj"]), (w, sil(r))])),
        "e_reliab": ("去 AMI；CHAOS(可靠度加权):PAS = 2:1 分 1−w，+ silhouette 原值",
                     lambda r, w: weighted([((1 - w) * 2 / 3 * rb(r), ch(r)), ((1 - w) / 3, r["pas_adj"]), (w, sil(r))])),
        "e_knn": ("去 AMI；kNN agreement 代 CHAOS，kNN:PAS = 2:1 分 1−w，+ silhouette 原值",
                  lambda r, w: weighted([((1 - w) * 2 / 3, r["knn_adj"]), ((1 - w) / 3, r["pas_adj"]), (w, sil(r))])),
        "e_pas": ("去 AMI 与 CHAOS；PAS 1−w + silhouette 原值 w",
                  lambda r, w: weighted([(1 - w, r["pas_adj"]), (w, sil(r))])),
    }


def panel_variants(signal=2.0):
    """name -> (description, scoring function of one row)."""
    ch, fl, rb = chaos_current, chaos_floor, chaos_reliability
    v = {
        "a_current": ("现状：CHAOS 0.4 / PAS 0.2 / AMI 0.4",
                      lambda r: weighted([(0.4, ch(r)), (0.2, r["pas_adj"]), (0.4, r["ami"])])),
        "b1_floor": ("CHAOS 分母下限 max(E−d_min, d_min)，权重同现状",
                     lambda r: weighted([(0.4, fl(r)), (0.2, r["pas_adj"]), (0.4, r["ami"])])),
        "b2_reliab": ("CHAOS 权重乘 min(1,(E−d_min)/d_min)（可靠度加权），其余同现状",
                      lambda r: weighted([(0.4 * rb(r), ch(r)), (0.2, r["pas_adj"]), (0.4, r["ami"])])),
        "b3_knn": ("CHAOS 换成 kNN agreement 校正值（闭式期望），权重同现状",
                   lambda r: weighted([(0.4, r["knn_adj"]), (0.2, r["pas_adj"]), (0.4, r["ami"])])),
        "d0_noami": ("去掉 AMI：CHAOS 0.4 / PAS 0.2",
                     lambda r: weighted([(0.4, ch(r)), (0.2, r["pas_adj"])])),
        "d1_ami01": ("AMI 降到 0.1：CHAOS 0.4 / PAS 0.2 / AMI 0.1",
                     lambda r: weighted([(0.4, ch(r)), (0.2, r["pas_adj"]), (0.1, r["ami"])])),
        "d2_noami_floor": ("去 AMI + CHAOS 分母下限：CHAOS 0.4 / PAS 0.2",
                           lambda r: weighted([(0.4, fl(r)), (0.2, r["pas_adj"])])),
    }
    for fam, (desc, f) in _families(signal).items():
        for w in SIL_WEIGHTS:
            v[f"{fam}_{w}"] = (f"{desc}；w={w}", lambda r, f=f, w=w: f(r, w))
    v["sil_only"] = ("只用 silhouette（参照）", lambda r: sil_zero(r, signal))
    return v


def members():
    return {
        "chaos_adj": chaos_current,
        "chaos_floor": chaos_floor,
        "pas_adj": lambda r: r["pas_adj"],
        "ami": lambda r: r["ami"],
        "knn_adj": lambda r: r["knn_adj"],
        "sil": lambda r: r["sil_2"],
    }


def group(rows):
    out = {}
    for r in rows:
        out.setdefault((r["layout"], r["geometry"], r["k_star"], r["noise"]), []).append(r)
    for key in out:
        out[key].sort(key=lambda r: r["k"])
    return out


def argmax_set(rows, f):
    scores = {r["k"]: f(r) for r in rows}
    scores = {k: v for k, v in scores.items() if v is not None}
    best = max(scores.values())
    return sorted(k for k, v in scores.items() if best - v <= TIE), scores


def worst_dev(ks, k_star):
    return max((k - k_star for k in ks), key=abs)


def summarise(configs, f):
    devs, ties = [], 0
    for (_, _, k_star, _), rows in configs:
        ks, _ = argmax_set(rows, f)
        ties += len(ks) > 1
        devs.append(worst_dev(ks, k_star))
    devs = np.array(devs)
    return {
        "n": len(devs), "median_dev": float(np.median(devs)), "median_abs": float(np.median(np.abs(devs))),
        "within1": float(np.mean(np.abs(devs) <= 1)), "exact": float(np.mean(devs == 0)), "ties": ties,
    }


def fmt_summary(s):
    return f"{s['median_dev']:+.1f} / {s['median_abs']:.1f} / {s['within1']:.0%} / {s['exact']:.0%}"


SPLITS = {
    "全部36": lambda c: True,
    "训:条带": lambda c: c[1] == "stripes",
    "留:Voronoi": lambda c: c[1] == "voronoi",
    "训:K*4,10": lambda c: c[2] in (4, 10),
    "留:K*=7": lambda c: c[2] == 7,
}
SPLIT_PAIRS = (("训:条带", "留:Voronoi"), ("训:K*4,10", "留:K*=7"))


def _rank(s):
    return (s["within1"], -s["median_abs"])


def analyse(rows_path: Path, k_main: int):
    from scipy.stats import spearmanr

    data = json.loads(rows_path.read_text())
    all_rows = data["rows"]
    rows = [r for r in all_rows if r["k"] <= k_main]
    configs = sorted(group(rows).items())
    configs_long = sorted(group(all_rows).items())
    k_top = max(r["k"] for r in all_rows)
    out = [f"reference Leiden cluster counts (res 0.1/0.55/1.0): {data['reference_counts']}",
           f"main tables use K = 2..{k_main}; shape table uses K = 2..{k_top}", ""]

    mem = members()
    current = panel_variants()["a_current"][1]
    out += [f"### A. 各配置：面板成员与现状面板的 argmax K（K≤{k_main}，信号 2.0）", "",
            "| 布局 | 形状 | K* | 噪声 | CHAOS | PAS | AMI | kNN | silhouette | 现状面板 | 现状面板 K* 处 / 最高 |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for (lay, geo, k_star, noise), rs in configs:
        cells = [_kset(argmax_set(rs, mem[n])[0]) for n in ("chaos_adj", "pas_adj", "ami", "knn_adj", "sil")]
        ks, scores = argmax_set(rs, current)
        cells += [_kset(ks), f"{scores[k_star]:.3f} / {max(scores.values()):.3f}"]
        out.append(f"| {lay} | {geo} | {k_star} | {noise:.0%} | " + " | ".join(cells) + " |")
    out.append("")

    out += [f"### B. 偏好形状（K 扩到 {k_top}）", "",
            f"每个配置在 K∈[2K*, {k_top}] 段上的 Spearman(分数, K) 中位数（+1 继续单调上升，−1 回落）；"
            f"以及 K≤{k_top} 时的 argmax K 中位数。", "",
            "| 布局 | 量 | 现状面板 | CHAOS | PAS | AMI | kNN | silhouette |", "|---|---|---|---|---|---|---|---|"]
    fs = [current] + [mem[n] for n in ("chaos_adj", "pas_adj", "ami", "knn_adj", "sil")]
    for lay in LAYOUTS:
        rho, am = [], []
        for f in fs:
            vals, maxes = [], []
            for (l, _, k_star, noise), rs in configs_long:
                if l != lay:
                    continue
                ks, _ = argmax_set(rs, f)
                maxes.append(ks[-1] if len(ks) < 5 else np.nan)
                tail = [r for r in rs if r["k"] >= 2 * k_star]
                y = [f(r) for r in tail]
                if np.ptp(y) < 1e-9:
                    continue
                vals.append(spearmanr([r["k"] for r in tail], y)[0])
            rho.append(f"{np.median(vals):+.2f}" if vals else "平")
            maxes = [m for m in maxes if not np.isnan(m)]
            am.append(f"{np.median(maxes):.0f}" + ("" if len(maxes) == 18 else f"（{18 - len(maxes)} 个大平分除外）"))
        out.append(f"| {lay} | Spearman 尾段 | " + " | ".join(rho) + " |")
        out.append(f"| {lay} | argmax 中位数 | " + " | ".join(am) + " |")
    out.append("")

    out += [f"### C. AMI 的 argmax（K≤{k_top}）与参照 Leiden 簇数", "", "| 布局 | 参照簇数 | AMI argmax K（18 个配置） |", "|---|---|---|"]
    for lay in LAYOUTS:
        flat = sorted(k for (l, *_), rs in configs_long if l == lay for k in argmax_set(rs, mem["ami"])[0])
        out.append(f"| {lay} | {data['reference_counts'][lay]} | {flat} |")
    out.append("")

    variants = panel_variants()
    out += [f"### D. 各方案 argmax K 相对 K* 的偏差（K≤{k_main}，信号 2.0）", "",
            "每格：偏差中位数 / |偏差|中位数 / 落在 K*±1 的比例 / 恰为 K* 的比例。平分时取离 K* 最远者。", "",
            "| 方案 | " + " | ".join(SPLITS) + " |", "|---|" + "---|" * len(SPLITS)]
    for name, (desc, f) in variants.items():
        cells = [fmt_summary(summarise([c for c in configs if pred(c[0])], f)) for pred in SPLITS.values()]
        out.append(f"| {name} | " + " | ".join(cells) + " |")
    out += ["", "方案说明：", ""] + [f"- `{n}`：{d}" for n, (d, _) in variants.items() if not n[-1].isdigit() or n.startswith(("a_", "b", "d"))]
    out += [f"- `<族>_<w>`：{d}" for d in ()] + [f"- 族 `{fam}`：{d}" for fam, (d, _) in _families(2.0).items()] + [""]

    out += ["### E. 在训练集上选 silhouette 权重 w，报告留出集（信号 2.0；另列信号 1.0 / 4.0 的留出结果）", "",
            f"w 的候选 {SIL_WEIGHTS}；选择准则：训练集 K*±1 比例最高，平手取 |偏差|中位数更小者，再平手取更小的 w。", ""]
    out += ["| 族 | 划分 | 选中 w | 训练 | 留出（信号 2.0） | 留出（信号 1.0） | 留出（信号 4.0） |", "|---|---|---|---|---|---|---|"]
    for fam in _families(2.0):
        for train, hold in SPLIT_PAIRS:
            tr = [c for c in configs if SPLITS[train](c[0])]
            best = None
            for w in SIL_WEIGHTS:
                sm = summarise(tr, panel_variants(2.0)[f"{fam}_{w}"][1])
                if best is None or _rank(sm) > _rank(best[1]):
                    best = (w, sm)
            w = best[0]
            ho = [c for c in configs if SPLITS[hold](c[0])]
            cells = [fmt_summary(summarise(ho, panel_variants(sig)[f"{fam}_{w}"][1])) for sig in (2.0, 1.0, 4.0)]
            out.append(f"| {fam} | {train}→{hold} | {w} | {fmt_summary(best[1])} | " + " | ".join(cells) + " |")
    for name in ("a_current", "d0_noami", "d2_noami_floor", "sil_only"):
        for train, hold in SPLIT_PAIRS:
            ho = [c for c in configs if SPLITS[hold](c[0])]
            tr = [c for c in configs if SPLITS[train](c[0])]
            cells = [fmt_summary(summarise(ho, panel_variants(sig)[name][1])) for sig in (2.0, 1.0, 4.0)]
            out.append(f"| {name} | {train}→{hold} | — | {fmt_summary(summarise(tr, variants[name][1]))} | " + " | ".join(cells) + " |")
    out.append("")

    key = ["a_current", "b1_floor", "d0_noami", "d2_noami_floor", "c_sil0_0.5", "e_chaos_0.5", "e_floor_0.5",
           "e_reliab_0.5", "e_knn_0.5", "e_pas_0.5", "e_ami01_0.5", "sil_only"]
    out += ["### F. 按噪声分层（全部 36，信号 2.0）", "", "| 方案 | 噪声 0 | 噪声 5% | 噪声 15% |", "|---|---|---|---|"]
    for name in key:
        f = variants[name][1]
        cells = [fmt_summary(summarise([c for c in configs if c[0][3] == nz], f)) for nz in NOISE_LEVELS]
        out.append(f"| {name} | " + " | ".join(cells) + " |")
    out.append("")

    out += ["### G. CHAOS 动态范围 (E−d_min)/d_min（噪声 0，中位数）", "",
            "| 布局 | K=2 | K=3 | K=4 | K=7 | K=10 | K=20 | K=40 |", "|---|---|---|---|---|---|---|---|"]
    for lay in LAYOUTS:
        cells = []
        for k in (2, 3, 4, 7, 10, 20, 40):
            vals = [(r["chaos_E"] - r["chaos_dmin"]) / r["chaos_dmin"] for r in rows
                    if r["layout"] == lay and r["k"] == k and r["noise"] == 0]
            cells.append(f"{np.median(vals):.3f}")
        out.append(f"| {lay} | " + " | ".join(cells) + " |")
    out.append("")
    print("\n".join(out))


def _kset(ks):
    return str(ks[0]) if len(ks) == 1 else (f"{ks[0]}–{ks[-1]}（平{len(ks)}）")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compute")
    c.add_argument("--out", type=Path, required=True)
    c.add_argument("--workers", type=int, default=96)
    c.add_argument("--k-cap", type=int, default=60, help="candidates up to max(Leiden counts, 3K*, k_cap)")
    a = sub.add_parser("analyse")
    a.add_argument("--rows", type=Path, required=True)
    a.add_argument("--k-main", type=int, default=K_FLOOR)
    args = parser.parse_args()
    if args.cmd == "compute":
        compute(args.out, args.workers, args.k_cap)
    else:
        analyse(args.rows, args.k_main)


if __name__ == "__main__":
    main()
