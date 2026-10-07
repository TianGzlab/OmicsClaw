"""Record what a pilot skill's CLI produces, and compare later runs with it value by value.

A snapshot keeps the values that matter, not the bytes: every CSV under
``tables/``, each categorical ``obs`` column of ``processed.h5ad`` as
``obs_name,label``, the numeric ``obs`` columns, the ``obsm`` keys with their
shapes, the ``summary`` of ``result.json`` without times and paths, and the
names of the files under ``figures/``.

Snapshots live in ``tests/parity/golden/<skill>/<case>/``, which is not
committed: they only mean something on the machine and in the environment
that recorded them.

    python -m tests.parity.snapshot record sc-clustering --case default
    python -m tests.parity.snapshot compare sc-clustering --case default --output <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GOLDEN = Path(__file__).resolve().parent / "golden"
RTOL = 1e-6
_THREAD_VARIABLES = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS")

@dataclass(frozen=True)
class Case:
    """CLI arguments, reasoned exclusions and an optional fixed-input writer.

    Exclusion keys name a snapshot file, ``file.csv:column``, a
    ``summary.json:key.path`` or ``figures/filename``. An input writer
    receives a Path and writes one reproducible .h5ad there.
    Environment entries override inherited values; None removes a variable.
    """

    args: tuple[str, ...]
    exclude: dict[str, str] = field(default_factory=dict)
    input: Callable[[Path], None] | None = None
    environment: dict[str, str | None] = field(default_factory=dict)
    root_tables: tuple[str, ...] = ()


@dataclass(frozen=True)
class Skill:
    script: str
    api_runner: str | None
    cases: dict[str, Case]
    legacy_sigkill: bool = False

def _integration_input(path: Path) -> None:
    """Use the old demo's preprocessing with one seeded batch assignment."""
    import numpy as np
    import scanpy as sc
    from skills.singlecell._lib.io import load_repo_demo_data

    adata, _ = load_repo_demo_data("pbmc3k_raw")
    adata.layers["counts"] = adata.X.copy()
    sc.pp.normalize_total(adata)
    sc.pp.log1p(adata)
    adata.raw = adata.copy()
    sc.pp.highly_variable_genes(adata, n_top_genes=2000, layer="counts", flavor="seurat_v3")
    sc.pp.pca(adata)
    processed, _ = load_repo_demo_data("pbmc3k_processed")
    adata.obs["louvain"] = processed.obs.reindex(adata.obs_names)["louvain"].astype(str)
    adata.obs["batch"] = np.random.default_rng(0).choice(["batch1", "batch2"], adata.n_obs)
    adata.write_h5ad(path)


def _drug_response_input(path: Path) -> None:
    """PBMC expression with two explicit comparison groups for the old CLI."""
    from skills.singlecell._lib.io import load_repo_demo_data

    adata, _ = load_repo_demo_data('pbmc3k_processed')
    adata = adata.raw.to_adata()
    adata.obs['comparison_group'] = adata.obs['louvain'].astype(str).map(
        lambda value: 'T_cell' if 'T' in value else 'other')
    adata.write_h5ad(path)


_CORRELATION_CORRECTIONS = {
    'tables/diff_regulation.csv': 'Remove fabricated p-values/z/FC and sort by dr_score; retained dr_score/wt_ko_corr are checked by gene in test_perturbation_numeric_parity.py.',
    'figures/pvalue_distribution.png': 'No calibrated p-values exist for correlation edge-removal scores.',
    'summary.json:n_significant': 'No significance test is performed by the descriptive Python method.',
}
_DRUG_EXPRESSION_RENAME = {
    'tables/drug_rankings.csv:Score': 'Rename the descriptive mean to mean_target_expression; keyed values checked in test_perturbation_numeric_parity.py.',
    'tables/drug_rankings.csv:mean_target_expression': 'The same expression mean under its truthful name, not a response prediction.',
}


def _spatial_input(path: Path) -> None:
    from scripts.generate_demo_data import generate_demo_visium

    generate_demo_visium().write_h5ad(path)


