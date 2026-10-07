"""Fixed inputs and public-library parity for spatial labels and statistics."""
from pathlib import Path


def spatial_input(path: Path) -> None:
    import scanpy as sc
    from skills._sdk.notebook import load_demo

    adata = load_demo("spatial_synthetic")
    adata.obs["leiden"] = adata.obs["domain_ground_truth"].astype("category")
    adata.layers["counts"] = adata.X.copy()
    sc.pp.normalize_total(adata)
    sc.pp.log1p(adata)
    sc.pp.pca(adata, n_comps=30, random_state=0)
    sc.pp.neighbors(adata, random_state=0)
    sc.tl.umap(adata, random_state=0)
    adata.write_h5ad(path)


_ENV = {name: "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS")}
def register(Case, Skill):
    return {
        "spatial-annotate": Skill("skills/spatial/spatial-annotate/spatial_annotate.py", "tests.parity.spatial_s3:annotation", {
            "default": Case((), input=spatial_input, environment=_ENV),
            "ttest": Case(("--marker-rank-method", "t-test"), input=spatial_input, environment=_ENV),
        }),
        "spatial-domains": Skill("skills/spatial/spatial-domains/spatial_domains.py", "tests.parity.spatial_s3:domains", {
            "default": Case((), input=spatial_input, environment=_ENV),
            "expression": Case(("--spatial-weight", "0"), input=spatial_input, environment=_ENV),
        }),
        "spatial-microenvironment-subset": Skill("skills/spatial/spatial-microenvironment-subset/spatial_microenvironment_subset.py", "tests.parity.spatial_s3:subset", {
            "default": Case(("--center-key", "leiden", "--center-values", "domain_0", "--radius-native", "1.5"), input=spatial_input, environment=_ENV),
        }),
        "spatial-statistics": Skill("skills/spatial/spatial-statistics/spatial_statistics.py", "tests.parity.spatial_s3:statistics", {
            "default": Case((), input=spatial_input, environment=_ENV),
            "network": Case(("--analysis-type", "network_properties"), input=spatial_input, environment=_ENV),
        }),
    }


def annotation(case, *, input_path):
    import scanpy as sc
    from skills._sdk.notebook import load_skill
    api = load_skill("spatial-annotate")
    adata = sc.read_h5ad(input_path)
    api.annotate(adata, rank_method="t-test" if case == "ttest" else "wilcoxon")
    return {"adata": adata, "tables": {"annotation_summary.csv": api.cell_type_counts(adata)}}


def domains(case, *, input_path):
    import scanpy as sc
    from skills._sdk.notebook import load_skill
    api = load_skill("spatial-domains")
    adata = sc.read_h5ad(input_path)
    api.identify(adata, spatial_weight=0 if case == "expression" else 0.3)
    return {"adata": adata, "tables": {"domain_summary.csv": api.domain_counts(adata)}}


def subset(case, *, input_path):
    import scanpy as sc
    from skills._sdk.notebook import load_skill
    api = load_skill("spatial-microenvironment-subset")
    adata = api.subset(sc.read_h5ad(input_path), center_key="leiden", center_values=["domain_0"], radius_native=1.5)
    return {"tables": {"selected_observations.csv": api.selection_table(adata)}}


def statistics(case, *, input_path):
    import scanpy as sc
    from skills._sdk.notebook import load_skill
    api = load_skill("spatial-statistics")
    adata = sc.read_h5ad(input_path)
    api.analyze(adata, analysis_type="network_properties" if case == "network" else "neighborhood_enrichment")
    filename = "network_summary.csv" if case == "network" else "neighborhood_pairs.csv"
    name = "results_df" if case == "network" else "pair_summary_df"
    return {"adata": adata, "tables": {filename: api.results_table(adata, name=name)}}
