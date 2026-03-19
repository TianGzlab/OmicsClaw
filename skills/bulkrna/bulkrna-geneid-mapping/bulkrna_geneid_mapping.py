#!/usr/bin/env python3
"""bulkrna-geneid-mapping — Gene identifier conversion for bulk RNA-seq.

Converts gene identifiers in count matrices between Ensembl, Entrez,
HGNC symbols, and UniProt using built-in tables or mygene API.

Usage:
    python bulkrna_geneid_mapping.py --input counts.csv --from ensembl --to symbol --output results/
    python bulkrna_geneid_mapping.py --demo --output /tmp/geneid_demo
"""
from __future__ import annotations

import argparse
import json
import logging
import numpy as np
import pandas as pd
from pathlib import Path

import sys, os
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from omicsclaw.common.report import (
    generate_report_header,
    generate_report_footer,
    write_result_json,
)

logger = logging.getLogger(__name__)

SKILL_NAME = "bulkrna-geneid-mapping"
SKILL_VERSION = "0.3.0"

# Built-in demo mapping (small subset for demonstration)
_DEMO_MAPPING = {
    "ENSG00000141510": {"symbol": "TP53", "entrez": "7157"},
    "ENSG00000012048": {"symbol": "BRCA1", "entrez": "672"},
    "ENSG00000141736": {"symbol": "ERBB2", "entrez": "2064"},
    "ENSG00000171862": {"symbol": "PTEN", "entrez": "5728"},
    "ENSG00000157764": {"symbol": "BRAF", "entrez": "673"},
    "ENSG00000133703": {"symbol": "KRAS", "entrez": "3845"},
    "ENSG00000146648": {"symbol": "EGFR", "entrez": "1956"},
    "ENSG00000136997": {"symbol": "MYC", "entrez": "4609"},
    "ENSG00000105329": {"symbol": "TGFB1", "entrez": "7040"},
    "ENSG00000164690": {"symbol": "SHH", "entrez": "6469"},
}


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

def _generate_demo_data() -> pd.DataFrame:
    """Generate a small count matrix with Ensembl IDs."""
    np.random.seed(42)
    genes = list(_DEMO_MAPPING.keys()) + [f"ENSG{i:011d}" for i in range(200, 250)]
    samples = [f"sample_{i}" for i in range(1, 7)]
    counts = np.random.negative_binomial(5, 0.3, size=(len(genes), len(samples)))
    return pd.DataFrame(counts, index=genes, columns=samples)


def get_demo_data() -> tuple[pd.DataFrame, Path]:
    """Load or generate demo data."""
    project_root = Path(__file__).resolve().parents[3]
    demo_path = project_root / "examples" / "demo_bulkrna_ensembl_counts.csv"
    if demo_path.exists():
        return pd.read_csv(demo_path, index_col=0), demo_path
    df = _generate_demo_data()
    demo_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(demo_path)
    return df, demo_path


# ---------------------------------------------------------------------------
# Mapping logic
# ---------------------------------------------------------------------------

def _strip_version(gene_id: str) -> str:
    """Remove Ensembl version suffix: ENSG00000141510.12 -> ENSG00000141510."""
    return gene_id.split(".")[0] if gene_id.startswith("ENS") else gene_id


def _try_mygene_mapping(gene_ids: list[str], from_type: str, to_type: str,
                        species: str = "human") -> dict[str, str]:
    """Attempt mapping via mygene API (optional dependency)."""
    try:
        import mygene
    except ImportError:
        logger.warning("mygene not installed — skipping API-based mapping")
        return {}

    scope_map = {"ensembl": "ensembl.gene", "entrez": "entrezgene", "symbol": "symbol"}
    field_map = {"ensembl": "ensembl.gene", "entrez": "entrezgene", "symbol": "symbol"}

    mg = mygene.MyGeneInfo()
    results = mg.querymany(gene_ids, scopes=scope_map.get(from_type, from_type),
                           fields=field_map.get(to_type, to_type),
                           species=species, verbose=False)
    mapping: dict[str, str] = {}
    for r in results:
        if to_type == "symbol" and "symbol" in r:
            mapping[r["query"]] = r["symbol"]
        elif to_type == "entrez" and "entrezgene" in r:
            mapping[r["query"]] = str(r["entrezgene"])
        elif to_type == "ensembl" and "ensembl" in r:
            ens = r["ensembl"]
            if isinstance(ens, list):
                mapping[r["query"]] = ens[0].get("gene", r["query"])
            elif isinstance(ens, dict):
                mapping[r["query"]] = ens.get("gene", r["query"])
    return mapping


