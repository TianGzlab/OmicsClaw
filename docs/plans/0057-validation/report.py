"""Render the 0057 hold-out report (plan §4.7) as Markdown from ``analyse.py``, ``cost.py`` and ``power_0059.py`` output.

Sections without data say so rather than being dropped. ``--title`` sets the
heading (a sample run is labelled there).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ARMS, RUNNABLE, read_json  # noqa: E402
from evaluate import unit_means  # noqa: E402

J1_SENTENCE = "DLPFC 主要估计量主要反映 K=7 下的调参，不能作为 LLM 定 K 优于稳定性规则的证据。"
ARM_ORDER = ("A1", "A2", "A3", "A6")


def _f(value, digits=3):
    if value is None:
        return "-"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_f(v, digits) for v in value) + "]"
    if isinstance(value, float):
        if value != value:
            return "NaN"
        return f"{value:.{digits}f}"
    return str(value)


def per_unit(analysis: dict, mapping: dict) -> list[str]:
    head = ["| 单元 | 数据 | K* | " + " | ".join(f"A0 {m}" for m in RUNNABLE)
            + " | A0k | 默认中位数 | 默认最大 | " + " | ".join(f"{a} K/fin ARI" for a in ARM_ORDER) + " |",
            "|" + "---|" * (6 + len(RUNNABLE) + len(ARM_ORDER))]
    rows = []
    for uid, s in sorted(analysis["scores"].items()):
        m = mapping.get(uid, {})
        where = m.get("slice") or f"slide {m.get('slide')} FOV {m.get('fov')} {m.get('population', '')}"
        arms = []
        for arm in ARM_ORDER:
            reps = s["arms"].get(arm) or []
            arms.append("; ".join(f"{r['chosen_k']}{'*' if r['k_source'] == 'fallback' and arm != 'A6' else ''}/{_f(r['fin_ari'])}"
                                  for r in reps) or "-")
        a0k = s.get("a0k") or {}
        rows.append(f"| {uid} | {m.get('dataset', '')} {where} | {s['k_star']} | "
                    + " | ".join(_f(s["default_ari"].get(mm)) for mm in RUNNABLE)
                    + f" | {_f(a0k.get('ari'))}（K={a0k.get('n_labels')}） | {_f(s['median_def'])} | {_f(s['max_def'])} | "
                    + " | ".join(arms) + " |")
    return head + rows + ["", "`*` 表示该次 LLM 臂的 K 决策走了回退。"]


def per_unit_tuned(analysis: dict) -> list[str]:
    """A1's per-method answers (``tun_m`` ARI, mean over repetitions) with fallback counts, and the failures."""
    head = ["| 单元 | K* | " + " | ".join(f"A1 tun {m}" for m in RUNNABLE) + " | 失败 |",
            "|" + "---|" * (3 + len(RUNNABLE))]
    rows = []
    for uid, s in sorted(analysis["scores"].items()):
        reps = s["arms"].get("A1") or []
        cells = []
        for method in RUNNABLE:
            if method not in s["default_ari"]:
                cells.append("剔除")
                continue
            values = [r["tuned_ari"][method] for r in reps if method in r["tuned_ari"]]
            fallback = sum(method in r["fallback_default"] for r in reps)
            cells.append(_f(sum(values) / len(values) if values else None)
                         + (f" †{fallback}/{len(reps)}" if fallback else ""))
        failures = [f"A0 {m}" for m in RUNNABLE if m not in s["default_ari"]]
        for arm in ARM_ORDER:
            for index, r in enumerate(s["arms"].get(arm) or [], start=1):
                if r.get("status") != "ok" or r.get("fin_ari") is None:
                    failures.append(f"{arm} r{index}")
        rows.append(f"| {uid} | {s['k_star']} | " + " | ".join(cells) + f" | {', '.join(failures) or '-'} |")
    return head + rows + ["", "单元格是 A1 三次重复的 `tun_m` ARI 均值；`†n/3` 表示有 n 次重复该方法取了 "
                          "`fallback_default`（贡献 0）；`剔除` 表示该方法的默认结果失败，按 §4.4 不进入该单元。"]


