#!/usr/bin/env python3
"""Promoted OmicsClaw skill for Bulkrna Cosinor Rhythm."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))

from skills._sdk.result import (
    mark_result_status,
    write_result_json,
)


SKILL_NAME = "bulkrna-cosinor-rhythm"
SKILL_VERSION = "0.1.0"
DOMAIN = "bulkrna"
SUMMARY = "Deterministic fixed-period 24-hour single-component cosinor OLS rhythm analysis for a bulk RNA time-course CSV."
ANALYSIS_GOAL = "Apply deterministic 24-hour cosinor rhythmicity analysis to examples/demo_bulkrna_cosinor.csv. For every gene, fit the fixed-period single-component cosinor model y(t) = mesor + beta_cos*cos(2*pi*t/24) + beta_sin*sin(2*pi*t/24) by deterministic ordinary least squares (no resampling/bootstrap). Report per-gene fitted parameters and rhythmicity verdicts and write artifact files (cosinor_results.csv, semantic_summary.json, report.md) into the run workspace."
ANALYSIS_CONTEXT = ""
WEB_CONTEXT = ""
SOURCE_RUN_ID = "7787182985b2435997433fa94a7b7096"
DEFAULT_INPUT_FILE = str(Path(__file__).resolve().parent / "data" / "demo_input.csv")
REQUIRES_INPUT = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=SUMMARY)
    parser.add_argument("--input", dest="input_path", help="Path to input data")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Reuse the original autonomous-analysis input when available")
    parser.add_argument("--method", default="", help="Optional method backend name")
    parser.add_argument("--species", default="", help="Optional species label")

    return parser.parse_args()


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _load_semantic_summary(path: Path) -> dict:
    if not path.exists():
        return {}
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise RuntimeError("semantic_summary.json is not a bounded regular file")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("semantic_summary.json must contain a JSON object")
    return payload


def main() -> None:
    args = parse_args()
    effective_input = args.input_path or (DEFAULT_INPUT_FILE if args.demo else "")
    if REQUIRES_INPUT and not effective_input:
        raise SystemExit("Provide --input, or use --demo to reuse the original autonomous-analysis input.")

    skill_output_dir = Path(args.output)
    skill_output_dir.mkdir(parents=True, exist_ok=True)

    INPUT_FILE = effective_input
    AUTONOMOUS_OUTPUT_DIR = str(skill_output_dir)
    OUTPUT_PATH = skill_output_dir
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

    # --- mini-agent facade bootstrap (only referenced globals) -----------
    def ReturnAnswer(text=""):
        (OUTPUT_PATH / "answer.txt").write_text(str(text), encoding="utf-8")

    # === accepted step 1 ===
    import pandas as pd
    import numpy as np
    import json
    import re
    import math

    INPUT_CSV = INPUT_FILE
    OUT_DIR = OUTPUT_PATH

    df = pd.read_csv(INPUT_CSV)

    # Drop duplicate columns if any
    dup_cols = sorted(set(df.columns[df.columns.duplicated()]))
    if dup_cols:
        df = df.loc[:, ~df.columns.duplicated()]

    if "gene" not in df.columns:
        raise ValueError("Input CSV missing 'gene' column")

    df["gene"] = df["gene"].astype(str)
    df = df.drop_duplicates(subset=["gene"]).set_index("gene")

    # Identify and deterministically sort time columns
    pat = re.compile(r"^T(\d{2})_R(\d+)$")
    sample_cols = [c for c in df.columns if pat.match(str(c))]
    sample_cols.sort(key=lambda c: (int(pat.match(str(c)).group(1)), int(pat.match(str(c)).group(2))))

    # Drop sample columns with >20% missing values
    removed_cols = []
    kept_cols = []
    for c in sample_cols:
        if df[c].isna().mean() > 0.20:
            removed_cols.append(c)
        else:
            kept_cols.append(c)
    sample_cols = kept_cols
    times = np.array([int(pat.match(str(c)).group(1)) for c in sample_cols], dtype=float)

    results = []

    for gene, row in df.iterrows():
        y = pd.to_numeric(row[sample_cols], errors="coerce").to_numpy(dtype=float)
        mask = ~np.isnan(y)
        y = y[mask]
        t = times[mask]

        rec = {
            "gene": gene,
            "mesor": np.nan,
            "beta_cos": np.nan,
            "beta_sin": np.nan,
            "amplitude": np.nan,
            "peak_phase_hours": np.nan,
            "r_squared": np.nan,
            "amplitude_ratio": np.nan,
            "rhythmic": False,
        }

        if len(y) < 3:
            results.append(rec)
            continue

        # Fixed-period single-component cosinor design matrix
        X = np.column_stack([
            np.ones_like(t),
            np.cos(2.0 * np.pi * t / 24.0),
            np.sin(2.0 * np.pi * t / 24.0),
        ])

        # Deterministic OLS via normal equations
        try:
            beta = np.linalg.solve(X.T @ X, X.T @ y)
        except np.linalg.LinAlgError:
            results.append(rec)
            continue

        mesor, beta_cos, beta_sin = float(beta[0]), float(beta[1]), float(beta[2])
        pred = X @ beta

        ss_res = float(np.sum((y - pred) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan

        amplitude = math.sqrt(beta_cos**2 + beta_sin**2)

        if mesor > 0:
            amplitude_ratio = amplitude / mesor
        else:
            amplitude_ratio = np.nan

        phase_raw = math.atan2(beta_sin, beta_cos) * 12.0 / math.pi
        peak_phase_hours = phase_raw % 24.0
        if abs(peak_phase_hours - 24.0) < 1e-9:
            peak_phase_hours = 0.0

        rhythmic = bool(r_squared >= 0.80 and amplitude_ratio >= 0.20)

        results.append({
            "gene": gene,
            "mesor": mesor,
            "beta_cos": beta_cos,
            "beta_sin": beta_sin,
            "amplitude": amplitude,
            "peak_phase_hours": peak_phase_hours,
            "r_squared": r_squared,
            "amplitude_ratio": amplitude_ratio,
            "rhythmic": rhythmic,
        })

    # Write cosinor_results.csv
    results_df = pd.DataFrame(results)
    results_df.to_csv(OUT_DIR / "cosinor_results.csv", index=False)

    # Write semantic_summary.json
    rhythmic_genes = sorted([r["gene"] for r in results if r["rhythmic"]])
    semantic_summary = {
        "gene_count": len(results),
        "rhythmic_gene_count": len(rhythmic_genes),
        "rhythmic_genes": rhythmic_genes,
        "validation": {
            "duplicate_columns_dropped": dup_cols,
            "sample_columns_dropped_gt_20pct_missing": removed_cols,
            "sample_columns_used": sample_cols,
        },
    }
    with open(OUT_DIR / "semantic_summary.json", "w") as fh:
        json.dump(semantic_summary, fh, indent=2)

    # Write report.md
    md = []
    md.append("# Cosinor Rhythmicity Report")
    md.append("")
    md.append("Deterministic 24-hour fixed-period single-component cosinor model:")
    md.append("")
    md.append("y(t) = mesor + beta_cos*cos(2*pi*t/24) + beta_sin*sin(2*pi*t/24)")
    md.append("")
    md.append("Parameters were estimated by ordinary least squares via normal equations, with no resampling or bootstrap.")
    md.append("")
    removed_desc = ", ".join(removed_cols) if removed_cols else "none"
    md.append(f"Columns dropped for >20% missing: {removed_desc}")
    md.append("")
    md.append("| gene | mesor | beta_cos | beta_sin | amplitude | peak_phase_hours | r_squared | amplitude_ratio | rhythmic |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        md.append(
            f"| {r['gene']} | {r['mesor']:.6g} | {r['beta_cos']:.6g} | "
            f"{r['beta_sin']:.6g} | {r['amplitude']:.6g} | {r['peak_phase_hours']:.6g} | "
            f"{r['r_squared']:.6g} | {r['amplitude_ratio']:.6g} | {r['rhythmic']} |"
        )
    md.append("")
    md.append(f"Rhythmic genes ({len(rhythmic_genes)}): {', '.join(rhythmic_genes) if rhythmic_genes else 'none'}")
    with open(OUT_DIR / "report.md", "w") as fh:
        fh.write("\n".join(md))

    # Return the final answer
    answer_lines = []
    answer_lines.append(f"Cosinor analysis complete. Genes analyzed: {len(results)}; rhythmic: {len(rhythmic_genes)}.")
    answer_lines.append("gene,mesor,beta_cos,beta_sin,amplitude,peak_phase_hours,r_squared,amplitude_ratio,rhythmic")
    for r in results:
        answer_lines.append(
            f"{r['gene']},{r['mesor']:.6g},{r['beta_cos']:.6g},{r['beta_sin']:.6g},"
            f"{r['amplitude']:.6g},{r['peak_phase_hours']:.6g},{r['r_squared']:.6g},"
            f"{r['amplitude_ratio']:.6g},{r['rhythmic']}"
        )

    ReturnAnswer("\n".join(answer_lines))


    report = f"""# Promoted Skill Report

