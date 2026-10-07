"""Temporary R survival execution and result conversion."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

def _run_survival_r(
    expr_df: pd.DataFrame,
    clinical_df: pd.DataFrame,
    gene_list: list[str],
    cutoff_method: str = "median",
    *, scripts_dir: Path,
) -> list[dict]:
    """Run survival analysis via R survival package.

    Returns list of result dicts per gene (same format as analyze_gene()).
    """
    import tempfile
    from skills.bulkrna._lib.r_matrix import require_r, write_matrix
    from skills._sdk.r_script_runner import RScriptRunner

    require_r(["survival", "Matrix"])

    runner = RScriptRunner(scripts_dir=scripts_dir)

    with tempfile.TemporaryDirectory(prefix="omicsclaw_surv_") as tmpdir:
        tmpdir = Path(tmpdir)
        write_matrix(expr_df, tmpdir)
        clinical_df.to_csv(tmpdir / "clinical.csv", index=False)

        output_dir = tmpdir / "output"
        output_dir.mkdir()

        runner.run_script(
            "bulkrna_survival.R",
            args=[
                str(tmpdir),
                str(tmpdir / "clinical.csv"),
                str(output_dir),
                ",".join(gene_list),
                cutoff_method,
            ],
            expected_outputs=["survival_results.csv", "km_data.csv"],
            output_dir=output_dir,
        )

        results_df = pd.read_csv(output_dir / "survival_results.csv", dtype={"gene": str})
        km_data = pd.read_csv(output_dir / "km_data.csv", dtype={"gene": str})

    # Convert R results to Python dict format
    results = []
    for _, row in results_df.iterrows():
        gene = row["gene"]

        # Extract KM curve data for this gene
        km_high = km_data[(km_data["gene"] == gene) & (km_data["group"] == "high")]
        km_low = km_data[(km_data["gene"] == gene) & (km_data["group"] == "low")]
        if km_high.empty or km_low.empty:
            raise RuntimeError("R survival returned no KM curve for " + str(gene))

        results.append({
            "gene": gene,
            "status": "ok",
            "cutoff": float(row["cutoff"]),
            "n_high": int(row["n_high"]),
            "n_low": int(row["n_low"]),
            "log_rank_chi2": float(row["log_rank_chi2"]),
            "log_rank_pval": float(row["log_rank_pval"]),
            "median_survival_high": None if pd.isna(row.get("median_high")) else float(row["median_high"]),
            "median_survival_low": None if pd.isna(row.get("median_low")) else float(row["median_low"]),
            "median_high_note": str(row.get("median_high_note", "")),
            "median_low_note": str(row.get("median_low_note", "")),
            "hazard_ratio": float(row["hr"]),
            "hr_lower": float(row["hr_lower"]),
            "hr_upper": float(row["hr_upper"]),
            "km_high": (km_high["time"].values, km_high["surv"].values),
            "km_low": (km_low["time"].values, km_low["surv"].values),
        })

    return results