def _spatial_multisample_input(path: Path) -> None:
    import numpy as np
    from scripts.generate_demo_data import generate_demo_visium
    from skills._sdk.notebook import load_skill

    data = load_skill('spatial-preprocess').preprocess(generate_demo_visium(), n_top_hvg=50, n_pcs=15)
    data.obs['batch'] = [f'batch_{i % 3}' for i in range(data.n_obs)]
    data.obs['sample'] = [f'sample_{i % 6}' for i in range(data.n_obs)]
    data.obs['condition'] = np.where(np.arange(data.n_obs) % 6 < 3, 'control', 'treated')
    data.write_h5ad(path)


REGISTRY = {
    "spatial-register": Skill("skills/spatial/spatial-register/spatial_register.py", "api_spatial_register", {
        "default": Case(("--slice-key", "batch"), input=_spatial_multisample_input,
                        environment={key: "1" for key in _THREAD_VARIABLES}, exclude={
                            key: "Fix reference-by-source transport orientation and reject solver failure; old baseline silently returned unaligned coordinates. Unequal-size barycenter regression is in test_api.py."
                            for key in (
                                "summary.json:disparities", "summary.json:mean_disparity",
                                "figures/registration_disparities.png",
                                "tables/registration_metrics.csv:mean_shift",
                                "tables/registration_metrics.csv:median_shift",
                                "tables/registration_metrics.csv:max_shift",
                                "tables/registration_metrics.csv:disparity",
                                "tables/registration_summary.csv:value",
                                "obs_numeric.csv:registration_shift_distance",
                            )}),
    }),
    "spatial-condition": Skill("skills/spatial/spatial-condition/spatial_condition.py", "api_spatial_condition", {
        name: Case(args, input=_spatial_multisample_input,
                   environment={key: "1" for key in _THREAD_VARIABLES})
        for name, args in {"default": ("--pydeseq2-n-cpus", "1", "--sample-key", "sample"),
                           "wilcoxon": ("--method", "wilcoxon", "--sample-key", "sample")}.items()
    }),
    'spatial-integrate': Skill('skills/spatial/spatial-integrate/spatial_integrate.py', 'api_spatial_integrate', {
        name: Case(args, input=_spatial_multisample_input, environment={key: '1' for key in _THREAD_VARIABLES})
        for name, args in {
            'default': (), 'bbknn': ('--method', 'bbknn'), 'scanorama': ('--method', 'scanorama'),
        }.items()
    }),
    'spatial-preprocess': Skill('skills/spatial/spatial-preprocess/spatial_preprocess.py', 'api_spatial_preprocess', {
        'default': Case((), input=_spatial_input, environment={key: '1' for key in _THREAD_VARIABLES}),
        'resolution_sweep': Case(('--n-top-hvg', '50', '--n-pcs', '15', '--n-neighbors', '10',
                                  '--leiden-resolution', '0.8', '--resolutions', '0.4,0.8'),
                                 input=_spatial_input, environment={key: '1' for key in _THREAD_VARIABLES}),
    }),
    'sc-perturb-prep': Skill('skills/singlecell/scrna/sc-perturb-prep/sc_perturb_prep.py', 'api_sc_perturb_prep', {
        'default': Case(('--demo',)), 'keep_multi': Case(('--demo', '--keep-multi-guide')),
    }),
    'sc-perturb': Skill('skills/singlecell/scrna/sc-perturb/sc_perturb.py', 'api_sc_perturb', {
        'default': Case(('--demo',)), 'high_threshold': Case(('--demo', '--logfc-threshold', '2')),
    }),
    'sc-in-silico-perturbation': Skill('skills/singlecell/scrna/sc-in-silico-perturbation/sc_in_silico_perturbation.py', 'api_sc_in_silico_perturbation', {
        'default': Case(('--demo',), exclude=_CORRELATION_CORRECTIONS),
        'top500': Case(('--demo', '--n-top-genes', '500'), exclude=_CORRELATION_CORRECTIONS),
    }),
    'sc-drug-response': Skill('skills/singlecell/scrna/sc-drug-response/sc_drug_response.py', 'api_sc_drug_response', {
        'default': Case(('--demo',), exclude=_DRUG_EXPRESSION_RENAME),
        'two_groups': Case(('--cluster-key', 'comparison_group'), exclude=_DRUG_EXPRESSION_RENAME, input=_drug_response_input),
    }),
    "sc-cytotrace": Skill("skills/singlecell/scrna/sc-cytotrace/sc_cytotrace.py", "api_sc_cytotrace", {
        "default": Case(("--demo",)), "neighbors15": Case(("--demo", "--n-neighbors", "15")),
    }),
    "sc-metacell": Skill("skills/singlecell/scrna/sc-metacell/sc_metacell.py", "api_sc_metacell", {
        "default": Case(("--demo", "--method", "kmeans")),
        "twenty": Case(("--demo", "--method", "kmeans", "--n-metacells", "20")),
    }),
    "sc-pseudotime": Skill("skills/singlecell/scrna/sc-pseudotime/sc_pseudotime.py", "api_sc_pseudotime", {
        "default": Case(("--demo", "--use-rep", "X_pca")),
        "palantir": Case(("--demo", "--use-rep", "X_pca", "--method", "palantir")),
    }),
    "sc-velocity": Skill("skills/singlecell/scrna/sc-velocity/sc_velocity.py", "api_sc_velocity", {
        "default": Case(("--demo",)), "steady_state": Case(("--demo", "--mode", "steady_state")),
    }, legacy_sigkill=True),
    "sc-grn": Skill("skills/singlecell/scrna/sc-grn/sc_grn.py", "api_sc_grn", {
        "default": Case(("--demo",)), "simplified": Case(("--demo", "--allow-simplified-grn")),
    }),
    "sc-pathway-scoring": Skill("skills/singlecell/scrna/sc-pathway-scoring/sc_pathway_scoring.py", "api_sc_pathway_scoring", {
        "aucell_py": Case(("--demo", "--method", "aucell_py")),
        "score_genes_py": Case(("--demo", "--method", "score_genes_py")),
    }),
    "sc-gene-programs": Skill("skills/singlecell/scrna/sc-gene-programs/sc_gene_programs.py", "api_sc_gene_programs", {
        "default": Case(("--demo", "--method", "nmf")),
        "four": Case(("--demo", "--method", "nmf", "--n-programs", "4")),
    }),
    "sc-differential-abundance": Skill("skills/singlecell/scrna/sc-differential-abundance/sc_differential_abundance.py", "api_sc_differential_abundance", {
        "simple": Case(("--demo", "--method", "simple")),
        "milo": Case(("--demo", "--method", "milo")),
    }),
    "sc-cell-communication": Skill("skills/singlecell/scrna/sc-cell-communication/sc_cell_communication.py", "api_sc_cell_communication", {
        "builtin": Case(("--demo",)),
        "liana": Case(("--demo", "--method", "liana"), exclude={
            "tables/lr_interactions.csv:pvalue": "LIANA specificity_rank is not a p-value; now NaN.",
            "tables/lr_interactions.csv:specificity_rank": "Preserve the original rank under its correct name.",
            "tables/top_interactions.csv:pvalue": "LIANA specificity_rank is not a p-value; now NaN.",
            "tables/top_interactions.csv:specificity_rank": "Preserve the original rank under its correct name.",
            "summary.json:n_significant": "Consensus ranks are no longer counted as significant p-values.",
            "summary.json:pvalue_available": "LIANA consensus output does not provide p-values.",
            "summary.json:significance_semantics": "New explanation of LIANA rank semantics.",
            "summary.json:random_state": "Record LIANA's unchanged default seed 1337 explicitly.",
        }),
    }),
    "sc-multi-count": Skill("skills/singlecell/scrna/sc-multi-count/sc_multi_count.py", "api_sc_multi_count", {
        "default": Case(("--demo",)),
        "labels": Case(("--demo", "--sample-id", "control", "--sample-id", "treated")),
    }),
    "scatac-preprocessing": Skill("skills/singlecell/scatac/scatac-preprocessing/scatac_preprocessing.py", "api_scatac_preprocessing", {
        "default": Case(("--demo",)), "lsi20": Case(("--demo", "--n-lsi", "20")),
    }),
    "sc-batch-integration": Skill("skills/singlecell/scrna/sc-batch-integration/sc_integrate.py", "api_sc_batch_integration", {
        # M2's baseline script set these to one; BLAS threading changes Harmony metrics.
        "harmony": Case(("--method", "harmony"), input=_integration_input,
                        environment={key: "1" for key in (*_THREAD_VARIABLES, "NUMEXPR_NUM_THREADS")}),
        "scanorama": Case(("--method", "scanorama"), input=_integration_input),
    }),
    "sc-enrichment": Skill("skills/singlecell/scrna/sc-enrichment/sc_enrichment.py", "api_sc_enrichment", {
        "default": Case(("--demo", "--engine", "python")),
        "gsea": Case(("--demo", "--engine", "python", "--method", "gsea")),
    }),
    "sc-standardize-input": Skill("skills/singlecell/scrna/sc-standardize-input/sc_standardize_input.py", "api_sc_standardize_input", {
        "default": Case(("--demo",)), "human": Case(("--demo", "--species", "human")),
    }),
    "sc-doublet-detection": Skill("skills/singlecell/scrna/sc-doublet-detection/sc_doublet.py", "api_sc_doublet_detection", {
        "default": Case(("--demo",)),
        # Old and new CLIs agree with the baseline when its thread overrides are absent.
        "doubletdetection": Case(("--demo", "--method", "doubletdetection"),
                                  environment={key: None for key in _THREAD_VARIABLES}),
    }),
    "sc-ambient-removal": Skill("skills/singlecell/scrna/sc-ambient-removal/sc_ambient.py", "api_sc_ambient_removal", {
        "default": Case(("--demo",)), "tenth": Case(("--demo", "--contamination", "0.1")),
    }),
    "sc-qc": Skill("skills/singlecell/scrna/sc-qc/sc_qc.py", "api_sc_qc", {
        "default": Case(("--demo",)), "mouse": Case(("--demo", "--species", "mouse")),
    }),
    "sc-preprocessing": Skill("skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py", "api_sc_preprocessing", {
        "default": Case(("--demo",)), "pearson": Case(("--demo", "--method", "pearson_residuals")),
    }),
    "sc-clustering": Skill("skills/singlecell/scrna/sc-clustering/sc_cluster.py", "api_sc_clustering", {
        "default": Case(("--demo",)), "louvain": Case(("--demo", "--cluster-method", "louvain")),
    }),
    "sc-cell-annotation": Skill("skills/singlecell/scrna/sc-cell-annotation/sc_annotate.py", "api_sc_cell_annotation", {
        "default": Case(("--demo",)), "knnpredict": Case(("--demo", "--method", "knnpredict")),
    }),
    "sc-de": Skill("skills/singlecell/scrna/sc-de/sc_de.py", "api_sc_de", {
        "default": Case(("--demo",)), "ttest": Case(("--demo", "--method", "t-test")),
    }),
    "sc-filter": Skill("skills/singlecell/scrna/sc-filter/sc_filter.py", "api_sc_filter", {
        "default": Case(("--demo",)), "pbmc": Case(("--demo", "--tissue", "pbmc")),
    }),
    "sc-markers": Skill("skills/singlecell/scrna/sc-markers/sc_markers.py", "api_sc_markers", {
        "default": Case(("--demo",)), "ttest": Case(("--demo", "--method", "t-test")),
    }),
}
"""One entry per skill; the first five keep their original pilot cases."""

