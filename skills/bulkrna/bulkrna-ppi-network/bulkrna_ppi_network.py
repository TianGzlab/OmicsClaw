#!/usr/bin/env python3
"""bulkrna-ppi-network — PPI network analysis from DEG lists.

Queries STRING database for protein-protein interactions, builds a graph,
computes centrality metrics, identifies hub genes, and generates network
visualizations.

Usage:
    python bulkrna_ppi_network.py --input de_results.csv --output results/
    python bulkrna_ppi_network.py --demo --output /tmp/ppi_demo
"""
from __future__ import annotations

import argparse
import json
import logging
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path

import sys, os
_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))
from skills._sdk.report import (
    generate_report_header,
    generate_report_footer,
)
from skills._sdk.result import write_result_json
from skills._sdk.notebook import load_skill
from skills.bulkrna._lib.ppi import _generate_demo_de, _build_adjacency, _spring_layout

logger = logging.getLogger(__name__)

SKILL_NAME = "bulkrna-ppi-network"
SKILL_VERSION = "0.3.0"

# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


# Pre-built demo interactions (subset of STRING high-confidence edges)




def get_demo_data() -> tuple[pd.DataFrame, Path]:
    project_root = Path(__file__).resolve().parents[3]
    demo_path = project_root / "examples" / "demo_bulkrna_ppi_genes.csv"
    if demo_path.exists():
        return pd.read_csv(demo_path), demo_path
    # Demo generation is read-only with respect to the repository.  The
    # generated table is consumed in memory and all durable outputs go to the
    # caller's --output directory.
    return _generate_demo_de(), Path("built-in-demo")


# ---------------------------------------------------------------------------
# STRING API (with fallback)
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Graph analysis (pure Python — no networkx required)
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def generate_figures(output_dir: Path, edges_df: pd.DataFrame,
                     centrality_df: pd.DataFrame, de_info: dict[str, dict],
                     top_n: int = 20) -> list[str]:
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    # 1. Network visualization (spring layout)
    genes = list(centrality_df["gene"])
    adj = _build_adjacency(edges_df, genes)
    pos = _spring_layout(adj, genes)

    fig, ax = plt.subplots(figsize=(12, 10))
    # Edges
    for _, row in edges_df.iterrows():
        a, b = row["gene_a"], row["gene_b"]
        if a in pos and b in pos:
            ax.plot([pos[a][0], pos[b][0]], [pos[a][1], pos[b][1]],
                    color="#cccccc", linewidth=0.5, alpha=0.5, zorder=1)
    # Nodes
    for g in genes:
        if g in pos:
            deg = centrality_df.loc[centrality_df["gene"] == g, "degree"].values[0]
            size = max(60, min(400, deg * 40))
            info = de_info.get(g, {})
            lfc = info.get("log2FoldChange", 0)
            if lfc > 0.5:
                color = "#E84D60"  # up
            elif lfc < -0.5:
                color = "#4878CF"  # down
            else:
                color = "#AAAAAA"
            ax.scatter(pos[g][0], pos[g][1], s=size, c=color, edgecolors="white",
                       linewidth=0.8, zorder=2, alpha=0.85)
            if deg >= 3:  # Only label genes with >= 3 connections
                ax.annotate(g, pos[g], fontsize=6, ha="center", va="bottom",
                            textcoords="offset points", xytext=(0, 5), zorder=3)
    ax.set_title("Protein-Protein Interaction Network", fontsize=14, fontweight="bold")
    ax.axis("off")
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="#E84D60", label="Up-regulated"),
        Patch(facecolor="#4878CF", label="Down-regulated"),
        Patch(facecolor="#AAAAAA", label="Not significant"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=9)
    fig.tight_layout()
    p = fig_dir / "ppi_network.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    # 2. Hub genes barplot
    top_hubs = centrality_df.head(top_n).copy()
    fig, ax = plt.subplots(figsize=(8, max(4, top_n * 0.3)))
    colors_bar = []
    for g in top_hubs["gene"]:
        lfc = de_info.get(g, {}).get("log2FoldChange", 0)
        if lfc > 0.5:
            colors_bar.append("#E84D60")
        elif lfc < -0.5:
            colors_bar.append("#4878CF")
        else:
            colors_bar.append("#888888")
    ax.barh(range(len(top_hubs)), top_hubs["hub_score"].values, color=colors_bar,
            edgecolor="white", linewidth=0.5)
    ax.set_yticks(range(len(top_hubs)))
    ax.set_yticklabels(top_hubs["gene"].values, fontsize=8)
    ax.set_xlabel("Hub Score (degree + betweenness)")
    ax.set_title(f"Top {top_n} Hub Genes")
    ax.invert_yaxis()
    fig.tight_layout()
    p = fig_dir / "hub_genes_barplot.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    return paths




# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(output_dir: Path, summary: dict, params: dict,
                 edges_df: pd.DataFrame, centrality_df: pd.DataFrame,
                 top_n: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    header = generate_report_header(
        title="PPI Network Analysis Report", skill_name=SKILL_NAME,
    )

    top_hubs = centrality_df.head(top_n)
    body_lines = [
        "## Summary\n",
        f"- **Input genes**: {summary['n_genes']}",
        f"- **Interactions found**: {summary['n_edges']}",
        f"- **Connected genes**: {summary['n_connected']}",
        f"- **Isolated genes**: {summary['n_isolated']}",
        f"- **Mean degree**: {summary['mean_degree']:.1f}",
        "",
        f"## Top {top_n} Hub Genes\n",
        "| Rank | Gene | Degree | Betweenness | Hub Score |",
        "|------|------|--------|-------------|-----------|",
    ]
    for i, row in top_hubs.iterrows():
        body_lines.append(
            f"| {i+1} | {row['gene']} | {row['degree']} | "
            f"{row['betweenness']:.4f} | {row['hub_score']:.4f} |"
        )
    body_lines.extend(["", "## Figures\n",
                        "- `figures/ppi_network.png` — PPI network visualization",
                        "- `figures/hub_genes_barplot.png` — Hub gene ranking",
                        ""])

    footer = generate_report_footer()
    report_text = "\n".join([header, "\n".join(body_lines), footer])
    (output_dir / "report.md").write_text(report_text, encoding="utf-8")

    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, params)

    edges_df.to_csv(tables_dir / "interaction_edges.csv", index=False)
    centrality_df.to_csv(tables_dir / "node_centrality.csv", index=False)
    top_hubs.to_csv(tables_dir / "hub_genes.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    (repro_dir / "commands.sh").write_text(
        f"#!/usr/bin/env bash\npython bulkrna_ppi_network.py "
        f"--input {params.get('input', '<INPUT>')} "
        f"--output {params.get('output', '<OUTPUT>')} "
        f"--species {params.get('species', 9606)}\n", encoding="utf-8")
    logger.info("Report written to %s", output_dir)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    ap = argparse.ArgumentParser(description=f"{SKILL_NAME} v{SKILL_VERSION}")
    ap.add_argument("--input", type=str, help="Gene list or DE results CSV")
    ap.add_argument("--output", type=str, required=True)
    ap.add_argument("--species", type=int, default=9606)
    ap.add_argument("--score-threshold", type=int, default=400)
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    if args.demo and args.species != 9606:
        ap.error('The fixed demo reference contains human interactions only (species 9606)')
    if not 0 <= args.score_threshold <= 1000:
        ap.error('--score-threshold must be in [0, 1000]')

    output_dir = Path(args.output)

    if args.demo:
        de_df, input_path = get_demo_data()
    else:
        if not args.input:
            ap.error("--input required (or use --demo)")
        input_path = Path(args.input)
        if input_path.suffix == ".txt":
            genes = [g.strip() for g in input_path.read_text().splitlines() if g.strip()]
            de_df = pd.DataFrame({"gene": genes})
        else:
            de_df = pd.read_csv(input_path)

    gene_list = de_df["gene"].tolist()
    de_info = {}
    for _, row in de_df.iterrows():
        de_info[row["gene"]] = row.to_dict()

    library = load_skill(SKILL_NAME)
    if args.demo:
        edges_df = pd.read_csv(Path(__file__).parent / 'data/demo_string_edges.csv')
        edges_df = edges_df[edges_df.score >= args.score_threshold / 1000.]
    else:
        edges_df = library.fetch_interactions(gene_list, species=args.species, score_threshold=args.score_threshold)
    centrality_df = library.analyze(edges_df, genes=gene_list)
    summary = library.run_info(centrality_df, keep=False)
    params = {"input": str(input_path), "output": str(output_dir),
              "species": args.species, "score_threshold": args.score_threshold}

    generate_figures(output_dir, edges_df, centrality_df, de_info, args.top_n)
    write_report(output_dir, summary, params, edges_df, centrality_df, args.top_n)
    logger.info("✓ PPI network analysis complete → %s", output_dir)


if __name__ == "__main__":
    main()
