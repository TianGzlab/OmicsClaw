#!/usr/bin/env python3
"""Metabolomics Annotation — Annotate metabolite features by m/z matching.

Supports multiple adduct types ([M+H]+, [M-H]-, [M+Na]+) and configurable
mass tolerance in ppm.

Usage:
    python annotation.py --input <data.csv> --output <dir> --database hmdb
    python annotation.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import (
    generate_report_header,
    generate_report_footer,
    write_result_json,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "annotation"
SKILL_VERSION = "0.3.0"
SUPPORTED_DATABASES = ("hmdb", "kegg", "lipidmaps", "metlin")

# ---------------------------------------------------------------------------
# Adduct definitions (mass shifts)
# ---------------------------------------------------------------------------
# Proton mass: 1.007276 Da
_PROTON = 1.00727646677

ADDUCT_RULES: dict[str, float] = {
    "[M+H]+":  _PROTON,           # M + H
    "[M-H]-": -_PROTON,           # M - H
    "[M+Na]+": 22.98922,          # M + Na (22.98922 = Na - e)
    "[M+K]+":  38.96316,          # M + K
    "[M+NH4]+": 18.03437,         # M + NH4
}

# ---------------------------------------------------------------------------
# Demo metabolite database
# Monoisotopic *neutral* masses from HMDB / PubChem
# ---------------------------------------------------------------------------
DEMO_METABOLITES = [
    # (name, neutral_monoisotopic_mass, hmdb_id, molecular_formula)
    ("D-Glucose",       180.063388, "HMDB0000122", "C6H12O6"),
    ("L-Lactic acid",    90.031694, "HMDB0000190", "C3H6O3"),
    ("L-Alanine",        89.047678, "HMDB0000161", "C3H7NO2"),
    ("Glycine",          75.032028, "HMDB0000123", "C2H5NO2"),
    ("L-Serine",        105.042593, "HMDB0000187", "C3H7NO3"),
    ("L-Proline",       115.063329, "HMDB0000162", "C5H9NO2"),
    ("L-Valine",        117.078979, "HMDB0000883", "C5H11NO2"),
    ("L-Leucine",       131.094629, "HMDB0000687", "C6H13NO2"),
    ("L-Isoleucine",    131.094629, "HMDB0000172", "C6H13NO2"),
    ("L-Threonine",     119.058243, "HMDB0000167", "C4H9NO3"),
    ("Pyruvic acid",     88.016044, "HMDB0000243", "C3H4O3"),
    ("Citric acid",     192.027003, "HMDB0000094", "C6H8O7"),
    ("Succinic acid",   118.026609, "HMDB0000254", "C4H6O4"),
    ("L-Glutamic acid", 147.053158, "HMDB0000148", "C5H9NO4"),
    ("L-Tryptophan",    204.089878, "HMDB0000929", "C11H12N2O2"),
]


def _compute_adduct_mz(neutral_mass: float, adduct: str) -> float:
    """Compute the expected m/z for a given adduct type."""
    return neutral_mass + ADDUCT_RULES[adduct]


# ---------------------------------------------------------------------------
# Core annotation
# ---------------------------------------------------------------------------

def annotate_mz(
    mz_values: pd.Series,
    database: str = "hmdb",
    ppm: float = 10.0,
    adducts: list[str] | None = None,
) -> pd.DataFrame:
    """Annotate observed m/z values against the metabolite database.

    Parameters
    ----------
    mz_values : Series
        Observed m/z values.
    database : str
        Database name (informational label; we use DEMO_METABOLITES for the demo).
    ppm : float
        Mass tolerance in parts-per-million.
    adducts : list[str] or None
        Which adducts to consider.  Defaults to ``["[M+H]+", "[M-H]-"]``.

    Returns
    -------
    DataFrame with columns: query_mz, name, formula, database_id,
        adduct, theoretical_mz, ppm_error, confidence.

    All matches within tolerance are reported (not just the first).
    """
    if adducts is None:
        adducts = ["[M+H]+", "[M-H]-"]

    logger.info(
        "Annotating %d features against %s (ppm=%.1f, adducts=%s)",
        len(mz_values), database, ppm, adducts,
    )

    annotations: list[dict] = []

    for mz in mz_values:
        matched = False
        for name, neutral_mass, db_id, formula in DEMO_METABOLITES:
            for adduct in adducts:
                theo_mz = _compute_adduct_mz(neutral_mass, adduct)
                error_ppm = abs(mz - theo_mz) / theo_mz * 1e6

                if error_ppm <= ppm:
                    confidence = "high" if error_ppm < 3 else ("medium" if error_ppm < 7 else "low")
                    annotations.append({
                        "query_mz": mz,
                        "name": name,
                        "formula": formula,
                        "database_id": db_id,
                        "adduct": adduct,
                        "theoretical_mz": round(theo_mz, 6),
                        "ppm_error": round(error_ppm, 2),
                        "confidence": confidence,
                    })
                    matched = True
                    # Do NOT break — report all matches

        if not matched:
            annotations.append({
                "query_mz": mz,
                "name": "Unknown",
                "formula": "",
                "database_id": "",
                "adduct": "",
                "theoretical_mz": np.nan,
                "ppm_error": np.nan,
                "confidence": "none",
            })

    return pd.DataFrame(annotations)


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

def get_demo_data() -> pd.DataFrame:
    """Generate demo peak table with realistic m/z values.

    Some values are drawn from known metabolites (shifted to [M+H]+ m/z)
    so that annotation will produce matches.
    """
    logger.info("Generating demo peak table")
    rng = np.random.default_rng(42)
    n_peaks = 50

    # Generate known-metabolite m/z values (as [M+H]+ adducts with small noise)
    known_mz = []
    for name, mass, _, _ in DEMO_METABOLITES[:12]:
        known_mz.append(mass + _PROTON + rng.normal(0, mass * 2e-6))

    # Fill remaining with random m/z
    random_mz = rng.uniform(100, 800, n_peaks - len(known_mz))
    all_mz = np.concatenate([known_mz, random_mz])
    rng.shuffle(all_mz)

    return pd.DataFrame({
        "mz": np.round(all_mz, 6),
        "rt": np.round(rng.uniform(0.5, 25, len(all_mz)), 3),
        "intensity": np.round(rng.lognormal(10, 2, len(all_mz)), 2),
    })


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
) -> None:
    """Write comprehensive report."""
    header = generate_report_header(
        title="Metabolite Annotation Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Database": summary["database"],
            "Annotated": f"{summary['n_annotated']}/{summary['n_queries']}",
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Database**: {summary['database']}",
        f"- **Adducts considered**: {summary['adducts']}",
        f"- **Total query features**: {summary['n_queries']}",
        f"- **Features with ≥1 match**: {summary['n_annotated']} ({summary['annotation_rate']:.1f}%)",
        f"- **Total matches**: {summary['n_total_matches']}",
        f"- **High confidence**: {summary.get('n_high_conf', 0)}",
        "",
        "## Method\n",
        "Each observed m/z is compared against theoretical m/z values for every "
        "metabolite × adduct combination in the database. All matches within the "
        "specified ppm tolerance are reported.",
        "",
        "## Parameters\n",
    ]
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python metabolomics_annotation.py --input <input.csv> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Metabolite Annotation")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--database", default="hmdb", choices=list(SUPPORTED_DATABASES))
    parser.add_argument("--ppm", type=float, default=10.0)
    parser.add_argument(
        "--adducts",
        nargs="+",
        default=["[M+H]+", "[M-H]-"],
        help="Adduct types to consider (default: [M+H]+ [M-H]-)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        peaks = get_demo_data()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        peaks = pd.read_csv(args.input_path)
        input_file = args.input_path

    logger.info("Input: %d features", len(peaks))

    annotations = annotate_mz(peaks["mz"], args.database, args.ppm, args.adducts)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    annotations.to_csv(tables_dir / "annotations.csv", index=False)

    # Unique query features that got at least one non-Unknown match
    n_queries = int(peaks["mz"].nunique())
    n_annotated = int(annotations.loc[annotations["name"] != "Unknown", "query_mz"].nunique())
    n_total_matches = int((annotations["name"] != "Unknown").sum())
    n_high_conf = int((annotations["confidence"] == "high").sum())

    summary = {
        "database": args.database,
        "adducts": ", ".join(args.adducts),
        "n_queries": n_queries,
        "n_annotated": n_annotated,
        "n_total_matches": n_total_matches,
        "n_high_conf": n_high_conf,
        "annotation_rate": float(n_annotated / max(n_queries, 1) * 100),
    }

    params = {
        "database": args.database,
        "ppm": args.ppm,
        "adducts": ", ".join(args.adducts),
    }

    write_report(output_dir, summary, input_file, params)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(
        f"Annotation complete: {summary['n_annotated']}/{summary['n_queries']} features "
        f"({summary['annotation_rate']:.1f}%), {n_total_matches} total matches"
    )


if __name__ == "__main__":
    main()