def _load_spatial_cases() -> None:
    from importlib import import_module

    for batch in ("s2", "s3", "s5", "deconv", "communication"):
        module_name = f"tests.parity.spatial_{batch}"
        if (Path(__file__).parent / f"spatial_{batch}.py").exists():
            module = import_module(module_name)
            REGISTRY.update(module.register(Case, Skill))


_load_spatial_cases()


def _load_remaining_cases() -> None:
    from importlib import import_module

    for domain in ("bulkrna", "genomics", "proteomics", "metabolomics", "literature",
                   "bulkrna_read", "bulkrna_r", "bulkrna_network"):
        if (Path(__file__).parent / f"{domain}.py").is_file():
            module = import_module(f"tests.parity.{domain}")
            REGISTRY.update(module.register(Case, Skill))


_load_remaining_cases()

_DROPPED_SUMMARY_KEYS = {"completed_at", "elapsed_seconds", "runtime_seconds", "output_dir", "output_h5ad",
                         "input_file", "standardized_at"}


def golden_dir(skill: str, case: str) -> Path:
    return GOLDEN / skill / case


def child_env() -> dict[str, str]:
    """The environment for a CLI or library run: this one, without the test-only numba switch.

    ``tests/conftest.py`` sets ``NUMBA_DISABLE_JIT=1`` to speed up unit tests;
    a UMAP run without JIT is slow and need not match a snapshot recorded with it.
    """
    env = {k: v for k, v in os.environ.items() if k != "NUMBA_DISABLE_JIT"}
    env.update(PYTHONPATH=str(REPO), PYTHONDONTWRITEBYTECODE="1")
    return env


