"""
annotation_enrichment.py — Bulk ChIP-seq Step 5b: peak→gene genomic annotation
and functional (GO/KEGG) enrichment of target genes.

SCAFFOLD MODULE — data contracts + signatures defined; tool-backed bodies raise
``NotImplementedError`` (apply references/methodology.md).

This is the ChIP-relevant downstream that replaces ATAC's TOBIAS footprinting:
  * Genomic annotation — assign each peak to a genomic feature (promoter-TSS,
    exon, intron, intergenic, ...) and its nearest gene, via HOMER
    ``annotatePeaks.pl`` (or a GTF ``bedtools closest`` fallback). Produces the
    feature-distribution pie + TSS-distance distribution.
  * Functional enrichment — take the target-gene set (peaks within a TSS window)
    and run GO / KEGG over-representation with ``gseapy.enrichr`` (offline gene
    sets supported), reporting enriched terms with adjusted p-values.

Input: a peak BED/narrowPeak (consensus, per-condition, or DA up/down subset).
Planned tools: HOMER (annotatePeaks.pl) / bedtools, gseapy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SCAFFOLD = "bulkchip-annotation-enrichment is a scaffold — implement per references/methodology.md"


# ===========================================================================
# Data contracts
# ===========================================================================

@dataclass
class AnnotationResult:
    """Output of annotate_peaks() for one peak set."""
    annotated_tsv:    Path                 # per-peak feature + nearest gene
    feature_counts:   dict[str, int] = field(default_factory=dict)  # feature → n
    target_genes:     list[str] = field(default_factory=list)       # within TSS window
    pie_png:          Path | None = None
    tss_dist_png:     Path | None = None


@dataclass
class EnrichmentResult:
    """Output of run_functional_enrichment() for one gene set."""
    gene_set:      str                     # "GO_Biological_Process" | "KEGG" | ...
    results_csv:   Path                     # term, overlap, padj, genes
    dotplot_png:   Path | None = None
    n_terms:       int = 0


# ===========================================================================
# Public API (scaffold)
# ===========================================================================

def annotate_peaks(*args: Any, **kwargs: Any) -> AnnotationResult:
    """HOMER annotatePeaks.pl (or GTF bedtools-closest) → feature + nearest gene."""
    raise NotImplementedError(_SCAFFOLD)


def run_functional_enrichment(*args: Any, **kwargs: Any) -> list[EnrichmentResult]:
    """GO / KEGG over-representation on the target-gene set (gseapy.enrichr)."""
    raise NotImplementedError(_SCAFFOLD)


def write_annotation_summary(*args: Any, **kwargs: Any) -> Path:
    """Write annotation_enrichment_summary.csv (feature distribution + top terms)."""
    raise NotImplementedError(_SCAFFOLD)
