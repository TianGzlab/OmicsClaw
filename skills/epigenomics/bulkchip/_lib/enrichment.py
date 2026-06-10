"""
enrichment.py — Bulk ChIP-seq functional (GO/KEGG) over-representation.

Standalone enrichment library for the ``bulkchip-enrichment`` skill. Consumes
the target-gene set produced by ``bulkchip-peak-annotation`` and runs GO / KEGG
over-representation (ORA) via ``gseapy.enrichr``. Peak→gene annotation is a
SEPARATE skill — this module never annotates peaks, it only enriches a gene
list.

Design contract
---------------
  * ``run_functional_enrichment`` returns one ``EnrichmentResult`` per requested
    gene-set library (``gene_set``, ``results_csv``, ``dotplot_png``, ``n_terms``).
  * MUST degrade gracefully and NEVER crash the skill: if ``gseapy`` is not
    importable, the Enrichr network call fails, or the gene list is empty, it
    logs a warning and returns an ``EnrichmentResult`` with ``n_terms=0`` and a
    header-only CSV.
  * All heavy imports (gseapy / pandas / matplotlib) are LAZY (inside the
    function) so this module imports cleanly in the base dev env.

References
----------
  gseapy / Enrichr : https://github.com/zqfang/GSEApy
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EnrichmentResult:
    """Output of run_functional_enrichment() for one gene set."""
    gene_set:      str                     # "GO_Biological_Process" | "KEGG" | ...
    results_csv:   Path                     # term, overlap, padj, genes
    dotplot_png:   Path | None = None
    n_terms:       int = 0
    top_term:      str | None = None        # most-significant term label
    top_padj:      float | None = None       # its adjusted p-value

logger = logging.getLogger(__name__)

# Column header shared by every results CSV (term, overlap, padj, genes).
_CSV_HEADER = ["term", "overlap", "adjusted_p_value", "p_value", "combined_score", "genes"]

# Friendly names → Enrichr library candidates (tried in order). Unknown names
# are passed straight through to gseapy.
_LIBRARY_CANDIDATES: dict[str, tuple[str, ...]] = {
    "GO_Biological_Process": ("GO_Biological_Process_2021", "GO_Biological_Process_2023"),
    "GO_Molecular_Function": ("GO_Molecular_Function_2021", "GO_Molecular_Function_2023"),
    "GO_Cellular_Component": ("GO_Cellular_Component_2021", "GO_Cellular_Component_2023"),
    "KEGG": ("KEGG_2021_Human", "KEGG_2019_Mouse", "KEGG_2019"),
    "KEGG_Pathways": ("KEGG_2021_Human",),
    "Reactome": ("Reactome_2022", "Reactome_Pathways_2024"),
    "MSigDB_Hallmark": ("MSigDB_Hallmark_2020",),
}


def _slug(text: str) -> str:
    """Filesystem-safe slug for a gene-set library name."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(text)).strip("_")[:80]


def _write_header_only_csv(path: Path) -> None:
    """Write a results CSV containing only the standard header (no rows)."""
    with path.open("w", newline="") as handle:
        csv.writer(handle).writerow(_CSV_HEADER)


def _load_gmt(path: Path) -> dict[str, list[str]]:
    """Load an offline GMT gene-set file: term -> gene list."""
    gene_sets: dict[str, list[str]] = {}
    with Path(path).open() as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            genes = [g for g in parts[2:] if g]
            if genes:
                gene_sets[parts[0]] = genes
    return gene_sets


def _resolve_gene_sets(name: str, gmt: Path | None) -> object:
    """Return the gene_sets argument handed to gseapy.enrichr for one library.

    With an offline ``gmt``, return the parsed mapping (gseapy accepts a dict).
    Otherwise return the resolved Enrichr library name (best candidate first;
    gseapy itself tries the name as given if our alias misses).
    """
    if gmt is not None:
        return _load_gmt(gmt)
    candidates = _LIBRARY_CANDIDATES.get(name, (name,))
    return candidates[0]