def case_env(skill: str, case: str) -> dict[str, str]:
    """Match explicit environment constraints of the recorded case."""
    env = child_env()
    for key, value in REGISTRY[skill].cases[case].environment.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


def case_input(skill: str, case: str, scratch: Path) -> Path | None:
    """Use the recorded input, or generate it once for a new recording."""
    entry = REGISTRY[skill].cases[case]
    if entry.input is None:
        return None
    recorded = golden_dir(skill, case) / "input.h5ad"
    if recorded.is_file():
        meta = json.loads((recorded.parent / "meta.json").read_text())
        if hashlib.sha256(recorded.read_bytes()).hexdigest() != meta["input_sha256"]:
            raise ValueError(f"recorded input changed: {recorded}")
        return recorded
    scratch.mkdir(parents=True, exist_ok=True)
    target = scratch / "input.h5ad"
    entry.input(target)
    return target


def run_cli(skill: str, case: str, output: Path, *, python: str | None = None,
            input_path: Path | None = None) -> subprocess.CompletedProcess:
    """Run *skill*'s CLI for *case* into *output* with the given interpreter (default: this one)."""
    env = case_env(skill, case)
    entry = REGISTRY[skill]
    source = input_path or case_input(skill, case, output.parent / "input")
    args = list(entry.cases[case].args)
    if source is not None:
        args += ["--input", str(source)]
    return subprocess.run(
        [python or sys.executable, str(REPO / entry.script), *args, "--output", str(output)],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=3600, start_new_session=True,
    )


