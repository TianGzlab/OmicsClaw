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
from skills.bulkrna._lib.geneid import _generate_demo_data

logger = logging.getLogger(__name__)

SKILL_NAME = "bulkrna-geneid-mapping"
SKILL_VERSION = "0.3.0"

# Built-in demo mapping (small subset for demonstration)


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------



def get_demo_data() -> tuple[pd.DataFrame, Path]:
    """Load or generate demo data."""
    project_root = Path(__file__).resolve().parents[3]
    demo_path = project_root / "examples" / "demo_bulkrna_ensembl_counts.csv"
    if demo_path.exists():
        return pd.read_csv(demo_path, index_col=0), demo_path
    df = _generate_demo_data()
    return df, Path('built-in-demo')


# ---------------------------------------------------------------------------
# Mapping logic
# ---------------------------------------------------------------------------







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
    ap.add_argument("--fetch-mygene", action="store_true", help="Explicitly query MyGene for mappings")
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
        custom_mapping = mf.iloc[:, :2].copy()
        custom_mapping.columns = ["source", "target"]

    library = load_skill(SKILL_NAME)
    if args.fetch_mygene:
        fetched = library.fetch_mapping(list(counts.index), from_type=args.from_type, to_type=args.to_type, species=args.species)
        custom_mapping = fetched if custom_mapping is None else pd.concat([custom_mapping, fetched]).drop_duplicates('source', keep='first')
    mapped_counts = library.map_ids(counts, from_type=args.from_type, to_type=args.to_type, species=args.species,
                                    on_duplicate=args.on_duplicate, mapping=custom_mapping)
    mapping_df = library.mapping_table(mapped_counts)
    info = library.run_info(mapped_counts, keep=False)
    result = {'summary': info['summary'], 'mapping_df': mapping_df,
              'unmapped_genes': mapping_df.loc[~mapping_df.was_mapped, 'original_id'].tolist()}

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