This skill was generated from a successful Autonomous Code Run.

## Original Goal

{ANALYSIS_GOAL}

## Promotion Notes

- This script started from `analysis.py` code that previously ran successfully.
- Review imports, parameter handling, and output paths before considering it production-ready.
- Expand tests and tighten the OmicsClaw output contract in follow-up edits.
"""

    summary = {"method": args.method, "input": effective_input}
    data = {
        "skill": SKILL_NAME,
        "domain": DOMAIN,
        "input": effective_input,
        "source_run_id": SOURCE_RUN_ID,
        "description": SUMMARY,
    }
    semantic_summary = _load_semantic_summary(skill_output_dir / "semantic_summary.json")
    if semantic_summary:
        data["semantic_summary"] = semantic_summary

    # README.md is owned by the shared runner. Preserve a scientific report
    # emitted by the promoted body; only supply a bounded fallback when the
    # source analysis did not create one.
    if not (skill_output_dir / "report.md").exists():
        _write_text(skill_output_dir / "report.md", report)
    _write_text(
        skill_output_dir / "reproducibility" / "commands.sh",
        f"python {Path(__file__).resolve().name} --output {skill_output_dir}\n",
    )
    write_result_json(
        skill_output_dir, skill=SKILL_NAME, version="0.1.0", summary=summary, data=data
    )
    # Reaching this line means the promoted body above ran to completion without
    # raising, so this is a genuine success signal (unlike the scaffold
    # placeholder's SCAFFOLD_STATUS sentinel, which marks unimplemented science).
    mark_result_status(skill_output_dir, "ok")

    print(f"Promoted skill '{SKILL_NAME}' completed. Outputs written to {skill_output_dir}")


if __name__ == "__main__":
    main()