def recording_succeeded(skill: str, proc: subprocess.CompletedProcess, output: Path) -> bool:
    """Accept the old velocity CLI's self-kill only after its outputs are complete.

    This exception is for baseline recording. Regression runs require exit 0.
    Recording uses a new temporary output directory for each invocation.
    """
    if proc.returncode == 0:
        return True
    if skill != "sc-velocity" or not REGISTRY[skill].legacy_sigkill or proc.returncode != -signal.SIGKILL:
        return False
    import anndata
    import pandas as pd
    from skills._sdk.result import RESULT_SCHEMA

    try:
        result = json.loads((output / "result.json").read_text())
        types = {"str": str, "dict": dict}
        if any(not isinstance(result.get(key), types[kind]) for key, kind in RESULT_SCHEMA["required"].items()):
            return False
        if any(not result[key] for key in RESULT_SCHEMA["non_empty"]):
            return False
        if result["skill"] != skill or result.get("status", "ok") != "ok":
            return False
        if result["data"]["output_h5ad"] != "processed.h5ad":
            return False
        outputs = result["data"]["output_files"]
        for value in [outputs["processed_h5ad"], *outputs["compatibility_aliases"]]:
            path = Path(value)
            if not path.is_absolute():
                path = output / path
            path.resolve().relative_to(output.resolve())
            if not path.is_file() or path.stat().st_size == 0:
                return False
        adata = anndata.read_h5ad(output / "processed.h5ad")
        if adata.shape != (result["summary"]["n_cells"], result["summary"]["n_genes"]):
            return False
        for name in ("velocity_summary.csv", "velocity_cells.csv", "top_velocity_genes.csv"):
            table = pd.read_csv(output / "tables" / name)
            if name == "velocity_cells.csv" and len(table) != adata.n_obs:
                return False
        if not (output / "report.md").read_text().strip():
            return False
        manifest = json.loads((output / "figures" / "manifest.json").read_text())
        for plot in manifest["plots"]:
            path = output / "figures" / plot["filename"]
            path.resolve().relative_to(output.resolve())
            if not path.is_file() or path.stat().st_size == 0:
                return False
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return True


def _clean_summary(value):
    if isinstance(value, dict):
        return {k: _clean_summary(v) for k, v in value.items() if k not in _DROPPED_SUMMARY_KEYS}
    if isinstance(value, list):
        return [_clean_summary(v) for v in value]
    if isinstance(value, str) and (value.startswith("/") or value.startswith(str(REPO))):
        return "<path>"
    return value


