#!/usr/bin/env python3
"""Single-Cell Markers - cluster marker discovery with standardized outputs."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import pandas as pd

try:
    import anndata
    anndata.settings.allow_write_nullable_strings = True
except Exception:
    pass

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    load_result_json,
    write_result_json,
    write_replot_hint,
)
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib import markers as sc_markers_utils
from skills.singlecell._lib.adata_utils import (
    ensure_input_contract,
    get_matrix_contract,
    infer_x_matrix_kind,
    propagate_singlecell_contracts,
    store_analysis_metadata,
)
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice
from skills.singlecell._lib.preflight import apply_preflight, preflight_sc_markers, _obs_candidates
from skills.singlecell._lib.viz import (
    plot_marker_cluster_summary,
    plot_marker_dotplot,
    plot_marker_effect_summary,
    plot_marker_fraction_scatter,
    plot_marker_heatmap,
)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

SKILL_NAME = 'sc-markers'
SKILL_VERSION = '0.5.0'
SCRIPT_REL_PATH = 'skills/singlecell/scrna/sc-markers/sc_markers.py'

# R Enhanced renderers for this skill.
# Key   = renderer name registered in viz/r/registry.R R_PLOT_REGISTRY
# Value = output filename (written to figures/r_enhanced/)
R_ENHANCED_PLOTS: dict[str, str] = {
    "plot_marker_heatmap": "r_marker_heatmap.png",
    "plot_feature_violin": "r_feature_violin.png",
}


def _render_r_enhanced(
    output_dir: Path,
    figure_data_dir: Path,
    r_enhanced: bool,
) -> list[str]:
    """Run R Enhanced rendering pass. Always called after Python figures are complete."""
    if not r_enhanced:
        return []
    from skills.singlecell._lib.viz.r import call_r_plot
    r_figures_dir = output_dir / "figures" / "r_enhanced"
    r_figures_dir.mkdir(parents=True, exist_ok=True)
    r_figure_paths: list[str] = []
    for renderer, filename in R_ENHANCED_PLOTS.items():
        out_path = r_figures_dir / filename
        call_r_plot(renderer, figure_data_dir, out_path)
        if out_path.exists():
            r_figure_paths.append(str(out_path))
    return r_figure_paths

METHOD_REGISTRY: dict[str, MethodConfig] = {
    'wilcoxon': MethodConfig(name='wilcoxon', description='Wilcoxon rank-sum cluster marker ranking', dependencies=('scanpy',)),
    't-test': MethodConfig(name='t-test', description="Welch's t-test cluster marker ranking", dependencies=('scanpy',)),
    'logreg': MethodConfig(name='logreg', description='Logistic-regression marker ranking', dependencies=('scanpy',)),
    'cosg': MethodConfig(name='cosg', description='COSG cosine-similarity specificity scoring (no p-values, fast)', dependencies=('scanpy', 'sklearn')),
}


def _write_repro_requirements(repro_dir: Path, packages: list[str]) -> None:
    try:
        from importlib.metadata import PackageNotFoundError, version as get_version
    except ImportError:  # pragma: no cover
        PackageNotFoundError = Exception
        from importlib_metadata import version as get_version  # type: ignore

    lines: list[str] = []
    for pkg in packages:
        try:
            lines.append(f"{pkg}=={get_version(pkg)}")
        except PackageNotFoundError:
            continue
        except Exception:
            continue
    (repro_dir / 'requirements.txt').write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='utf-8')




def _candidate_groupby(adata) -> list[str]:
    matrix_contract = get_matrix_contract(adata)
    primary = matrix_contract.get('primary_cluster_key')
    candidates: list[str] = []
    if primary and primary in adata.obs.columns:
        candidates.append(str(primary))
    for key in _obs_candidates(adata, 'cluster') + _obs_candidates(adata, 'cell_type'):
        if key not in candidates:
            candidates.append(key)
    return candidates


def _resolve_groupby(adata, requested: str | None) -> str:
    if requested and requested in adata.obs.columns:
        return requested
    candidates = _candidate_groupby(adata)
    if requested and requested not in adata.obs.columns:
        raise ValueError(f"Grouping column '{requested}' not found in adata.obs")
    if not candidates:
        raise ValueError('No cluster/cell-type grouping column available for marker discovery.')
    return candidates[0]


def _build_cluster_summary(markers: pd.DataFrame, *, n_top: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    if markers.empty:
        return pd.DataFrame(), pd.DataFrame()
    frame = markers.copy()
    effect_col = 'logfoldchanges' if 'logfoldchanges' in frame.columns and pd.to_numeric(frame['logfoldchanges'], errors='coerce').notna().any() else 'scores'
    sort_cols = []
    ascending = []
    if 'pvals_adj' in frame.columns and pd.to_numeric(frame['pvals_adj'], errors='coerce').notna().any():
        sort_cols.append('pvals_adj')
        ascending.append(True)
    sort_cols.append(effect_col)
    ascending.append(False)
    frame = frame.sort_values(sort_cols, ascending=ascending)
    top_df = frame.groupby('group', sort=False, observed=False).head(n_top).copy()
    summary_df = (
        frame.groupby('group', dropna=False, observed=False)
        .agg(
            n_markers=('names', 'count'),
            top_gene=('names', 'first'),
            top_effect=(effect_col, 'max'),
            median_effect=(effect_col, 'median'),
        )
        .reset_index()
    )
    summary_df['effect_metric'] = effect_col
    return summary_df, top_df


def _write_figure_data(output_dir: Path, *, markers: pd.DataFrame, top_markers: pd.DataFrame, cluster_summary: pd.DataFrame) -> dict[str, str]:
    figure_data_dir = output_dir / 'figure_data'
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    files = {
        'markers_all': 'markers_all.csv',
        'markers_top': 'markers_top.csv',
        'cluster_summary': 'cluster_summary.csv',
    }
    markers.to_csv(figure_data_dir / files['markers_all'], index=False)
    top_markers.to_csv(figure_data_dir / files['markers_top'], index=False)
    cluster_summary.to_csv(figure_data_dir / files['cluster_summary'], index=False)
    (figure_data_dir / 'manifest.json').write_text(
        json.dumps({'skill': SKILL_NAME, 'available_files': files}, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )
    return files


def generate_marker_figures(adata, markers: pd.DataFrame, output_dir: Path, *, groupby: str, n_top: int, cluster_summary_df: pd.DataFrame) -> None:
    plot_marker_heatmap(adata, markers, output_dir, groupby=groupby, n_top=n_top)
    plot_marker_dotplot(adata, markers, output_dir, groupby=groupby, n_top=min(5, n_top))
    plot_marker_effect_summary(markers, output_dir, n_top=min(3, n_top))
    plot_marker_cluster_summary(cluster_summary_df, output_dir)
    plot_marker_fraction_scatter(markers, output_dir, n_top=min(5, n_top))


def write_report(output_dir: Path, summary: dict, params: dict, input_file: str | None, *, cluster_summary_df: pd.DataFrame) -> None:
    header = generate_report_header(
        title='Single-Cell Marker Report',
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            'Grouping': params['groupby'],
            'Method': params['method'],
            'Clusters': str(summary['n_clusters']),
            'Total markers': str(summary['n_markers']),
        },
    )

    lines = [
        '## Summary\n',
        f"- **Grouping column**: `{params['groupby']}`",
        f"- **Method**: `{params['method']}`",
        f"- **Clusters / groups**: {summary['n_clusters']}",
        f"- **Total markers exported**: {summary['n_markers']}",
        '',
        '## First-pass Settings\n',
        f"- `groupby`: {params['groupby']}",
        f"- `method`: {params['method']}",
        f"- `n_genes`: {params['n_genes'] if params['n_genes'] is not None else 'all'}",
        f"- `n_top`: {params['n_top']}",
        f"- `min_in_group_fraction`: {params['min_in_group_fraction']}",
        f"- `min_fold_change`: {params['min_fold_change']}",
        f"- `max_out_group_fraction`: {params['max_out_group_fraction']}",
        '',
        '## Beginner Notes\n',
        '- `sc-markers` is usually the step after clustering and before final annotation.',
        '- The current wrapper ranks marker genes using normalized expression in `adata.X` rather than raw counts.',
        '- Marker ranking helps interpret clusters, but it does not replace replicate-aware condition DE.',
        '',
        '## Recommended Next Steps\n',
        '- If cluster identity is still unclear, use these markers to guide `sc-cell-annotation`.',
        '- If you need treated-vs-control differential expression rather than cluster markers, use `sc-de`.',
        '- If the clusters themselves look unstable, revisit `sc-clustering` before trusting markers.',
        '',
        '## Output Files\n',
        '- `processed.h5ad` — normalized AnnData with marker-analysis metadata preserved.',
        '- `tables/markers_all.csv` — all exported markers.',
        '- `tables/markers_top.csv` — top marker rows used for compact summaries.',
        '- `tables/cluster_summary.csv` — marker counts and top genes per group.',
        '- `figures/` — marker gallery (heatmap, dotplot, effect summary, group summary, optional prevalence scatter).',
        '- `figure_data/` — reusable tables for downstream styling and notebook work.',
    ]

    if not cluster_summary_df.empty:
        lines.extend(['', '## Top Marker Snapshot\n'])
        for _, row in cluster_summary_df.head(8).iterrows():
            lines.append(f"- `{row['group']}`: top gene `{row['top_gene']}` ({row['effect_metric']} median={row['median_effect']:.2f})")

    report = header + '\n'.join(lines) + '\n' + generate_report_footer()
    (output_dir / 'report.md').write_text(report, encoding='utf-8')


def write_reproducibility(output_dir: Path, params: dict, input_file: str | None, *, demo_mode: bool = False) -> None:
    repro_dir = output_dir / 'reproducibility'
    repro_dir.mkdir(parents=True, exist_ok=True)
    command_parts = ['python', SCRIPT_REL_PATH]
    if demo_mode:
        command_parts.append('--demo')
    elif input_file:
        command_parts.extend(['--input', input_file])
    else:
        command_parts.extend(['--input', '<input.h5ad>'])
    command_parts.extend(['--output', str(output_dir)])
    for key in ('groupby','method','n_genes','n_top','min_in_group_fraction','min_fold_change','max_out_group_fraction'):
        value = params.get(key)
        if value not in (None, ''):
            command_parts.extend([f"--{key.replace('_','-')}", str(value)])
    command = ' '.join(shlex.quote(part) for part in command_parts)
    (repro_dir / 'commands.sh').write_text(f"#!/bin/bash\n{command}\n", encoding='utf-8')
    _write_repro_requirements(repro_dir, ['scanpy', 'anndata', 'numpy', 'pandas', 'matplotlib', 'seaborn'])


def get_demo_data():
    adata, _ = sc_io.load_repo_demo_data('pbmc3k_processed')
    return adata


def main():
    parser = argparse.ArgumentParser(description='Single-Cell Marker Discovery')
    parser.add_argument('--input', dest='input_path')
    parser.add_argument('--output', dest='output_dir', required=True)
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--groupby', default=None)
    parser.add_argument('--method', choices=list(METHOD_REGISTRY.keys()), default='wilcoxon')
    parser.add_argument('--n-genes', type=int, default=None)
    parser.add_argument('--n-top', type=int, default=10)
    parser.add_argument('--min-in-group-fraction', type=float, default=0.25)
    parser.add_argument('--min-fold-change', type=float, default=0.25)
    parser.add_argument('--max-out-group-fraction', type=float, default=0.5)
    # COSG-specific parameters
    parser.add_argument('--mu', type=float, default=1.0, help='COSG specificity penalty (0-1, default 1)')
    parser.add_argument(
        "--r-enhanced", action="store_true",
        help="Generate R Enhanced ggplot2 figures in addition to standard Python plots."
    )
    args = parser.parse_args()

    # -- Parameter validation --
    from skills.singlecell._lib.param_validators import ParamValidator
    v = ParamValidator(SKILL_NAME)
    v.positive("n_top", args.n_top, min_val=1)
    v.positive("n_genes", args.n_genes, min_val=1)
    v.in_range("min_in_group_fraction", args.min_in_group_fraction, low=0, high=1)
    v.in_range("max_out_group_fraction", args.max_out_group_fraction, low=0, high=1)
    v.non_negative("min_fold_change", args.min_fold_change)
    v.in_range("mu", args.mu, low=0, high=1)
    v.check()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata = get_demo_data()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError('--input required when not using --demo')
        adata = sc_io.smart_load(args.input_path, skill_name=SKILL_NAME)
        input_file = str(Path(args.input_path))

    method = validate_method_choice(args.method, METHOD_REGISTRY)
    apply_preflight(
        preflight_sc_markers(
            adata,
            groupby=args.groupby,
            method=method,
            n_genes=args.n_genes,
            n_top=args.n_top,
            min_in_group_fraction=args.min_in_group_fraction,
            min_fold_change=args.min_fold_change,
            max_out_group_fraction=args.max_out_group_fraction,
            source_path=input_file,
        ),
        logger,
    )

    resolved_groupby = _resolve_groupby(adata, args.groupby)
    if method == 'cosg':
        markers = sc_markers_utils.find_cosg_markers(
            adata,
            cluster_key=resolved_groupby,
            n_genes=args.n_genes if args.n_genes is not None else 50,
            mu=args.mu,
            use_raw=False,
        )
    else:
        markers = sc_markers_utils.find_all_cluster_markers(
            adata,
            cluster_key=resolved_groupby,
            method=method,
            n_genes=args.n_genes,
            min_in_group_fraction=args.min_in_group_fraction,
            min_fold_change=args.min_fold_change,
            max_out_group_fraction=args.max_out_group_fraction,
            use_raw=False,
        )

    cluster_summary_df, top_markers_df = _build_cluster_summary(markers, n_top=args.n_top)
    summary = {
        'method': method,
        'groupby': resolved_groupby,
        'n_clusters': int(markers['group'].nunique()) if not markers.empty else 0,
        'n_markers': int(len(markers)),
    }
    params = {
        'groupby': resolved_groupby,
        'method': method,
        'n_genes': args.n_genes,
        'n_top': args.n_top,
        'min_in_group_fraction': args.min_in_group_fraction,
        'min_fold_change': args.min_fold_change,
        'max_out_group_fraction': args.max_out_group_fraction,
        'expression_source': 'adata.X',
        'mu': args.mu if method == 'cosg' else None,
    }

    generate_marker_figures(adata, markers, output_dir, groupby=resolved_groupby, n_top=args.n_top, cluster_summary_df=cluster_summary_df)
    tables_dir = output_dir / 'tables'
    tables_dir.mkdir(parents=True, exist_ok=True)
    markers.to_csv(tables_dir / 'markers_all.csv', index=False)
    top_markers_df.to_csv(tables_dir / 'markers_top.csv', index=False)
    cluster_summary_df.to_csv(tables_dir / 'cluster_summary.csv', index=False)
    figure_data_files = _write_figure_data(output_dir, markers=markers, top_markers=top_markers_df, cluster_summary=cluster_summary_df)

    write_report(output_dir, summary, params, input_file, cluster_summary_df=cluster_summary_df)
    write_reproducibility(output_dir, params, input_file, demo_mode=args.demo)

    for key in ('rank_genes_groups', 'rank_genes_groups_filtered'):
        if key in adata.uns:
            del adata.uns[key]

    input_contract, matrix_contract = propagate_singlecell_contracts(
        adata,
        adata,
        producer_skill=SKILL_NAME,
        x_kind='normalized_expression',
        raw_kind=get_matrix_contract(adata).get('raw'),
        primary_cluster_key=get_matrix_contract(adata).get('primary_cluster_key') or resolved_groupby,
    )
    store_analysis_metadata(adata, SKILL_NAME, method, params)
    output_h5ad = output_dir / 'processed.h5ad'
    save_h5ad(adata, output_h5ad)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ''
    result_data = {
        'params': params,
        'input_contract': input_contract,
        'matrix_contract': matrix_contract,
        'visualization': {'available_figure_data': figure_data_files},
    }
    result_data["next_steps"] = [
        {"skill": "sc-de", "reason": "Perform detailed differential expression analysis", "priority": "optional"},
        {"skill": "sc-enrichment", "reason": "Pathway enrichment analysis on marker genes", "priority": "optional"},
    ]
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    write_replot_hint(output_dir, SKILL_NAME, R_ENHANCED_PLOTS)
    result_payload = load_result_json(output_dir) or {'skill': SKILL_NAME, 'summary': summary, 'data': result_data}

    # R Enhanced figures (only when --r-enhanced flag is set)
    r_enhanced_figures = _render_r_enhanced(
        output_dir=output_dir,
        figure_data_dir=output_dir / "figure_data",
        r_enhanced=args.r_enhanced,
    )
    if r_enhanced_figures:
        result_data["r_enhanced_figures"] = r_enhanced_figures

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Marker discovery complete: {summary['n_markers']} rows across {summary['n_clusters']} groups using {method}")

    # --- Next-step guidance ---
    print()
    print(">> Next steps:")
    print(f"  - sc-de:         python omicsclaw.py run sc-de --input {output_dir}/processed.h5ad --output <dir>")
    print(f"  - sc-enrichment: python omicsclaw.py run sc-enrichment --input {output_dir}/processed.h5ad --output <dir>")


if __name__ == '__main__':
    main()