def run_functional_enrichment(
    gene_list,
    output_dir,
    *,
    gene_sets,
    organism: str = "human",
    gmt=None,
    padj_cutoff: float = 0.05,
) -> list[EnrichmentResult]:
    """Run GO / KEGG over-representation on a ChIP target-gene set.

    For each library name in ``gene_sets`` run ``gseapy.enrichr`` and write one
    results CSV (term, overlap, adjusted p-value, genes) plus a dotplot PNG,
    returning one ``EnrichmentResult`` per library.

    Degrades gracefully: gseapy missing, network failure, or an empty gene list
    → a warning is logged and an ``EnrichmentResult`` with ``n_terms=0`` and a
    header-only CSV is returned (the skill never crashes).

    Args:
        gene_list: target genes from bulkchip-peak-annotation.
        output_dir: directory for ``<library>.csv`` / ``<library>_dotplot.png``.
        gene_sets: list of Enrichr library names (e.g. ``["GO_Biological_Process",
            "KEGG"]``).
        organism: gseapy organism (``human`` / ``mouse`` / ``yeast`` / ...).
        gmt: optional offline ``.gmt`` path used for every library.
        padj_cutoff: adjusted-p-value cutoff for the dotplot / term count.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    gene_list = [str(g) for g in (gene_list or []) if str(g)]
    # De-duplicate while keeping order.
    seen: set[str] = set()
    gene_list = [g for g in gene_list if not (g in seen or seen.add(g))]

    gmt_path = Path(gmt) if gmt else None
    results: list[EnrichmentResult] = []

    if not gene_list:
        logger.warning(
            "bulkchip-enrichment: empty target-gene set — writing empty enrichment "
            "results (n_terms=0) for each requested library."
        )
        for name in gene_sets:
            csv_path = out_dir / f"{_slug(name)}.csv"
            _write_header_only_csv(csv_path)
            results.append(EnrichmentResult(gene_set=str(name), results_csv=csv_path,
                                            dotplot_png=None, n_terms=0))
        return results

    # Lazy heavy imports — keep the module importable in the base env.
    try:
        import gseapy as gp  # noqa: F401
    except Exception as exc:  # ImportError or any transitive failure
        logger.warning(
            "bulkchip-enrichment: gseapy unavailable (%s) — returning empty "
            "enrichment results. Install gseapy in the bulkchip env to enable GO/KEGG.",
            exc,
        )
        for name in gene_sets:
            csv_path = out_dir / f"{_slug(name)}.csv"
            _write_header_only_csv(csv_path)
            results.append(EnrichmentResult(gene_set=str(name), results_csv=csv_path,
                                            dotplot_png=None, n_terms=0))
        return results

    import pandas as pd

    for name in gene_sets:
        slug = _slug(name)
        csv_path = out_dir / f"{slug}.csv"
        dotplot_path = out_dir / f"{slug}_dotplot.png"
        resolved = _resolve_gene_sets(str(name), gmt_path)

        try:
            enr = gp.enrichr(
                gene_list=gene_list,
                gene_sets=resolved,
                organism=organism,
                outdir=str(out_dir / f"_enrichr_{slug}"),
                no_plot=True,
            )
            res = enr.results.copy() if hasattr(enr, "results") and enr.results is not None else pd.DataFrame()
        except Exception as exc:
            logger.warning(
                "bulkchip-enrichment: Enrichr call failed for library '%s' (%s) — "
                "writing empty results for this library.",
                name, exc,
            )
            _write_header_only_csv(csv_path)
            results.append(EnrichmentResult(gene_set=str(name), results_csv=csv_path,
                                            dotplot_png=None, n_terms=0))
            continue

        if res is None or res.empty:
            logger.warning("bulkchip-enrichment: library '%s' returned no terms.", name)
            _write_header_only_csv(csv_path)
            results.append(EnrichmentResult(gene_set=str(name), results_csv=csv_path,
                                            dotplot_png=None, n_terms=0))
            continue

        # Normalize to the standard CSV contract.
        std = pd.DataFrame({
            "term": res.get("Term", pd.Series(dtype=str)),
            "overlap": res.get("Overlap", pd.Series(dtype=str)),
            "adjusted_p_value": pd.to_numeric(res.get("Adjusted P-value"), errors="coerce"),
            "p_value": pd.to_numeric(res.get("P-value"), errors="coerce"),
            "combined_score": pd.to_numeric(res.get("Combined Score"), errors="coerce"),
            "genes": res.get("Genes", pd.Series(dtype=str)),
        })
        std = std.sort_values("adjusted_p_value", ascending=True, na_position="last").reset_index(drop=True)
        std.to_csv(csv_path, index=False)

        sig = std[std["adjusted_p_value"].fillna(1.0) <= float(padj_cutoff)]
        n_terms = int(len(sig))

        dotplot_out: Path | None = None
        top_term: str | None = None
        top_padj: float | None = None
        if n_terms > 0:
            dotplot_out = _make_dotplot(sig, dotplot_path, title=str(name))
            top_row = sig.iloc[0]
            top_term = str(top_row["term"])
            top_padj = float(top_row["adjusted_p_value"]) if pd.notna(top_row["adjusted_p_value"]) else None

        results.append(EnrichmentResult(
            gene_set=str(name), results_csv=csv_path,
            dotplot_png=dotplot_out, n_terms=n_terms,
            top_term=top_term, top_padj=top_padj,
        ))

    return results


def _make_dotplot(sig_df, dotplot_path: Path, *, title: str, top_n: int = 15):
    """Render a top-terms dotplot (-log10 padj vs gene count). Lazy matplotlib."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception as exc:
        logger.warning("bulkchip-enrichment: matplotlib unavailable (%s) — skipping dotplot.", exc)
        return None

    try:
        top = sig_df.head(int(top_n)).iloc[::-1].reset_index(drop=True)
        # Gene count = numerator of "k/K" overlap string.
        counts = []
        for ov in top["overlap"].astype(str):
            try:
                counts.append(int(ov.split("/")[0]))
            except (ValueError, IndexError):
                counts.append(1)
        neglog = -np.log10(top["adjusted_p_value"].fillna(1.0).clip(lower=1e-300).to_numpy())
        labels = [t if len(t) <= 50 else t[:47] + "..." for t in top["term"].astype(str)]

        fig, ax = plt.subplots(figsize=(8, max(3, 0.4 * len(top) + 1)))
        sizes = [20 + 25 * c for c in counts]
        sc = ax.scatter(neglog, range(len(top)), s=sizes, c=neglog, cmap="viridis")
        ax.set_yticks(range(len(top)))
        ax.set_yticklabels(labels, fontsize=8)
        ax.set_xlabel("-log10(adjusted p-value)")
        ax.set_title(f"{title} — top enriched terms")
        fig.colorbar(sc, ax=ax, label="-log10(padj)")
        fig.tight_layout()
        fig.savefig(dotplot_path, dpi=150)
        plt.close(fig)
        return dotplot_path
    except Exception as exc:
        logger.warning("bulkchip-enrichment: dotplot rendering failed (%s) — skipping.", exc)
        return None


def write_enrichment_summary(results: list[EnrichmentResult], output_dir) -> Path:
    """Write enrichment_summary.csv: one row per gene-set library."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "enrichment_summary.csv"
    with summary_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["gene_set", "n_significant_terms", "results_csv", "dotplot_png"])
        for r in results:
            writer.writerow([
                r.gene_set,
                r.n_terms,
                str(r.results_csv),
                str(r.dotplot_png) if r.dotplot_png else "",
            ])
    return summary_path