def obs_frames(adata):
    """The categorical and numeric ``obs`` columns of *adata*, keyed by ``obs_name``."""
    import pandas as pd
    from pandas.api import types

    labels: dict[str, pd.Series] = {}
    numeric = pd.DataFrame(index=adata.obs_names.astype(str))
    for column in adata.obs.columns:
        series = adata.obs[column]
        if types.is_bool_dtype(series) or not types.is_numeric_dtype(series):
            labels[str(column)] = series.astype(str).set_axis(adata.obs_names.astype(str))
        else:
            numeric[str(column)] = series.to_numpy()
    numeric.index.name = "obs_name"
    return labels, numeric


def extract(output: Path, target: Path, *, root_tables: tuple[str, ...] = ()) -> None:
    """Write the snapshot of the CLI output in *output* to *target*."""
    import anndata

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    tables = output / "tables"
    if tables.is_dir():
        for csv in sorted(tables.rglob("*.csv")):
            destination = target / "tables" / csv.relative_to(tables)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(csv, destination)
    for name in root_tables:
        if Path(name).name != name or not name.endswith('.csv'):
            raise ValueError('Root table names must be CSV basenames')
        destination = target / 'tables' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output / name, destination)
    h5ad = output / "processed.h5ad"
    if h5ad.is_file():
        adata = anndata.read_h5ad(h5ad)
        labels, numeric = obs_frames(adata)
        for column, series in labels.items():
            path = target / "obs_labels" / f"{column}.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            series.rename("label").rename_axis("obs_name").to_csv(path)
        numeric.to_csv(target / "obs_numeric.csv")
        (target / "obsm.json").write_text(
            json.dumps({str(k): list(v.shape) for k, v in adata.obsm.items()}, indent=2, sort_keys=True) + "\n"
        )
    result = json.loads((output / "result.json").read_text())
    (target / "summary.json").write_text(
        json.dumps(_clean_summary(result.get("summary", {})), indent=2, sort_keys=True, default=str) + "\n"
    )
    figures = output / "figures"
    names = sorted(p.relative_to(figures).as_posix() for p in figures.rglob("*") if p.is_file()) if figures.is_dir() else []
    (target / "figures.json").write_text(json.dumps(names, indent=2) + "\n")


