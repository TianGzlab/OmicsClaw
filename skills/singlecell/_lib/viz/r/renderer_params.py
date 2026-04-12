"""Renderer parameter schemas for R Enhanced plots.

Maps each renderer name to its tunable parameters with type, default, and description.
Used by ``replot`` to validate and document available params for each renderer.

Derived from ``params[[...]]`` usage in each R file under viz/r/.
"""

from __future__ import annotations

# Schema format per param:
#   "param_name": {"type": "int"|"float"|"str"|"bool", "default": ..., "desc": "..."}
RENDERER_PARAMS: dict[str, dict[str, dict]] = {
    # ── de.R ──────────────────────────────────────────────────────────────────
    "plot_de_volcano": {
        "padj_thresh": {"type": "float", "default": 0.05,  "desc": "Adjusted p-value threshold for significance"},
        "fc_thresh":   {"type": "float", "default": 0.25,  "desc": "log2FC threshold for significance"},
        "n_label":     {"type": "int",   "default": 5,     "desc": "Number of top genes to label"},
    },
    "plot_de_heatmap": {
        "n_top":       {"type": "int",   "default": 5,     "desc": "Top N genes per group shown in heatmap"},
    },
    "plot_de_manhattan": {
        "padj_thresh": {"type": "float", "default": 0.05,  "desc": "Adjusted p-value threshold"},
        "fc_thresh":   {"type": "float", "default": 0.25,  "desc": "log2FC threshold"},
        "n_label":     {"type": "int",   "default": 3,     "desc": "Number of top genes to label"},
        "jitter_width": {"type": "float", "default": 0.4,  "desc": "Horizontal jitter width"},
    },
    # ── markers.R ─────────────────────────────────────────────────────────────
    "plot_marker_heatmap": {
        "n_top":       {"type": "int",   "default": 10,    "desc": "Top N marker genes per cluster"},
    },
    # ── embedding.R ───────────────────────────────────────────────────────────
    "plot_embedding_discrete": {
        "color_by":    {"type": "str",   "default": None,  "desc": "Column to colour points by"},
    },
    "plot_embedding_feature": {
        "feature":     {"type": "str",   "default": None,  "desc": "Gene or numeric feature to visualise"},
    },
    # ── enrichment.R ──────────────────────────────────────────────────────────
    "plot_enrichment_bar": {
        "top_n":       {"type": "int",   "default": 20,    "desc": "Number of top terms to show"},
        "group":       {"type": "str",   "default": None,  "desc": "Cell group to filter (None = first group)"},
    },
    "plot_gsea_mountain": {
        "group":       {"type": "str",   "default": None,  "desc": "Cell group"},
        "term":        {"type": "str",   "default": None,  "desc": "Pathway term to plot"},
    },
    "plot_gsea_nes_heatmap": {
        "padj_cutoff":      {"type": "float", "default": 0.05, "desc": "Adjusted p-value cutoff"},
        "top_n":            {"type": "int",   "default": 25,   "desc": "Top N pathways"},
    },
    "plot_enrichment_dotplot": {
        "top_n":       {"type": "int",   "default": 8,     "desc": "Top N terms per group"},
        "group":       {"type": "str",   "default": None,  "desc": "Cell group (None = first group)"},
    },
    "plot_enrichment_lollipop": {
        "top_n":       {"type": "int",   "default": 10,    "desc": "Top N terms"},
        "group":       {"type": "str",   "default": None,  "desc": "Cell group (None = first group)"},
    },
    "plot_enrichment_network": {
        "top_n":       {"type": "int",   "default": 10,    "desc": "Top N terms"},
        "padj_cutoff": {"type": "float", "default": 0.05,  "desc": "Adjusted p-value cutoff"},
        "group":       {"type": "str",   "default": None,  "desc": "Cell group"},
    },
    "plot_enrichment_enrichmap": {
        "top_n":            {"type": "int",   "default": 50,   "desc": "Top N terms"},
        "padj_cutoff":      {"type": "float", "default": 0.05, "desc": "Adjusted p-value cutoff"},
        "min_similarity":   {"type": "float", "default": 0.1,  "desc": "Minimum term similarity for edges"},
        "group":            {"type": "str",   "default": None, "desc": "Cell group"},
    },
    # ── communication.R ───────────────────────────────────────────────────────
    "plot_ccc_heatmap": {
        "plot_type":   {"type": "str",   "default": None,  "desc": "Interaction type to plot"},
    },
    "plot_ccc_network": {
        "min_score":   {"type": "float", "default": 0.0,   "desc": "Minimum interaction score threshold"},
        "top_n":       {"type": "int",   "default": 20,    "desc": "Top N interactions"},
    },
    "plot_ccc_bubble": {
        "top_n":       {"type": "int",   "default": 30,    "desc": "Top N LR pairs to show"},
    },
    "plot_ccc_stat_bar": {
        "top_n":       {"type": "int",   "default": 15,    "desc": "Top N interactions"},
        "group_by":    {"type": "str",   "default": None,  "desc": "Grouping column"},
    },
    "plot_ccc_stat_violin": {
        "facet_by":    {"type": "str",   "default": "source", "desc": "Column to facet by"},
        "top_n":       {"type": "int",   "default": 20,    "desc": "Top N interactions"},
    },
    "plot_ccc_stat_scatter": {
        "ligand":      {"type": "str",   "default": None,  "desc": "Ligand gene to focus on"},
        "top_n":       {"type": "int",   "default": 20,    "desc": "Top N targets"},
    },
    "plot_ccc_bipartite": {
        "min_diff":    {"type": "float", "default": 0.0,   "desc": "Minimum score difference for differential"},
        "top_n":       {"type": "int",   "default": 20,    "desc": "Top N interactions"},
    },
    "plot_ccc_diff_network": {
        "min_diff":    {"type": "float", "default": 0.0,   "desc": "Minimum differential score"},
        "top_n":       {"type": "int",   "default": 20,    "desc": "Top N interactions"},
    },
    # ── correlation.R ─────────────────────────────────────────────────────────
    "plot_feature_cor": {
        "cor_method":  {"type": "str",   "default": "pearson", "desc": "Correlation method (pearson/spearman)"},
        "features":    {"type": "str",   "default": None,  "desc": "Comma-separated feature names to include"},
    },
    # ── cytotrace.R ───────────────────────────────────────────────────────────
    "plot_cytotrace_boxplot": {
        "group_col":   {"type": "str",   "default": "cell_type",       "desc": "Column for group labels"},
        "score_col":   {"type": "str",   "default": "cytotrace_score", "desc": "Column for CytoTRACE scores"},
    },
    # ── density.R ─────────────────────────────────────────────────────────────
    "plot_cell_density": {
        "feature":     {"type": "str",   "default": None,  "desc": "Feature/score column for density colouring"},
        "group_by":    {"type": "str",   "default": None,  "desc": "Column to group cells by"},
        "flip":        {"type": "bool",  "default": False, "desc": "Flip x/y axes"},
    },
    # ── stat.R ────────────────────────────────────────────────────────────────
    "plot_feature_violin": {
        "n_genes":     {"type": "int",   "default": 6,     "desc": "Number of top genes to show"},
    },
    "plot_feature_boxplot": {
        "n_genes":     {"type": "int",   "default": 5,     "desc": "Number of top genes to show"},
    },
    "plot_cell_barplot": {
        "position":    {"type": "str",   "default": "stack", "desc": "Bar position (stack/fill/dodge)"},
    },
    "plot_cell_proportion": {
        "style":       {"type": "str",   "default": "donut", "desc": "Plot style (donut/pie/bar)"},
    },
    "plot_proportion_test": {
        "FDR_threshold":   {"type": "float", "default": 0.05, "desc": "FDR threshold for significance"},
        "fold_threshold":  {"type": "float", "default": 1.5,  "desc": "Fold-change threshold"},
    },
    # ── sankey.R ──────────────────────────────────────────────────────────────
    "plot_cell_sankey": {
        "left_col":    {"type": "str",   "default": None,  "desc": "Left-side column for sankey"},
        "right_col":   {"type": "str",   "default": None,  "desc": "Right-side column for sankey"},
        "title":       {"type": "str",   "default": None,  "desc": "Plot title (auto-generated if omitted)"},
    },
    # ── pseudotime.R ──────────────────────────────────────────────────────────
    "plot_pseudotime_lineage": {
        "span":              {"type": "float", "default": 0.75, "desc": "LOESS smoothing span"},
        "compare_lineages":  {"type": "bool",  "default": True, "desc": "Overlay multiple lineages"},
    },
    "plot_pseudotime_dynamic": {
        "n_genes":     {"type": "int",   "default": 5,     "desc": "Number of dynamic genes to show"},
    },
    "plot_pseudotime_heatmap": {
        "n_genes":     {"type": "int",   "default": 30,    "desc": "Number of genes in heatmap"},
        "n_bins":      {"type": "int",   "default": 50,    "desc": "Number of pseudotime bins"},
    },
    # ── velocity.R ────────────────────────────────────────────────────────────
    "plot_velocity": {
        "color_by":    {"type": "str",   "default": None,  "desc": "Column to colour cells by"},
        "plot_type":   {"type": "str",   "default": None,  "desc": "Plot type (stream/grid/arrow)"},
        "n_bins":      {"type": "int",   "default": None,  "desc": "Number of grid bins"},
    },
}

