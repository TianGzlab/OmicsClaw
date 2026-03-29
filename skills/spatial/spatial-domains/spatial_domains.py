#!/usr/bin/env python3
"""Spatial Domains — identify tissue regions and spatial niches.

Supports multiple algorithms with distinct strengths:
  - leiden:   Graph-based clustering with spatial-weighted neighbors (default, fast)
  - louvain:  Classic graph-based clustering (requires: pip install louvain)
  - spagcn:   Spatial Graph Convolutional Network (integrates histology)
  - stagate:  Graph attention auto-encoder (PyTorch Geometric)
  - graphst:  Self-supervised contrastive learning (PyTorch)
  - banksy:   Explicit spatial feature augmentation (interpretable)
  - cellcharter:  Neighborhood-aggregated GMM clustering (CSOgroup/cellcharter)

Usage:
    python spatial_domains.py --input <preprocessed.h5ad> --output <dir>
    python spatial_domains.py --demo --output <dir>
    python spatial_domains.py --input <file> --method spagcn --n-domains 7 --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import scanpy as sc

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)
from skills.spatial._lib.adata_utils import get_spatial_key, store_analysis_metadata
from skills.spatial._lib.domains import (
    SUPPORTED_METHODS,
    dispatch_method,
    refine_spatial_domains,
)
from skills.spatial._lib.viz import VizParams, plot_features
from skills.spatial._lib.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-domains"
SKILL_VERSION = "0.4.0"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path) -> list[str]:
    """Generate spatial domain map and UMAP domain plot."""
    figures = []
    spatial_key = get_spatial_key(adata)

    if spatial_key and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = adata.obsm[spatial_key]

    domain_col = "spatial_domain" if "spatial_domain" in adata.obs.columns else None
    if domain_col is None:
        logger.warning("No 'spatial_domain' column found; skipping domain figures")
        return figures

    import matplotlib.pyplot as plt

    if spatial_key is not None:
        try:
            import squidpy as sq
            # We enforce use of squidpy's robust semantic scatter plotter to avoid manual point-size tuning
            sq.pl.spatial_scatter(
                adata,
                color=domain_col,
                spatial_key="spatial",
                palette="tab20",
                title="Spatial Domains",
                figsize=(8, 8),
            )
            fig = plt.gcf()
            p = save_figure(fig, output_dir, "spatial_domains.png")
            figures.append(str(p))
            plt.close(fig)
        except Exception as exc:
            logger.warning("squidpy.pl.spatial_scatter failed (%s). Falling back to sc.pl.embedding", exc)
            try:
                sc.pl.embedding(
                    adata,
                    basis="spatial",
                    color=domain_col,
                    palette="tab20",
                    title="Spatial Domains",
                    show=False,
                )
                fig = plt.gcf()
                p = save_figure(fig, output_dir, "spatial_domains.png")
                figures.append(str(p))
                plt.close(fig)
            except Exception as exc2:
                logger.warning("Could not generate spatial domain figure: %s", exc2)

    if "X_umap" not in adata.obsm:
        try:
            sc.tl.umap(adata)
        except Exception as exc:
            logger.warning("Could not compute UMAP: %s", exc)

    if "X_umap" in adata.obsm:
        try:
            sc.pl.umap(
                adata,
                color=domain_col,
                palette="tab20",
                title="UMAP — Spatial Domains",
                show=False,
            )
            fig = plt.gcf()
            p = save_figure(fig, output_dir, "umap_domains.png")
            figures.append(str(p))
            plt.close(fig)
        except Exception as exc:
            logger.warning("Could not generate UMAP domain figure: %s", exc)

    return figures


def _generate_next_steps(summary: dict, n_cells: int | None = None) -> list[str]:
    """Generate actionable next-step suggestions based on actual results."""
    steps = []
    n_domains = summary.get("n_domains", 0)
    method = summary.get("method", "")
    counts = summary.get("domain_counts", {})
    total = sum(counts.values()) if counts else 0

    if n_domains > 15:
        steps.append(
            f"- **Many domains detected ({n_domains})**: Consider lowering "
            "`--resolution` or `--n-domains` for coarser partitioning."
        )
    elif n_domains < 3:
        steps.append(
            f"- **Few domains detected ({n_domains})**: Consider raising "
            "`--resolution` or `--n-domains` for finer partitioning."
        )

    if total > 0:
        max_domain = max(counts.values())
        max_pct = max_domain / total * 100
        if max_pct > 60:
            dominant = [k for k, v in counts.items() if v == max_domain][0]
            steps.append(
                f"- **Domain {dominant} is dominant ({max_pct:.0f}%)**: "
                "This may indicate a batch effect, under-clustering, or "
                "preprocessing issue."
            )

    if n_cells is not None and n_cells > 30000 and method in ("graphst", "spagcn", "stagate"):
        steps.append(
            f"- **Large dataset ({n_cells:,} spots)**: If runtime was long, "
            "reduce `--epochs` in subsequent runs."
        )

    if method == "graphst" and (n_cells is None or n_cells > 5000):
        steps.append(
            "- **GraphST labels can be speckled/noisy on large tissue sections**: "
            "try `--refine` for KNN spatial smoothing, or increase `--epochs` "
            "(e.g., 100-200) for more stable domains."
        )

    if method in ("leiden", "louvain") and n_domains >= 5:
        steps.append(
            "- Consider running downstream `spatial-de` to find marker genes "
            "for each domain."
        )

    return steps


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict,
                 current_params: dict | None = None, n_cells: int | None = None) -> None:
    """Write report.md, result.json, tables, reproducibility."""
    header = generate_report_header(
        title="Spatial Domain Identification Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Domains identified": str(summary["n_domains"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Domains identified**: {summary['n_domains']}",
    ]
    if "resolution" in summary:
        body_lines.append(f"- **Leiden resolution**: {summary['resolution']}")
    if "n_domains_requested" in summary:
        body_lines.append(f"- **Domains requested**: {summary['n_domains_requested']}")
    if n_cells is not None:
        body_lines.append(f"- **Total cells/spots**: {n_cells:,}")

    # Running parameters (for reproducibility)
    if current_params:
        body_lines.append("")
        body_lines.append("### Running Parameters\n")
        for k, v in current_params.items():
            if k != "method":
                body_lines.append(f"- `{k}`: **{v}**")

    # Actionable next-step suggestions based on actual results
    next_steps = _generate_next_steps(summary, n_cells)
    if next_steps:
        body_lines.append("")
        body_lines.append("### 💡 Next Steps\n")
        body_lines.extend(next_steps)

    body_lines.extend([
        "",
        "### Domain sizes\n",
        "| Domain | Cells | Proportion |",
        "|--------|-------|------------|",
    ])

    total_cells = sum(summary["domain_counts"].values())
    for domain, count in sorted(
        summary["domain_counts"].items(),
        key=lambda x: int(x[0]) if x[0].isdigit() else x[0],
    ):
        pct = count / total_cells * 100 if total_cells > 0 else 0
        body_lines.append(f"| {domain} | {count} | {pct:.1f}% |")

    body_lines.append("")
    body_lines.append("## Parameters\n")
    for k, v in params.items():
        if v is not None:
            body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, skill=SKILL_NAME, version=SKILL_VERSION,
                      summary=summary, data={"params": params, **summary}, input_checksum=checksum)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    rows = []
    for domain, count in summary["domain_counts"].items():
        pct = count / total_cells * 100 if total_cells > 0 else 0
        rows.append({"domain": domain, "n_cells": count, "proportion": round(pct, 2)})
    pd.DataFrame(rows).to_csv(tables_dir / "domain_summary.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    # Repro command should reflect the actually used method parameters and be
    # runnable from any location when OmicsClaw is installed.
    run_params = current_params or params
    cmd = "oc run spatial-domain-identification --input <input.h5ad> --output <output_dir>"
    for k, v in run_params.items():
        if k == "method" and v:
            cmd += f" --method {v}"
            continue
        if v is not None and not isinstance(v, bool):
            cmd += f" --{k.replace('_', '-')} {v}"
        elif isinstance(v, bool) and v:
            cmd += f" --{k.replace('_', '-')}"

    command_lines = [
        "#!/bin/bash",
        "set -euo pipefail",
        "",
        "# Re-run this analysis with the same key parameters.",
        "# Replace placeholders before running.",
        cmd,
        "",
    ]
    (repro_dir / "commands.sh").write_text("\n".join(command_lines))

    try:
        from importlib.metadata import version as _get_version
    except ImportError:
        from importlib_metadata import version as _get_version  # type: ignore
    method = str(params.get("method", "")).lower()

    def _pkg_line(candidates: list[str]) -> str:
        for pkg in candidates:
            try:
                return f"{pkg}=={_get_version(pkg)}"
            except Exception:
                continue
        # Keep the first candidate as the canonical package name in fallback output.
        return f"{candidates[0]}=?"

    # Base dependencies needed for all methods in this skill.
    package_groups: list[list[str]] = [
        ["scanpy"],
        ["anndata"],
        ["squidpy"],
        ["numpy"],
        ["pandas"],
        ["matplotlib"],
        ["scikit-learn"],
    ]

    # Method-specific dependencies (minimal & accurate, avoids unrelated packages).
    # Custom mappings for methods requiring special package names or extra dependencies.
    method_packages: dict[str, list[list[str]]] = {
        "leiden": [["igraph"], ["leidenalg"]],
        "louvain": [["igraph"], ["louvain"]],
        "spagcn": [["torch"], ["SpaGCN"]],
        "stagate": [["torch"], ["torch-geometric", "torch_geometric"]],
        "graphst": [["torch"], ["GraphST"]],
        # Module name is `banksy`, distribution name is commonly `pybanksy`.
        "banksy": [["pybanksy", "banksy"]],
        "cellcharter": [["cellcharter"]],
    }
    
    # Auto-resolve extra packages. If a method isn't explicitly defined above,
    # assume the PyPI package name matches the method name exactly.
    extra_pkgs = method_packages.get(method)
    if extra_pkgs is None and method:
        extra_pkgs = [[method]]
        
    if extra_pkgs:
        package_groups.extend(extra_pkgs)

    env_lines: list[str] = []
    seen: set[str] = set()
    for candidates in package_groups:
        line = _pkg_line(candidates)
        key = line.split("==", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        env_lines.append(line)

    (repro_dir / "requirements.txt").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


def get_demo_data():
    """Load the built-in demo dataset."""
    demo_path = _PROJECT_ROOT / "examples" / "demo_visium.h5ad"
    if demo_path.exists():
        return sc.read_h5ad(demo_path), str(demo_path)

    logger.info("Demo file not found, generating synthetic data")
    sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
    from generate_demo_data import generate_demo_visium
    return generate_demo_visium(), None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

def main():
    parser = argparse.ArgumentParser(
        description="Spatial Domains — multi-method tissue region identification",
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(SUPPORTED_METHODS), default="leiden")
    parser.add_argument("--n-domains", type=int, default=None, help="Target number of domains (defaults to 7 for GNNs)")
    parser.add_argument("--epochs", type=int, default=100, help="Max training epochs (for GraphST/SpaGCN/STAGATE)")
    parser.add_argument("--resolution", type=float, default=1.0)
    parser.add_argument("--spatial-weight", type=float, default=0.3)
    # STAGATE network params
    parser.add_argument("--rad-cutoff", type=float, default=None)
    parser.add_argument("--k-nn", type=int, default=6)
    parser.add_argument("--stagate-alpha", type=float, default=0.0, help="Cell type-aware module weight (0 to disable)")
    parser.add_argument("--pre-resolution", type=float, default=0.2, help="STAGATE Louvain pre-clustering resolution")
    # GraphST
    parser.add_argument("--dim-output", type=int, default=64, help="GraphST embedding output dimension")
    # BANKSY param
    parser.add_argument("--lambda-param", type=float, default=0.2, help="Mixing param for spatial vs expression")
    parser.add_argument("--num-neighbours", type=int, default=15, help="Spatial neighbors for feature construction (k_geom)")
    # SpaGCN
    parser.add_argument("--spagcn-p", type=float, default=0.5, help="Spatial neighbor contribution in graph (0 to 1)")
    # CellCharter params
    parser.add_argument("--auto-k", type=str2bool, nargs='?', const=True, default=False, help="Enable automatic selection of the best number of clusters (CellCharter)")
    parser.add_argument("--auto-k-min", type=int, default=2, help="Minimum K to evaluate when auto-k is enabled")
    parser.add_argument("--auto-k-max", type=int, default=None, help="Maximum K to evaluate when auto-k is enabled")
    parser.add_argument("--n-layers", type=int, default=3, help="Number of spatial neighborhood hops to aggregate (CellCharter)")
    parser.add_argument("--use-rep", type=str, default=None, help="Feature representation to use (e.g., X_pca)")
    
    parser.add_argument("--refine", type=str2bool, nargs='?', const=True, default=False)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    elif args.input_path:
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
        if "X_pca" not in adata.obsm:
            logger.warning(
                "Input data lacks 'X_pca' in obsm. Auto-computing PCA now."
            )
            sc.tl.pca(adata, n_comps=min(50, adata.n_vars - 1))
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    # Ensure GNNs have a default target n_domains if none was passed
    if args.n_domains is None and args.method in ["spagcn", "stagate", "graphst"]:
        logger.info("Method '%s' strictly requires 'n_domains'. Defaulting to 7.", args.method)
        args.n_domains = 7

    # Helpful parameter reminders and current status
    param_tips = {
        "leiden": "1. --resolution (granularity, default 1.0)  2. --spatial-weight (spatial influence, default 0.3)",
        "louvain": "1. --resolution (granularity, default 1.0)  2. --spatial-weight (spatial influence, default 0.3)",
        "spagcn": "1. --spagcn-p (neighborhood cont, default 0.5)  2. --n-domains (clusters)  3. --epochs (default 200)",
        "stagate": "1. --rad-cutoff / --k-nn (spatial network)  2. --stagate-alpha + --pre-resolution (cell type aware)  3. --epochs",
        "graphst": "1. --epochs (default ~600, lower for huge data)  2. --dim-output (default 64)  3. --n-domains",
        "banksy": "1. --lambda-param (0.2 cell-typing / 0.8 domain-finding)  2. --num-neighbours (k_geom, default 15)  3. --resolution / --n-domains",
        "cellcharter": "1. --auto-k (automatic best K)  2. --n-domains (if fixed K)  3. --n-layers (default 3)  4. --use-rep (e.g., X_pca)"
    }
    
    # Collect current parameters specific to the method
    current_params = {"method": args.method}
    if args.method in ["leiden", "louvain", "banksy"]:
        current_params["resolution"] = args.resolution
    if args.method in ["leiden", "louvain"]:
        current_params["spatial_weight"] = args.spatial_weight
    if args.n_domains is not None:
        current_params["n_domains"] = args.n_domains
    if args.epochs is not None and args.method in ["spagcn", "stagate", "graphst"]:
        current_params["epochs"] = args.epochs
    if args.method == "stagate":
        current_params["rad_cutoff"] = args.rad_cutoff
        current_params["k_nn"] = args.k_nn
        current_params["stagate_alpha"] = args.stagate_alpha
        current_params["pre_resolution"] = args.pre_resolution
    if args.method == "banksy":
        current_params["lambda_param"] = args.lambda_param
        current_params["num_neighbours"] = args.num_neighbours
    if args.method == "cellcharter":
        current_params["auto_k"] = args.auto_k
        if args.auto_k:
            current_params["auto_k_min"] = args.auto_k_min
            if args.auto_k_max is not None:
                current_params["auto_k_max"] = args.auto_k_max
        current_params["n_layers"] = args.n_layers
        if args.use_rep is not None:
            current_params["use_rep"] = args.use_rep
    if args.method == "spagcn":
        current_params["spagcn_p"] = args.spagcn_p
    if args.method == "graphst":
        current_params["dim_output"] = args.dim_output

    print("\n" + "="*60)
    print(f"🚀 SPATIAL DOMAIN IDENTIFICATION: {args.method.upper()}")
    print("-" * 60)
    print("🔧 CURRENT RUNNING PARAMETERS:")
    for k, v in current_params.items():
        if k != "method":
            print(f"   • {k}: {v}")
    
    if args.method in param_tips:
        print("\n💡 TUNING TIPS (Priority Checklist):")
        for tip in param_tips[args.method].split("  "):
            print(f"   {tip.strip()}")
    print("="*60 + "\n")

    # Dispatch to the chosen algorithm via _lib
    summary = dispatch_method(
        args.method, adata,
        resolution=args.resolution,
        spatial_weight=args.spatial_weight,
        n_domains=args.n_domains,  # Safe variable
        epochs=args.epochs,
        rad_cutoff=args.rad_cutoff,
        k_nn=args.k_nn,
        stagate_alpha=args.stagate_alpha,
        pre_resolution=args.pre_resolution,
        dim_output=args.dim_output,
        lambda_param=args.lambda_param,
        num_neighbours=args.num_neighbours,
        spagcn_p=args.spagcn_p,
        auto_k=args.auto_k,
        auto_k_min=args.auto_k_min,
        auto_k_max=args.auto_k_max,
        n_layers=args.n_layers,
        use_rep=args.use_rep,
    )

    if args.refine:
        logger.info("Applying spatial KNN refinement ...")
        refined = refine_spatial_domains(adata)
        adata.obs["spatial_domain"] = pd.Categorical(refined)
        summary["domain_counts"] = adata.obs["spatial_domain"].value_counts().to_dict()
        summary["n_domains"] = adata.obs["spatial_domain"].nunique()
        summary["refined"] = True

    params = {"method": args.method, "resolution": args.resolution,
              "spatial_weight": args.spatial_weight, "refine": args.refine}
    if args.n_domains is not None:
        params["n_domains"] = args.n_domains
    if args.epochs is not None:
        params["epochs"] = args.epochs
    if args.method == "stagate":
        params["rad_cutoff"] = args.rad_cutoff
        params["k_nn"] = args.k_nn
        params["stagate_alpha"] = args.stagate_alpha
    if args.method == "banksy":
        params["lambda_param"] = args.lambda_param
        params["num_neighbours"] = args.num_neighbours
    if args.method == "cellcharter":
        params["auto_k"] = args.auto_k
        params["n_layers"] = args.n_layers
        if args.use_rep is not None:
            params["use_rep"] = args.use_rep
    if args.method == "spagcn":
        params["spagcn_p"] = args.spagcn_p
    if args.method == "graphst":
        params["dim_output"] = args.dim_output

    if "spatial_domain" in adata.obs.columns:
        import re
        def _natsort_key(s, _nsre=re.compile('([0-9]+)')):
            return [int(text) if text.isdigit() else text.lower() for text in _nsre.split(str(s))]
        try:
            # Ensure the column is properly categorical before reordering
            adata.obs["spatial_domain"] = adata.obs["spatial_domain"].astype("category")
            cats = adata.obs["spatial_domain"].cat.categories.tolist()
            sorted_cats = sorted(cats, key=_natsort_key)
            adata.obs["spatial_domain"] = adata.obs["spatial_domain"].cat.reorder_categories(sorted_cats)
        except Exception as e:
            logger.debug("Could not naturally sort spatial_domain categories: %s", e)

    generate_figures(adata, output_dir)
    write_report(output_dir, summary, input_file, params,
                 current_params=current_params,
                 n_cells=adata.n_obs)
    store_analysis_metadata(adata, SKILL_NAME, summary["method"], params=params)

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    print(f"Domain identification complete: {summary['n_domains']} domains ({summary['method']})")


if __name__ == "__main__":
    main()
