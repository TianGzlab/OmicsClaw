"""Centralized metrics registry for OmicsClaw autoagent optimization.

Maps (skill, method) pairs to their evaluation metrics without modifying
individual SKILL.md files.  Common omics metrics (LISI, ASW, annotation
confidence, batch mixing, etc.) are defined once and reused across skills.

Usage:
    from omicsclaw.autoagent.metrics_registry import get_metrics_for_skill

    metrics = get_metrics_for_skill("sc-batch-integration", "harmony")
    # => {"mean_ilisi": MetricDef(...), "mean_clisi": MetricDef(...), ...}
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricDef:
    """Definition of a single evaluation metric.

    Attributes:
        source: Where to read the metric value.  Two patterns:
            - ``"result.json:summary.mean_ilisi"`` — dot-path into result.json
            - ``"tables/integration_metrics.csv"`` — CSV file; use *column*.
        column: Column name when *source* points to a CSV file.
        direction: ``"maximize"`` or ``"minimize"``.
        weight: Relative weight in the composite score (must be > 0).
        description: Human-readable explanation (shown to the LLM meta-agent).
    """

    source: str
    direction: str  # "maximize" | "minimize"
    weight: float = 1.0
    column: str | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if self.direction not in ("maximize", "minimize"):
            raise ValueError(
                f"direction must be 'maximize' or 'minimize', got {self.direction!r}"
            )
        if self.weight <= 0:
            raise ValueError(f"weight must be > 0, got {self.weight}")


# ---------------------------------------------------------------------------
# Common omics metric libraries
# ---------------------------------------------------------------------------

LISI_METRICS: dict[str, MetricDef] = {
    "mean_ilisi": MetricDef(
        source="result.json:summary.mean_ilisi",
        direction="maximize",
        weight=0.4,
        description="Integration LISI — higher means better batch mixing",
    ),
    "mean_clisi": MetricDef(
        source="result.json:summary.mean_clisi",
        direction="minimize",
        weight=0.3,
        description="Cell-type LISI — lower means better cell-type separation",
    ),
}

ASW_METRICS: dict[str, MetricDef] = {
    "batch_asw": MetricDef(
        source="result.json:summary.batch_asw",
        direction="minimize",
        weight=0.15,
        description="Batch ASW — closer to 0 means better batch mixing",
    ),
    "celltype_asw": MetricDef(
        source="result.json:summary.celltype_asw",
        direction="maximize",
        weight=0.15,
        description="Cell-type ASW — higher means better cell-type separation",
    ),
}

INTEGRATION_METRICS: dict[str, MetricDef] = {**LISI_METRICS, **ASW_METRICS}

BATCH_MIXING_METRICS: dict[str, MetricDef] = {
    "batch_mixing_after": MetricDef(
        source="result.json:summary.batch_mixing_after",
        direction="maximize",
        weight=0.7,
        description="Batch mixing entropy after integration",
    ),
    "batch_mixing_gain": MetricDef(
        source="result.json:summary.batch_mixing_gain",
        direction="maximize",
        weight=0.3,
        description="Improvement in batch mixing relative to pre-integration",
    ),
}

# DE metrics — only n_de_genes is the common key across spatial-de and bulkrna-de.
# spatial-de also has: n_significant, n_effect_size_hits, n_marker_hits
# bulkrna-de also has: n_up, n_down, frac_significant
# We use n_de_genes (present in both) as the primary metric.
SPATIAL_DE_METRICS: dict[str, MetricDef] = {
    "n_de_genes": MetricDef(
        source="result.json:summary.n_de_genes",
        direction="maximize",
        weight=0.4,
        description="Total DE gene entries detected",
    ),
    "n_significant": MetricDef(
        source="result.json:summary.n_significant",
        direction="maximize",
        weight=0.4,
        description="Genes passing adjusted p-value threshold",
    ),
    "n_marker_hits": MetricDef(
        source="result.json:summary.n_marker_hits",
        direction="maximize",
        weight=0.2,
        description="Genes passing both significance and effect-size thresholds",
    ),
}

BULKRNA_DE_METRICS: dict[str, MetricDef] = {
    "n_de_genes": MetricDef(
        source="result.json:summary.n_de_genes",
        direction="maximize",
        weight=0.5,
        description="Number of significant DE genes",
    ),
    "frac_significant": MetricDef(
        source="result.json:summary.frac_significant",
        direction="maximize",
        weight=0.5,
        description="Fraction of tested genes that are significant",
    ),
}

# sc-markers outputs n_markers and n_clusters, not n_de_genes
SC_MARKERS_METRICS: dict[str, MetricDef] = {
    "n_markers": MetricDef(
        source="result.json:summary.n_markers",
        direction="maximize",
        weight=0.6,
        description="Number of marker genes identified across all clusters",
    ),
    "n_clusters": MetricDef(
        source="result.json:summary.n_clusters",
        direction="maximize",
        weight=0.4,
        description="Number of clusters with markers found",
    ),
}

# Annotation metrics — sc-cell-annotation outputs n_cell_types;
# spatial-annotate scanvi/cellassign also output mean_confidence
ANNOTATION_CONFIDENCE_METRICS: dict[str, MetricDef] = {
    "n_cell_types": MetricDef(
        source="result.json:summary.n_cell_types",
        direction="maximize",
        weight=0.5,
        description="Number of distinct cell types annotated",
    ),
    "mean_confidence": MetricDef(
        source="result.json:summary.mean_confidence",
        direction="maximize",
        weight=0.5,
        description="Mean annotation confidence score (model-based methods only)",
    ),
}

# Deconvolution — no ground-truth quality metrics; use n_cell_types and n_common_genes
DECONVOLUTION_METRICS: dict[str, MetricDef] = {
    "n_cell_types": MetricDef(
        source="result.json:summary.n_cell_types",
        direction="maximize",
        weight=0.5,
        description="Number of cell types deconvolved",
    ),
    "n_common_genes": MetricDef(
        source="result.json:summary.n_common_genes",
        direction="maximize",
        weight=0.5,
        description="Genes shared between spatial and reference data",
    ),
}

SPATIAL_DOMAIN_METRICS: dict[str, MetricDef] = {
    "silhouette": MetricDef(
        source="result.json:summary.silhouette",
        direction="maximize",
        weight=0.4,
        description="Silhouette coefficient — higher means tighter, well-separated domains",
    ),
    "mean_local_purity": MetricDef(
        source="result.json:summary.mean_local_purity",
        direction="maximize",
        weight=0.4,
        description="Mean spatial neighbor purity — higher means more spatially coherent domains",
    ),
    "calinski_harabasz": MetricDef(
        source="result.json:summary.calinski_harabasz",
        direction="maximize",
        weight=0.2,
        description="Calinski-Harabasz index — higher means better-defined clusters",
    ),
}

# sc-clustering outputs n_clusters and cluster_counts only (unsupervised)
# NOTE: sc-clustering does NOT compute silhouette; if needed, add it
# to the skill script like we did for spatial-domains.
SC_CLUSTERING_METRICS: dict[str, MetricDef] = {
    "n_clusters": MetricDef(
        source="result.json:summary.n_clusters",
        direction="maximize",
        weight=1.0,
        description="Number of clusters identified",
    ),
}

COEXPRESSION_METRICS: dict[str, MetricDef] = {
    "n_modules": MetricDef(
        source="result.json:summary.n_modules",
        direction="maximize",
        weight=0.5,
        description="Number of co-expression modules detected",
    ),
    "soft_power": MetricDef(
        source="result.json:summary.soft_power",
        direction="maximize",
        weight=0.5,
        description="Soft-thresholding power selected for scale-free topology",
    ),
}

# ---------------------------------------------------------------------------
# Skill → Metrics mapping
# ---------------------------------------------------------------------------
# Key: (canonical_skill_alias, method).
#   - Use the canonical alias from the skill registry (typically the directory name).
#   - Use "*" as method to match all methods for that skill.
#   - Do NOT add duplicate entries for aliases — alias resolution in
#     get_metrics_for_skill() handles that automatically.
# Lookup priority: exact (skill, method) → wildcard (skill, "*") → alias-resolved.

SKILL_METRICS_MAP: dict[tuple[str, str], dict[str, MetricDef]] = {
    # Single-cell
    ("sc-batch-integration", "*"): INTEGRATION_METRICS,
    ("sc-cell-annotation", "*"): ANNOTATION_CONFIDENCE_METRICS,
    ("sc-clustering", "*"): SC_CLUSTERING_METRICS,
    ("sc-markers", "*"): SC_MARKERS_METRICS,
    # Spatial
    ("spatial-integrate", "*"): BATCH_MIXING_METRICS,
    ("spatial-annotate", "*"): ANNOTATION_CONFIDENCE_METRICS,
    ("spatial-deconv", "*"): DECONVOLUTION_METRICS,
    ("spatial-domains", "*"): SPATIAL_DOMAIN_METRICS,
    ("spatial-de", "*"): SPATIAL_DE_METRICS,
    # Bulk RNA-seq
    ("bulkrna-de", "*"): BULKRNA_DE_METRICS,
    ("bulkrna-coexpression", "*"): COEXPRESSION_METRICS,
}


def register_metrics(
    skill_name: str,
    metrics: dict[str, MetricDef],
    method: str = "*",
) -> None:
    """Register metrics for a skill at runtime.

    Use this to add metrics for new skills without modifying SKILL_METRICS_MAP
    source code.  The *skill_name* should be the canonical alias (directory name).
    """
    SKILL_METRICS_MAP[(skill_name, method)] = metrics


def get_metrics_for_skill(
    skill_name: str,
    method: str = "*",
) -> dict[str, MetricDef] | None:
    """Look up the metric definitions for a *skill* + *method* pair.

    Resolution order:
    1. Direct lookup with the given name
    2. Resolve alias via skill registry → lookup with canonical name

    Returns ``None`` if no metrics are registered for the given skill.
    """
    # Fast path: direct match
    result = (
        SKILL_METRICS_MAP.get((skill_name, method))
        or SKILL_METRICS_MAP.get((skill_name, "*"))
    )
    if result:
        return result

    # Resolve alias to canonical name and retry
    canonical = _canonicalize_skill_name(skill_name)
    if canonical and canonical != skill_name:
        return (
            SKILL_METRICS_MAP.get((canonical, method))
            or SKILL_METRICS_MAP.get((canonical, "*"))
        )

    return None


def list_optimizable_skills() -> list[dict[str, str]]:
    """Return canonical skills that have both metrics and optimizable methods."""
    try:
        from omicsclaw.core.registry import registry

        registry.load_all()
        primary_skills = registry.iter_primary_skills()
    except Exception:
        primary_skills = []

    result: list[dict[str, str]] = []
    if primary_skills:
        for skill, info in sorted(primary_skills, key=lambda item: item[0]):
            metrics = get_metrics_for_skill(skill)
            if not metrics or not _has_optimizable_methods(info.get("param_hints", {})):
                continue
            result.append({
                "skill": skill,
                "method_scope": "*",
                "metric_count": str(len(metrics)),
                "metrics": ", ".join(metrics.keys()),
            })
        return result

    seen: set[str] = set()
    for (skill, method), metrics in SKILL_METRICS_MAP.items():
        canonical_skill = _canonicalize_skill_name(skill)
        if canonical_skill in seen:
            continue
        seen.add(canonical_skill)
        result.append({
            "skill": canonical_skill,
            "method_scope": method,
            "metric_count": str(len(metrics)),
            "metrics": ", ".join(metrics.keys()),
        })
    return result


def _canonicalize_skill_name(skill_name: str) -> str:
    try:
        from omicsclaw.core.registry import registry

        registry.load_all()
        info = registry.skills.get(skill_name)
        if info is not None:
            return str(info.get("alias", skill_name))
    except Exception:
        pass
    return skill_name


def _has_optimizable_methods(param_hints: object) -> bool:
    if not isinstance(param_hints, dict):
        return False
    for hints in param_hints.values():
        if not isinstance(hints, dict):
            continue
        params = hints.get("params", [])
        if isinstance(params, list) and any(str(param).strip() for param in params):
            return True
    return False