def measured_cost(cost: dict) -> list[str]:
    """Totals of the measured cost per arm, the probe's, and the A3 token distribution."""
    import statistics

    measured = cost.get("measured") or {}
    probe = [m["probe"] for m in measured.values()]
    lines = ["| 项 | 次数 | 新运行数 | GPU·h | 核·h（预留） | LLM 调用 | 输入 token | 其中缓存命中 | 输出 token | 墙钟 h（合计） | 墙钟 h（每次中位数） |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    if probe:
        lines.append(f"| 探测 | {len(probe)} | {sum(p['trials'] for p in probe)} | {_f(sum(p['gpu_h'] for p in probe), 1)} | "
                     f"{_f(sum(p['core_h'] for p in probe), 0)} | 0 | 0 | 0 | 0 | {_f(sum(p['wall_h'] for p in probe), 1)} | "
                     f"{_f(statistics.median(p['wall_h'] for p in probe), 2)} |")
    for arm in ("A1", "A2", "A6", "A3"):
        reps = [r for m in measured.values() for r in m["arms"].get(arm, [])]
        if not reps:
            continue
        total = lambda key: sum((r.get(key) or 0) for r in reps)  # noqa: E731
        calls = "-" if arm == "A3" else str(int(total("llm_calls")))
        lines.append(f"| {arm} | {len(reps)} | {int(total('new_runs'))} | {_f(total('gpu_h'), 1)} | {_f(total('core_h'), 0)} | "
                     f"{calls} | {int(total('input'))} | {int(total('cache_read'))} | {int(total('output'))} | "
                     f"{_f(total('wall_h'), 1)} | {_f(statistics.median(r['wall_h'] for r in reps), 2)} |")
    a3 = [r for m in measured.values() for r in m["arms"].get("A3", [])]
    if a3:
        tokens = sorted(r["tokens"] for r in a3)
        p95 = tokens[min(len(tokens) - 1, math.ceil(0.95 * len(tokens)) - 1)]
        lines += ["", f"A3 每次 token（输入 + 输出，缓存命中全额计入）：最小 {tokens[0]}、中位数 {_f(statistics.median(tokens), 0)}、"
                      f"p95 {p95}、最大 {tokens[-1]}；n={len(a3)}，失败 {sum(r['status'] != 'ok' for r in a3)}，"
                      f"触顶 {sum(bool(r.get('capped')) for r in a3)}，发出提醒 {sum(bool(r.get('reminded')) for r in a3)}。"
                      "A3 的 LLM 调用次数没有单独记录。"]
    return lines


def estimator_table(block: dict, keys=("D1", "D2", "D3", "fin_ari")) -> list[str]:
    lines = ["| 臂 | 估计量 | n | 均值 | 中位数 | t95 | BCa95 | 符号翻转 p |", "|---|---|---|---|---|---|---|---|"]
    for arm in ARM_ORDER:
        for key in keys:
            d = (block.get(arm) or {}).get(key) or {}
            if d.get("n"):
                lines.append(f"| {arm} | {key} | {d['n']} | {_f(d['mean'])} | {_f(d['median'])} | {_f(d['t95'])} | "
                             f"{_f(d['bca95'])} | {_f(d.get('sign_flip_p'), 4)} |")
    for other in ("A1-A2", "A1-A3", "A1-A6", "A1_cellcharter-A0k"):
        d = block.get(other) or {}
        if d.get("n"):
            lines.append(f"| {other} | 差 | {d['n']} | {_f(d['mean'])} | {_f(d['median'])} | {_f(d['t95'])} | "
                         f"{_f(d['bca95'])} | {_f(d.get('sign_flip_p'), 4)} |")
    return lines


def per_method_d1(analysis: dict, uids: list[str]) -> list[str]:
    lines = ["| 方法 | A1 的 D1_m 均值 | n |", "|---|---|---|"]
    for method in RUNNABLE:
        values = []
        for u in uids:
            reps = analysis["scores"][u]["arms"].get("A1") or []
            vals = [r["D1_m"].get(method) for r in reps if r["D1_m"].get(method) is not None]
            if vals:
                values.append(sum(vals) / len(vals))
        lines.append(f"| {method} | {_f(sum(values) / len(values) if values else None)} | {len(values)} |")
    return lines


def k_choice_table(block: dict | None) -> list[str]:
    if not block:
        return ["（无数据）"]
    lines = ["| 臂 | n | 选 7 的比例 | K 分布 | 落在稳定峰值 | 随机水平 \\|M\\|/\\|G\\| | 平均 \\|K−K*\\| | chosen_k=7 时的 D1 | 来源 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for arm in ARM_ORDER:
        d = block.get(arm)
        if not d:
            continue
        lines.append(f"| {arm} | {d['n']} | {_f(d['share_7'])} | {d['distribution']} | {_f(d['share_in_stable_peaks'])} | "
                     f"{_f(d['chance_share'])} | {_f(d['abs_k_error_mean'], 2)} | {_f(d['D1_given_k7'])} | {d['sources']} |")
    return lines


def render(analysis: dict, mapping: dict, cost: dict | None, power: dict | None, title: str, notes: list[str]) -> str:
    groups = analysis["groups"]
    dlpfc = groups.get("DLPFC", {})
    out = [f"# {title}", "", *notes, "", "## 1. 逐单元", "", *per_unit(analysis, mapping), "",
           *per_unit_tuned(analysis), ""]
    out += ["## 2. 主要估计量（DLPFC）", "", *estimator_table(dlpfc), "", "每方法 D1_m：", "",
            *per_method_d1(analysis, dlpfc.get("units", [])), ""]
    spread = {arm: (dlpfc.get(arm) or {}).get("rep_sd_median") or {} for arm in ARM_ORDER}
    out += ["重复间标准差（每个单元内算，再取单元中位数）：" + "；".join(
        f"{arm} D1 {_f(s.get('D1'))}、D2 {_f(s.get('D2'))}" for arm, s in spread.items() if s) + "。", ""]
    stop = dlpfc.get("stop_line")
    if stop:
        verdict = "**触发**：不进入 0059 确证" if stop["triggered"] else "未触发"
        out += [f"**无效停止线**：D1 t95 上界 {_f(stop['d1_t95'][1])}，D2 t95 上界 {_f(stop['d2_t95'][1])} → {verdict}。", ""]
    else:
        out += ["**无效停止线**：数据不足，无法判定。", ""]
    out += ["敏感性（剔除 fallback_default 方法、失败按默认中位数计）见上表的 `D1_excluding_fallback`/`D2_median_fill`：", "",
            *estimator_table(dlpfc, keys=("D1_excluding_fallback", "D2_median_fill")), ""]
    out += ["## 3. 次要估计量", "", "见第 2 节表中的 D3 与 A1−A2/A3/A6、A1 cellcharter−A0k 行。", ""]
    out += ["## 4. K 选择与 J1 判读", ""]
    for key in sorted(k for k in groups if k.startswith("DLPFC_Kstar")):
        out += [f"### {key}", "", *k_choice_table(groups[key].get("k_choice")), ""]
    j1 = analysis.get("j1", {})
    if j1.get("A1_share7_Kstar5") is None:
        out += ["J1 判读：本次数据中没有 K*=5 的 DLPFC 单元，无法判读。", ""]
    else:
        out += [f"J1 判读：A1 在 K*=5 组选 7 的比例 {_f(j1['A1_share7_Kstar5'])}，A6 {_f(j1['A6_share7_Kstar5'])}。"
                + (J1_SENTENCE if j1["triggered"] else "未触发判读句。"), ""]
    for key in sorted(k for k in groups if k.startswith("DLPFC_Kstar")):
        block = groups[key]
        out += [f"{key} 的 D1/D2：", "", *estimator_table(block, keys=("D1", "D2")), ""]
    out += ["## 5. 按供体、slide 分列", ""]
    for key in sorted(k for k in groups if k.startswith("DLPFC_Br") or k == "DLPFC_without_Br8100"):
        out += [f"### {key}（{', '.join(groups[key]['units'])}）", "", *estimator_table(groups[key], keys=("D1", "D2")), ""]
    for key in sorted(k for k in groups if k.startswith("CosMx_slide")):
        out += [f"### {key}（n={len(groups[key]['units'])}）", "", *estimator_table(groups[key], keys=("D1", "D2", "D3")),
                "", *k_choice_table(groups[key].get("k_choice")), ""]
    strat = groups.get("CosMx_primary_stratified") or {}
    for key in ("D1", "D2"):
        if strat.get(key):
            s = strat[key]
            out.append(f"- CosMx 主总体按 slide 等权分层的 A1 {key}：{_f(s['mean'])}，95% 分层 bootstrap {_f(s['ci95'])}，"
                       f"各 slide {({k: round(v, 3) for k, v in s['per_slide'].items()})}")
    both = groups.get("CosMx_primary_both_definitions")
    if both:
        out += ["", f"两种 K* 口径都 ≥ 3 的 CosMx 块（n={len(both['units'])}）：", "", *estimator_table(both, keys=("D1", "D2")), ""]
    single = groups.get("CosMx_single_Kstar2") or {}
    if single.get("blocks"):
        out += ["", "### CosMx K*=2 单列块", "", "| 块 | slide | FOV | A1 D1 | A1 D2 | A1 fin ARI |", "|---|---|---|---|---|---|"]
        for u, b in sorted(single["blocks"].items()):
            a1 = b.get("A1") or {}
            out.append(f"| {u} | {b['slide']} | {b['fov']} | {_f(a1.get('D1'))} | {_f(a1.get('D2'))} | {_f(a1.get('fin_ari'))} |")
        out += ["", f"A1 D2 中位数：{_f(single.get('median_D2_A1'))}", ""]
    for definition in ("k_star", "k_star_5pct"):
        block = groups.get(f"CosMx_k_choice_by_{definition}")
        if block:
            out += [f"CosMx 按真值 K（{definition}）分组的 K 选择：", ""]
            for k, choice in block.items():
                out += [f"K*={k}：", "", *k_choice_table(choice), ""]
    out += ["## 6. 描述性", "", "| 单元 | oracle | oracle（仅探测） | A1 遗憾 | 固定 K 下 ρ（K: n, ρ） | 最终选择来源 | 跳过第 2 阶段 |",
            "|---|---|---|---|---|---|---|"]
    for u, d in sorted(analysis["descriptive"].items()):
        rho = "; ".join(f"{k}: {v['n']}, {v['rho']:.2f}" for k, v in d["spearman_at_chosen_k"].items())
        out.append(f"| {u} | {_f(d['oracle'])} | {_f(d['oracle_probe'])} | {_f(d['regret_A1'])} | {rho or '-'} | "
                   f"{d['search']['final_sources']} | {d['search']['stage2_skipped']}/{d['search']['two_stage']} |")
    out += ["", "## 7. 成本", ""]
    if cost:
        e = cost["extrapolation"]
        out += [f"- 实测单元数 {e['units_measured']}；探测每单元 {_f(e['per_unit_probe']['gpu_h'], 2)} GPU·h、"
                f"{_f(e['per_unit_probe']['core_h'], 1)} 核·h（预留口径）。", "",
                "| 臂 | 每次 GPU·h | 每次核·h | 每次输入 token | 每次输出 token | 重复 |", "|---|---|---|---|---|---|"]
        for arm, a in e["per_arm_run"].items():
            out.append(f"| {arm} | {_f(a.get('gpu_h'), 2)} | {_f(a.get('core_h'), 1)} | {_f(a.get('input'), 0)} | "
                       f"{_f(a.get('output'), 0)} | {a['reps']} |")
        t = e["holdout_total"]
        out += ["", f"按 42 个单元外推：{_f(t['gpu_h'], 0)} GPU·h、{_f(t['core_h'], 0)} 核·h、"
                f"输入 {_f(t['input_tokens'] / 1e6, 1)}M / 输出 {_f(t['output_tokens'] / 1e6, 1)}M token。", "",
                "实测合计：", "", *measured_cost(cost), ""]
    else:
        out += ["（未提供）", ""]
    out += ["## 8. 给 0059 的功效计算输入", "", "```json", json.dumps(power, indent=1) if power else "（未提供）", "```", ""]
    out += ["## 9. 偏离、失败与泄漏拦截", ""]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--cost", type=Path, default=None)
    parser.add_argument("--power", type=Path, default=None)
    parser.add_argument("--title", default="计划 0057 留出集报告")
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    text = render(read_json(args.analysis), read_json(args.map), read_json(args.cost) if args.cost else None,
                  read_json(args.power) if args.power else None, args.title, args.note)
    args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