def _close(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
            return True
        return math.isclose(a, b, rel_tol=RTOL, abs_tol=0.0) or a == b
    return a == b


def compare_values(expected, actual, where: str) -> list[str]:
    """Differences between two JSON-like values, floats compared within ``RTOL``."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        problems = []
        if set(expected) != set(actual):
            problems.append(f"{where}: keys differ: missing {sorted(set(expected) - set(actual))}, "
                            f"extra {sorted(set(actual) - set(expected))}")
        for key in sorted(set(expected) & set(actual)):
            problems += compare_values(expected[key], actual[key], f"{where}.{key}")
        return problems
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return [f"{where}: length {len(expected)} != {len(actual)}"]
        problems = []
        for index, (e, a) in enumerate(zip(expected, actual)):
            problems += compare_values(e, a, f"{where}[{index}]")
        return problems
    return [] if _close(expected, actual) else [f"{where}: {expected!r} != {actual!r}"]


def compare_frames(expected, actual, where: str, *, structure_only: bool = False,
                   column_rtol: dict[str, float] | None = None) -> list[str]:
    """Value-by-value differences between two tables: same columns and rows, floats within ``RTOL``."""
    import numpy as np
    from pandas.api import types

    if list(expected.columns) != list(actual.columns):
        return [f"{where}: columns {list(expected.columns)} != {list(actual.columns)}"]
    if expected.shape != actual.shape:
        return [f"{where}: shape {expected.shape} != {actual.shape}"]
    problems = []
    for column in expected.columns:
        left, right = expected[column], actual[column]
        if structure_only:
            if types.is_numeric_dtype(left) != types.is_numeric_dtype(right):
                problems.append(f"{where}.{column}: numeric and non-numeric")
            elif not types.is_numeric_dtype(left) and set(left.astype(str)) != set(right.astype(str)):
                problems.append(f"{where}.{column}: label sets differ")
            continue
        if types.is_float_dtype(left) or types.is_float_dtype(right):
            if not (types.is_numeric_dtype(left) and types.is_numeric_dtype(right)):
                problems.append(f"{where}.{column}: numeric and non-numeric")
                continue
            rtol = (column_rtol or {}).get(column, RTOL)
            if not np.allclose(left.to_numpy(float), right.to_numpy(float), rtol=rtol, atol=0.0, equal_nan=True):
                bad = int((~np.isclose(left.to_numpy(float), right.to_numpy(float), rtol=rtol, atol=0.0,
                                       equal_nan=True)).sum())
                problems.append(f"{where}.{column}: {bad} values differ beyond rtol {rtol}")
        elif not (left.astype(str).to_numpy() == right.astype(str).to_numpy()).all():
            bad = int((left.astype(str).to_numpy() != right.astype(str).to_numpy()).sum())
            problems.append(f"{where}.{column}: {bad} values differ")
    return problems


def compare_labels(expected, actual, where: str, *, structure_only: bool = False) -> list[str]:
    """Differences between two ``obs_name -> label`` series."""
    if set(expected.index) != set(actual.index):
        return [f"{where}: cells differ ({len(set(expected.index) ^ set(actual.index))} not shared)"]
    actual = actual.reindex(expected.index)
    if structure_only:
        return [f"{where}: label sets differ"] if set(expected.astype(str)) != set(actual.astype(str)) else []
    bad = int((expected.astype(str).to_numpy() != actual.astype(str).to_numpy()).sum())
    return [f"{where}: {bad} labels differ"] if bad else []


def _structure(value):
    if isinstance(value, dict):
        return {key: _structure(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_structure(item) for item in value]
    return "number" if isinstance(value, (int, float)) and not isinstance(value, bool) else type(value).__name__


def compare(golden: Path, snapshot: Path, *, exclude: dict[str, str] | None = None,
            structure_only: bool = False) -> list[str]:
    """Every difference between a recorded snapshot and a new one."""
    import pandas as pd

    exclude = exclude or {}
    if any(not reason.strip() for reason in exclude.values()):
        raise ValueError("each parity exclusion needs a reason")
    problems: list[str] = []
    for name in ("summary.json", "figures.json", "obsm.json"):
        if name in exclude:
            continue
        left, right = golden / name, snapshot / name
        if left.exists() != right.exists():
            problems.append(f"{name}: present in only one snapshot")
        elif left.exists():
            left_value, right_value = json.loads(left.read_text()), json.loads(right.read_text())
            if name == "figures.json":
                left_value, right_value = ([item for item in value if f"figures/{item}" not in exclude]
                                           for value in (left_value, right_value))
            else:
                for key in exclude:
                    if key.startswith(f"{name}:"):
                        parts = key.split(":", 1)[1].split(".")
                        for value in (left_value, right_value):
                            for part in parts[:-1]:
                                value = value.get(part, {}) if isinstance(value, dict) else {}
                            if isinstance(value, dict):
                                value.pop(parts[-1], None)
            if structure_only and name == "summary.json":
                left_value, right_value = _structure(left_value), _structure(right_value)
            problems += compare_values(left_value, right_value, name)
    for folder in ("tables", "obs_labels"):
        expected = {p.relative_to(golden / folder).as_posix() for p in (golden / folder).rglob("*.csv")} \
            if (golden / folder).is_dir() else set()
        actual = {p.relative_to(snapshot / folder).as_posix() for p in (snapshot / folder).rglob("*.csv")} \
            if (snapshot / folder).is_dir() else set()
        expected = {name for name in expected if f"{folder}/{name}" not in exclude}
        actual = {name for name in actual if f"{folder}/{name}" not in exclude}
        if expected != actual:
            problems.append(f"{folder}: files differ: missing {sorted(expected - actual)}, extra {sorted(actual - expected)}")
        for relative in sorted(expected & actual):
            frames = []
            for path in (golden / folder / relative, snapshot / folder / relative):
                try:
                    frames.append(pd.read_csv(path))
                except pd.errors.EmptyDataError:
                    frames.append(pd.DataFrame())
            left, right = frames
            columns = [key.split(":", 1)[1] for key in exclude if key.startswith(f"{folder}/{relative}:")]
            left, right = (frame.drop(columns=columns, errors="ignore") for frame in (left, right))
            if folder == "obs_labels":
                problems += compare_labels(left.set_index("obs_name")["label"], right.set_index("obs_name")["label"],
                                           f"{folder}/{relative}", structure_only=structure_only)
            else:
                problems += compare_frames(left, right, f"{folder}/{relative}", structure_only=structure_only)
    left, right = golden / "obs_numeric.csv", snapshot / "obs_numeric.csv"
    if "obs_numeric.csv" in exclude:
        return problems
    if left.exists() and right.exists():
        columns = [key.split(":", 1)[1] for key in exclude if key.startswith("obs_numeric.csv:")]
        problems += compare_frames(pd.read_csv(left).drop(columns=columns, errors="ignore"),
                                   pd.read_csv(right).drop(columns=columns, errors="ignore"), "obs_numeric.csv",
                                   structure_only=structure_only)
    elif left.exists() != right.exists():
        problems.append("obs_numeric.csv: present in only one snapshot")
    return problems


def compare_output(skill: str, case: str, output: Path) -> list[str]:
    """Differences between the recorded snapshot of *case* and the CLI output in *output*."""
    with tempfile.TemporaryDirectory(prefix="parity-") as scratch:
        snapshot = Path(scratch) / "snapshot"
        extract(output, snapshot, root_tables=REGISTRY[skill].cases[case].root_tables)
        return compare(golden_dir(skill, case), snapshot, **comparison_options(skill, case))


def comparison_options(skill: str, case: str) -> dict:
    meta_path = golden_dir(skill, case) / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
    exclude = REGISTRY[skill].cases[case].exclude
    differences = meta.get("repeat_differences", [])
    prefixes = tuple(key.replace(":", ".", 1) + ": " for key in exclude if ":" in key)
    only_excluded_columns_vary = bool(differences) and all(
        difference.startswith(prefixes) for difference in differences)
    return {"exclude": exclude,
            "structure_only": meta.get("deterministic") is False and not only_excluded_columns_vary}


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def record(skill: str, case: str) -> Path:
    """Record two CLI runs and mark value differences as nondeterministic."""
    with tempfile.TemporaryDirectory(prefix=f"parity-{skill}-") as scratch:
        scratch = Path(scratch)
        source = case_input(skill, case, scratch / "input")
        snapshots = []
        for number in range(2):
            output = scratch / f"out-{number}"
            proc = run_cli(skill, case, output, input_path=source)
            if not recording_succeeded(skill, proc, output):
                raise SystemExit(f"{skill} {case} failed:\n{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}")
            path = scratch / f"snapshot-{number}"
            extract(output, path, root_tables=REGISTRY[skill].cases[case].root_tables)
            snapshots.append(path)
        differences = compare(*snapshots, exclude=REGISTRY[skill].cases[case].exclude)
        target = golden_dir(skill, case)
        input_hash = hashlib.sha256(source.read_bytes()).hexdigest() if source else None
        if source is not None:
            shutil.copy2(source, snapshots[0] / "input.h5ad")
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(snapshots[0], target)
    from importlib.metadata import version

    meta = {
        "skill": skill, "case": case, "args": REGISTRY[skill].cases[case].args, "python": sys.executable,
        "python_version": platform.python_version(), "git_commit": _git_commit(),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "versions": {name: version(name) for name in ("scanpy", "anndata", "numpy", "pandas")},
        "runs": 2, "deterministic": not differences, "repeat_differences": differences,
        "uncertainty_reason": "; ".join(differences) if differences else None,
        "input_sha256": input_hash, "exclude": REGISTRY[skill].cases[case].exclude,
        "environment": {key: case_env(skill, case).get(key)
                        for key in (*_THREAD_VARIABLES, "NUMEXPR_NUM_THREADS", "PYTHONHASHSEED")},
    }
    (target / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.parity.snapshot")
    commands = parser.add_subparsers(dest="command", required=True)
    rec = commands.add_parser("record")
    rec.add_argument("skill", choices=sorted(REGISTRY))
    rec.add_argument("--case", required=True)
    cmp_ = commands.add_parser("compare")
    cmp_.add_argument("skill", choices=sorted(REGISTRY))
    cmp_.add_argument("--case", required=True)
    cmp_.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.case not in REGISTRY[args.skill].cases:
        parser.error(f"{args.skill} has cases {sorted(REGISTRY[args.skill].cases)}")
    if args.command == "record":
        print(record(args.skill, args.case))
        return 0
    problems = compare_output(args.skill, args.case, args.output)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
