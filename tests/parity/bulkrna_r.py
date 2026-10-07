"""Recorded R-primary bulk RNA CLI and public library comparisons."""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def register(Case, Skill):
    entries = {f"bulkrna-{name}": Skill(
        f"skills/bulkrna/bulkrna-{name}/bulkrna_{name.replace('-', '_')}.py",
        "tests.parity.bulkrna_r:" + name.replace("-", "_"),
        {"default": Case(("--demo",))})
        for name in ("batch-correction", "survival", "coexpression")}
    reason = ("PCA uses signed log2(1+abs(x)) so legal negative ComBat corrections do not cause NaN/SVD failure; "
              "corrected expression and the pre-correction metric remain strictly compared.")
    entries["bulkrna-batch-correction"] = Skill(
        "skills/bulkrna/bulkrna-batch-correction/bulkrna_batch_correction.py",
        "tests.parity.bulkrna_r:batch_correction",
        {"default": Case(("--demo",), exclude={"summary.json:silhouette_after": reason,
                                              "tables/batch_metrics.csv:after": reason})})
    return entries


def batch_correction(case, *, input_path=None):
    from skills._sdk.notebook import load_skill
    api = load_skill("bulkrna-batch-correction")
    data = pd.read_csv(ROOT / "examples/demo_bulkrna_batch_expr.csv", index_col=0)
    metadata = pd.read_csv(ROOT / "examples/demo_bulkrna_batch_info.csv")
    result = api.correct(data, batches=metadata)
    summary = api.run_info(result)["summary"]
    output = result.reset_index().rename(columns={"index": "Unnamed: 0"})
    metrics = pd.DataFrame([{"metric": "silhouette_score", "before": summary["silhouette_before"],
                             "after": summary["silhouette_after"]}])
    return {"tables": {"corrected_expression.csv": output, "batch_metrics.csv": metrics}, "summary": summary}


def survival(case, *, input_path=None):
    from skills._sdk.notebook import load_skill
    api = load_skill("bulkrna-survival")
    data = pd.read_csv(ROOT / "examples/demo_bulkrna_survival_expr.csv", index_col=0)
    metadata = pd.read_csv(ROOT / "examples/demo_bulkrna_survival_clinical.csv")
    result = api.analyze(data, clinical=metadata, genes=list(data.index[:8]))
    return {"tables": {"survival_results.csv": result}, "summary": api.run_info(result)["summary"]}


def coexpression(case, *, input_path=None):
    from skills._sdk.notebook import load_skill
    api = load_skill("bulkrna-coexpression")
    data = pd.read_csv(ROOT / "examples/demo_bulkrna_counts.csv", index_col=0)
    result = api.analyze(data)
    summary = api.run_info(result)["summary"]
    summary.pop("module_assignments")
    summary["module_assignment_count"] = len(result)
    hubs = api.hub_genes(result)
    hubs = hubs.assign(rank=hubs.groupby("module").cumcount() + 1)[["module", "rank", "gene"]]
    return {"tables": {"module_assignments.csv": result.sort_values(["module", "gene"]).reset_index(drop=True),
                       "hub_genes.csv": hubs, "threshold_fit.csv": api.threshold_fit(result)},
            "summary": summary}