# ── Per-skill renderer lookup ──────────────────────────────────────────────────
# Maps skill alias → list of renderer names (matches R_ENHANCED_PLOTS keys).
SKILL_RENDERERS: dict[str, list[str]] = {
    "sc-ambient-removal": [
        "plot_feature_violin",
    ],
    "sc-batch-integration": [
        "plot_embedding_discrete",
    ],
    "sc-cell-annotation": [
        "plot_embedding_discrete",
        "plot_embedding_feature",
        "plot_cell_barplot",
        "plot_cell_proportion",
        "plot_cell_sankey",
    ],
    "sc-cell-communication": [
        "plot_ccc_heatmap",
        "plot_ccc_network",
        "plot_ccc_bubble",
        "plot_ccc_stat_bar",
        "plot_ccc_stat_violin",
        "plot_ccc_stat_scatter",
        "plot_ccc_bipartite",
        "plot_ccc_diff_network",
    ],
    "sc-clustering": [
        "plot_embedding_discrete",
        "plot_embedding_feature",
        "plot_cell_barplot",
        "plot_cell_proportion",
    ],
    "sc-cytotrace": [
        "plot_embedding_discrete",
        "plot_embedding_feature",
        "plot_cytotrace_boxplot",
        "plot_cell_density",
    ],
    "sc-de": [
        "plot_de_volcano",
        "plot_de_heatmap",
        "plot_feature_violin",
        "plot_feature_cor",
        "plot_de_manhattan",
    ],
    "sc-differential-abundance": [
        "plot_embedding_discrete",
        "plot_cell_barplot",
        "plot_proportion_test",
        "plot_cell_density",
    ],
    "sc-doublet-detection": [
        "plot_embedding_discrete",
        "plot_embedding_feature",
        "plot_feature_violin",
    ],
    "sc-enrichment": [
        "plot_enrichment_bar",
        "plot_gsea_mountain",
        "plot_gsea_nes_heatmap",
        "plot_enrichment_dotplot",
        "plot_enrichment_lollipop",
        "plot_enrichment_network",
        "plot_enrichment_enrichmap",
    ],
    "sc-filter": [
        "plot_feature_violin",
    ],
    "sc-gene-programs": [
        "plot_feature_violin",
        "plot_feature_cor",
    ],
    "sc-grn": [
        "plot_feature_violin",
        "plot_feature_cor",
    ],
    "sc-in-silico-perturbation": [
        "plot_de_volcano",
    ],
    "sc-markers": [
        "plot_marker_heatmap",
        "plot_feature_violin",
    ],
    "sc-metacell": [
        "plot_embedding_discrete",
    ],
    "sc-pathway-scoring": [
        "plot_feature_violin",
    ],
    "sc-perturb": [
        "plot_cell_barplot",
    ],
    "sc-preprocessing": [
        "plot_feature_violin",
    ],
    "sc-pseudotime": [
        "plot_pseudotime_lineage",
        "plot_pseudotime_dynamic",
        "plot_pseudotime_heatmap",
        "plot_embedding_discrete",
        "plot_embedding_feature",
        "plot_cell_density",
    ],
    "sc-qc": [
        "plot_feature_violin",
    ],
    "sc-velocity": [
        "plot_velocity",
        "plot_embedding_discrete",
        "plot_embedding_feature",
    ],
}
