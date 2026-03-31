#!/usr/bin/env python3
"""Spatial Microenvironment Subset.

Extract a local neighborhood around a center cell/spot population using a
radius in either native coordinate units or microns.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import shlex
import sys

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)
from omicsclaw.common.runtime_env import ensure_runtime_cache_dirs
from skills.spatial._lib.adata_utils import get_spatial_key
from skills.spatial._lib.loader import SUPPORTED_SPATIAL_PLATFORMS, load_spatial_data
from skills.spatial._lib.microenvironment import (
    SpatialScale,
    build_label_composition_table,
    build_selection_table,
    compute_radius_native,
    extract_microenvironment_subset,
    infer_microns_per_coordinate_unit,
    parse_csv_values,
    resolve_label_key,
)

ensure_runtime_cache_dirs("omicsclaw")

import matplotlib.pyplot as plt
import scanpy as sc

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-microenvironment-subset"
SKILL_VERSION = "0.1.0"
SCRIPT_REL_PATH = (
    "skills/spatial/spatial-microenvironment-subset/"
    "spatial_microenvironment_subset.py"
)


def _append_cli_flag(cmd: str, key: str, value) -> str:
    if value is None:
        return cmd
    flag = f"--{key.replace('_', '-')}"
    if isinstance(value, bool):
        return f"{cmd} {flag}" if value else cmd
    return f"{cmd} {flag} {shlex.quote(str(value))}"


def _plot_selection(full_adata, subset_adata, output_dir: Path) -> str | None:
    spatial_key = get_spatial_key(full_adata)
    if spatial_key is None:
        return None

    full_coords = np.asarray(full_adata.obsm[spatial_key])[:, :2]
    selected_names = set(subset_adata.obs_names.astype(str))
    center_names = set(
        subset_adata.obs_names[subset_adata.obs["microenv_is_center"].astype(bool)].astype(str)
    )
    obs_names = full_adata.obs_names.astype(str)

    selected_mask = obs_names.isin(selected_names)
    center_mask = obs_names.isin(center_names)
    neighbor_mask = selected_mask & ~center_mask
    background_mask = ~selected_mask

    fig, ax = plt.subplots(figsize=(8, 8))
    if background_mask.any():
        ax.scatter(
            full_coords[background_mask, 0],
            full_coords[background_mask, 1],
            s=8,
            c="#d9d9d9",
            alpha=0.45,
            linewidths=0,
            label="background",
        )
    if neighbor_mask.any():
        ax.scatter(
            full_coords[neighbor_mask, 0],
            full_coords[neighbor_mask, 1],
            s=14,
            c="#1f77b4",
            alpha=0.85,
            linewidths=0,
            label="neighbors",
        )
    if center_mask.any():
        ax.scatter(
            full_coords[center_mask, 0],
            full_coords[center_mask, 1],
            s=22,
            c="#d62728",
            alpha=0.95,
            linewidths=0.2,
            edgecolors="white",
            label="centers",
        )

    ax.set_title("Spatial Microenvironment Selection")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_aspect("equal")
    if spatial_key == "spatial":
        ax.invert_yaxis()
    ax.legend(loc="best", frameon=False)

    figures_dir = output_dir / "figures"
    figures_dir.mkdir(exist_ok=True)
    figure_path = figures_dir / "microenvironment_selection.png"
    fig.tight_layout()
    fig.savefig(figure_path, dpi=200)
    plt.close(fig)
    return str(figure_path)


def export_tables(
    full_adata,
    subset_adata,
    output_dir: Path,
    *,
    center_key: str,
    target_key: str | None,
    summary: dict,
) -> list[str]:
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    exported: list[str] = []

    selection_table = build_selection_table(subset_adata)
    for key in {center_key, target_key} - {None}:
        if key in subset_adata.obs.columns and key not in selection_table.columns:
            selection_table[key] = subset_adata.obs[key].astype(str).to_numpy()
    selection_path = tables_dir / "selected_observations.csv"
    selection_table.to_csv(selection_path, index=False)
    exported.append(str(selection_path))

    centers_path = tables_dir / "center_observations.csv"
    selection_table.loc[selection_table["microenv_is_center"]].to_csv(centers_path, index=False)
    exported.append(str(centers_path))

    composition_path = tables_dir / "label_composition.csv"
    build_label_composition_table(
        full_adata,
        subset_adata,
        label_key=center_key,
    ).to_csv(composition_path, index=False)
    exported.append(str(composition_path))

    summary_path = tables_dir / "selection_summary.csv"
    pd.DataFrame(
        [{"metric": key, "value": json.dumps(value) if isinstance(value, (list, dict)) else value}
         for key, value in summary.items()]
    ).to_csv(summary_path, index=False)
    exported.append(str(summary_path))

    return exported


def write_report(
    output_dir: Path,
    *,
    summary: dict,
    params: dict,
    subset_path: Path,
    input_file: str | None,
    figure_path: str | None,
) -> None:
    header = generate_report_header(
        title="Spatial Microenvironment Subset Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Center key": summary["center_key"],
            "Selected observations": str(summary["n_selected_observations"]),
        },
    )

    lines = [
        "## Summary\n",
        f"- **Center key**: {summary['center_key']}",
        f"- **Center labels**: {', '.join(summary['center_values'])}",
        f"- **Selected observations**: {summary['n_selected_observations']}",
        f"- **Neighbor observations**: {summary['n_neighbor_observations']}",
        f"- **Include centers**: {summary['include_centers']}",
        f"- **Subset file**: `{subset_path}`",
    ]
    if summary.get("target_values"):
        lines.append(
            f"- **Target filter**: {summary.get('target_key')} = {', '.join(summary['target_values'])}"
        )
    if summary.get("radius_microns") is not None:
        lines.append(f"- **Radius**: {summary['radius_microns']:.3f} microns")
    lines.append(f"- **Radius (native coordinates)**: {summary['radius_native']:.6g}")
    if summary.get("microns_per_coordinate_unit") is not None:
        lines.append(
            "- **Coordinate scale**: "
            f"{summary['microns_per_coordinate_unit']:.6g} microns per unit "
            f"({summary.get('scale_source', 'unknown source')})"
        )

    lines.extend(
        [
            "",
            "## Downstream Use\n",
            "- Run `spatial-cell-communication` directly on the subset h5ad to focus analysis on the selected microenvironment.",
            "- Reuse the same subset for spatial DE, enrichment, or domain-focused diagnostics without manual coordinate slicing.",
            "",
            "## Parameters\n",
        ]
    )
    for key, value in params.items():
        if value is not None:
            lines.append(f"- `{key}`: {value}")

    lines.extend(
        [
            "",
            "## Outputs\n",
            f"- `{subset_path.name}`: subset AnnData for downstream analyses",
            "- `tables/selected_observations.csv`: per-observation role and distance metadata",
            "- `tables/center_observations.csv`: center observations retained in the subset",
            "- `tables/label_composition.csv`: label composition before vs after subsetting",
            "- `tables/selection_summary.csv`: machine-readable run summary",
        ]
    )
    if figure_path:
        lines.append(f"- `{Path(figure_path).name}`: spatial overview of background vs selected observations")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(lines) + "\n" + footer)


def write_reproducibility(
    output_dir: Path,
    *,
    params: dict,
    input_file: str | None,
) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)

    cmd = (
        f"python {SCRIPT_REL_PATH} "
        f"{'--input <input.h5ad>' if input_file else '--demo'} "
        f"--output {shlex.quote(str(output_dir))}"
    )
    for key, value in params.items():
        cmd = _append_cli_flag(cmd, key, value)

    (repro_dir / "commands.sh").write_text(
        "\n".join(
            [
                "#!/bin/bash",
                "set -euo pipefail",
                "",
                "# Replace placeholders before rerunning.",
                cmd,
                "",
            ]
        )
    )
    (repro_dir / "requirements.txt").write_text(
        "\n".join(
            [
                "anndata",
                "scanpy",
                "numpy",
                "pandas",
                "scipy",
                "matplotlib",
                "",
            ]
        )
    )


def get_demo_data():
    """Load or generate a small demo dataset with meaningful labels."""
    demo_path = _PROJECT_ROOT / "examples" / "demo_visium.h5ad"
    if demo_path.exists():
        adata = sc.read_h5ad(demo_path)
        input_file = str(demo_path)
    else:
        logger.info("Demo file not found, generating synthetic data")
        sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
        from generate_demo_data import generate_demo_visium

        adata = generate_demo_visium()
        input_file = None

    if "cell_type" not in adata.obs.columns:
        if "domain_ground_truth" in adata.obs.columns:
            mapping = {
                "domain_0": "tumor",
                "domain_1": "stroma",
                "domain_2": "immune",
            }
            adata.obs["cell_type"] = (
                adata.obs["domain_ground_truth"].astype(str).map(mapping).fillna("other")
            )
        else:
            half = max(1, adata.n_obs // 3)
            labels = np.array(["tumor"] * adata.n_obs, dtype=object)
            labels[half : 2 * half] = "stroma"
            labels[2 * half :] = "immune"
            adata.obs["cell_type"] = labels

    # Demo coordinates use a synthetic grid; define a simple micron scale.
    adata.uns["omicsclaw_spatial_units"] = {
        "microns_per_coordinate_unit": 10.0,
        "coordinate_unit": "grid_step",
        "source": "synthetic demo",
    }
    return adata, input_file


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Spatial Microenvironment Subset - extract cells/spots within a radius "
            "of a center population and save a downstream-ready h5ad subset."
        )
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--data-type",
        default="generic",
        choices=list(SUPPORTED_SPATIAL_PLATFORMS),
        help="Input platform hint for loading and coordinate-scale inference.",
    )
    parser.add_argument(
        "--center-key",
        default=None,
        help="adata.obs column defining the center population labels",
    )
    parser.add_argument(
        "--center-values",
        required=True,
        help="Comma-separated labels defining the center population",
    )
    parser.add_argument(
        "--target-key",
        default=None,
        help="Optional adata.obs column used to restrict neighbor labels",
    )
    parser.add_argument(
        "--target-values",
        default=None,
        help="Optional comma-separated labels retained among within-radius neighbors",
    )
    parser.add_argument(
        "--exclude-centers",
        action="store_true",
        help="Exclude center observations from the exported subset",
    )
    radius_group = parser.add_mutually_exclusive_group(required=True)
    radius_group.add_argument(
        "--radius-microns",
        type=float,
        default=None,
        help="Neighborhood radius in microns",
    )
    radius_group.add_argument(
        "--radius-native",
        type=float,
        default=None,
        help="Neighborhood radius in native coordinate units",
    )
    parser.add_argument(
        "--microns-per-coordinate-unit",
        type=float,
        default=None,
        help="Manual scale override used when coordinates are not already in microns.",
    )
    return parser


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.demo and not args.input_path:
        parser.error("Provide --input or --demo")
    if args.input_path and not Path(args.input_path).exists():
        parser.error(f"Input path not found: {args.input_path}")
    if args.microns_per_coordinate_unit is not None and args.microns_per_coordinate_unit <= 0:
        parser.error("--microns-per-coordinate-unit must be > 0")
    if args.radius_microns is not None and args.radius_microns <= 0:
        parser.error("--radius-microns must be > 0")
    if args.radius_native is not None and args.radius_native <= 0:
        parser.error("--radius-native must be > 0")


def _load_input_adata(args: argparse.Namespace):
    if args.demo:
        adata, input_file = get_demo_data()
        if args.data_type == "generic":
            args.data_type = "visium"
        return adata, input_file
    return load_spatial_data(args.input_path, data_type=args.data_type), args.input_path


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _validate_args(parser, args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    adata, input_file = _load_input_adata(args)
    center_key = resolve_label_key(adata, args.center_key)
    center_values = parse_csv_values(args.center_values)
    target_values = parse_csv_values(args.target_values)
    target_key = resolve_label_key(adata, args.target_key) if args.target_key else None

    scale: SpatialScale | None = None
    if args.radius_microns is not None or args.microns_per_coordinate_unit is not None:
        scale = infer_microns_per_coordinate_unit(
            adata,
            data_type=args.data_type,
            user_scale=args.microns_per_coordinate_unit,
        )
        logger.info(
            "Resolved coordinate scale: %.6g microns per unit (%s)",
            scale.microns_per_coordinate_unit,
            scale.source,
        )

    radius_native, radius_microns = compute_radius_native(
        radius_native=args.radius_native,
        radius_microns=args.radius_microns,
        scale=scale,
    )

    subset_adata, summary = extract_microenvironment_subset(
        adata,
        center_key=center_key,
        center_values=center_values,
        radius_native=radius_native,
        include_centers=not args.exclude_centers,
        target_key=target_key,
        target_values=target_values or None,
        radius_microns=radius_microns,
        scale=scale,
    )

    subset_path = output_dir / "spatial_microenvironment_subset.h5ad"
    subset_adata.write_h5ad(subset_path)
    logger.info("Saved subset AnnData to %s", subset_path)

    figure_path = _plot_selection(adata, subset_adata, output_dir)
    export_tables(
        adata,
        subset_adata,
        output_dir,
        center_key=center_key,
        target_key=target_key,
        summary=summary,
    )

    params = {
        "data_type": args.data_type,
        "center_key": center_key,
        "center_values": ",".join(center_values),
        "target_key": target_key,
        "target_values": ",".join(target_values) if target_values else None,
        "exclude_centers": bool(args.exclude_centers),
        "radius_microns": radius_microns,
        "radius_native": radius_native,
        "microns_per_coordinate_unit": args.microns_per_coordinate_unit,
    }

    write_report(
        output_dir,
        summary=summary,
        params=params,
        subset_path=subset_path,
        input_file=input_file,
        figure_path=figure_path,
    )
    write_reproducibility(output_dir, params=params, input_file=input_file)

    checksum = (
        sha256_file(input_file)
        if input_file and Path(input_file).exists() and Path(input_file).is_file()
        else ""
    )
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=summary,
        data={
            "params": params,
            "subset_path": str(subset_path),
            "figure_path": figure_path,
        },
        input_checksum=checksum,
    )


if __name__ == "__main__":
    main()