def map_gene_ids(counts: pd.DataFrame, from_type: str, to_type: str,
                 species: str = "human", on_duplicate: str = "sum",
                 custom_mapping: dict[str, str] | None = None) -> tuple[pd.DataFrame, dict]:
    """Map gene IDs in a count matrix.

    Returns: (mapped_counts, summary_dict)
    """
    original_genes = list(counts.index)
    n_original = len(original_genes)

    # Step 1: Strip version suffixes
    stripped = [_strip_version(g) for g in original_genes]
    counts_work = counts.copy()
    counts_work.index = stripped

    # Step 2: Build mapping
    mapping: dict[str, str] = {}

    # Use custom mapping if provided
    if custom_mapping:
        mapping.update(custom_mapping)

    # Built-in mapping (for demo / small sets)
    if from_type == "ensembl":
        for ens_id, info in _DEMO_MAPPING.items():
            if to_type in info:
                mapping[ens_id] = info[to_type]

    # Attempt mygene for unmapped
    unmapped = [g for g in stripped if g not in mapping]
    if unmapped:
        api_mapping = _try_mygene_mapping(unmapped, from_type, to_type, species)
        mapping.update(api_mapping)

    # Step 3: Apply mapping
    new_index = [mapping.get(g, g) for g in stripped]
    mapped_mask = [g in mapping for g in stripped]
    n_mapped = sum(mapped_mask)
    n_unmapped = n_original - n_mapped

    counts_mapped = counts_work.copy()
    counts_mapped.index = new_index

    # Step 4: Handle duplicates
    n_duplicates = len(new_index) - len(set(new_index))
    if n_duplicates > 0:
        if on_duplicate == "sum":
            counts_mapped = counts_mapped.groupby(counts_mapped.index).sum()
        elif on_duplicate == "first":
            counts_mapped = counts_mapped[~counts_mapped.index.duplicated(keep="first")]
        elif on_duplicate == "drop":
            dup_ids = counts_mapped.index[counts_mapped.index.duplicated(keep=False)]
            counts_mapped = counts_mapped[~counts_mapped.index.isin(dup_ids)]

    # Build mapping table for export
    mapping_records = []
    for orig, stripped_id, new_id in zip(original_genes, stripped, new_index):
        mapping_records.append({
            "original_id": orig,
            "stripped_id": stripped_id,
            "mapped_id": new_id,
            "was_mapped": stripped_id in mapping,
        })
    mapping_df = pd.DataFrame(mapping_records)

    unmapped_genes = [orig for orig, s in zip(original_genes, stripped) if s not in mapping]

    summary = {
        "n_original_genes": n_original,
        "n_mapped": n_mapped,
        "n_unmapped": n_unmapped,
        "pct_mapped": round(100.0 * n_mapped / max(n_original, 1), 2),
        "n_duplicates_resolved": n_duplicates,
        "duplicate_strategy": on_duplicate,
        "n_final_genes": counts_mapped.shape[0],
        "from_type": from_type,
        "to_type": to_type,
        "species": species,
    }
    return counts_mapped, {
        "summary": summary,
        "mapping_df": mapping_df,
        "unmapped_genes": unmapped_genes,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(output_dir: Path, result: dict, params: dict,
                 mapped_counts: pd.DataFrame) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    summary = result["summary"]
    header = generate_report_header(
        title="Bulk RNA-seq Gene ID Mapping Report",
        skill_name=SKILL_NAME,
    )

    body_lines = [
        "## Summary\n",
        f"- **Source ID type**: {summary['from_type']}",
        f"- **Target ID type**: {summary['to_type']}",
        f"- **Species**: {summary['species']}",
        f"- **Original genes**: {summary['n_original_genes']}",
        f"- **Successfully mapped**: {summary['n_mapped']} ({summary['pct_mapped']:.1f}%)",
        f"- **Unmapped (kept original)**: {summary['n_unmapped']}",
        f"- **Duplicates resolved** ({summary['duplicate_strategy']}): {summary['n_duplicates_resolved']}",
        f"- **Final gene count**: {summary['n_final_genes']}",
        "",
    ]
    if result["unmapped_genes"]:
        body_lines.append("## Unmapped Genes (first 20)\n")
        for g in result["unmapped_genes"][:20]:
            body_lines.append(f"- `{g}`")
        if len(result["unmapped_genes"]) > 20:
            body_lines.append(f"- ... and {len(result['unmapped_genes']) - 20} more")
        body_lines.append("")

    footer = generate_report_footer()
    report_text = "\n".join([header, "\n".join(body_lines), footer])
    (output_dir / "report.md").write_text(report_text, encoding="utf-8")

    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, params)

    mapped_counts.to_csv(tables_dir / "mapped_counts.csv")
    result["mapping_df"].to_csv(tables_dir / "mapping_table.csv", index=False)
    if result["unmapped_genes"]:
        pd.DataFrame({"unmapped_gene": result["unmapped_genes"]}).to_csv(
            tables_dir / "unmapped_genes.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    script = f"""#!/usr/bin/env bash
# Reproducibility script for {SKILL_NAME} v{SKILL_VERSION}
python bulkrna_geneid_mapping.py \\
    --input {params.get('input', '<INPUT>')} \\
    --from {params.get('from_type', 'ensembl')} \\
    --to {params.get('to_type', 'symbol')} \\
    --species {params.get('species', 'human')} \\
    --output {params.get('output', '<OUTPUT>')}
"""
    (repro_dir / "commands.sh").write_text(script, encoding="utf-8")
    logger.info("Report written to %s", output_dir / "report.md")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    ap = argparse.ArgumentParser(description=f"{SKILL_NAME} v{SKILL_VERSION}")
    ap.add_argument("--input", type=str, help="Count matrix CSV")
    ap.add_argument("--from", dest="from_type", default="ensembl",
                    choices=["ensembl", "entrez", "symbol"])
    ap.add_argument("--to", dest="to_type", default="symbol",
                    choices=["ensembl", "entrez", "symbol"])
    ap.add_argument("--species", default="human", choices=["human", "mouse"])
    ap.add_argument("--on-duplicate", default="sum", choices=["sum", "first", "drop"])
    ap.add_argument("--mapping-file", type=str, help="Custom mapping TSV")
    ap.add_argument("--output", type=str, required=True)
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    output_dir = Path(args.output)

    if args.demo:
        counts, input_path = get_demo_data()
    else:
        if not args.input:
            ap.error("--input is required (or use --demo)")
        counts = pd.read_csv(args.input, index_col=0)
        input_path = Path(args.input)

    custom_mapping = None
    if args.mapping_file:
        mf = pd.read_csv(args.mapping_file, sep="\t")
        custom_mapping = dict(zip(mf.iloc[:, 0], mf.iloc[:, 1]))

    mapped_counts, result = map_gene_ids(
        counts, args.from_type, args.to_type, args.species,
        args.on_duplicate, custom_mapping)

    params = {
        "input": str(input_path),
        "from_type": args.from_type,
        "to_type": args.to_type,
        "species": args.species,
        "on_duplicate": args.on_duplicate,
        "output": str(output_dir),
    }

    write_report(output_dir, result, params, mapped_counts)
    logger.info("✓ Gene ID mapping complete → %s", output_dir)


if __name__ == "__main__":
    main()
