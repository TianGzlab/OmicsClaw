"""Local identifier mapping and the optional MyGene query adapter."""
import logging
import numpy as np
import pandas as pd
logger = logging.getLogger(__name__)

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

def _generate_demo_data() -> pd.DataFrame:
    """Generate a small count matrix with Ensembl IDs."""
    rng = np.random.RandomState(42)
    genes = list(_DEMO_MAPPING.keys()) + [f"ENSG{i:011d}" for i in range(200, 250)]
    samples = [f"sample_{i}" for i in range(1, 7)]
    counts = rng.negative_binomial(5, 0.3, size=(len(genes), len(samples)))
    return pd.DataFrame(counts, index=genes, columns=samples)

def _strip_version(gene_id: str) -> str:
    """Remove Ensembl version suffix: ENSG00000141510.12 -> ENSG00000141510."""
    return gene_id.split(".")[0] if gene_id.startswith("ENS") else gene_id

def _try_mygene_mapping(gene_ids: list[str], from_type: str, to_type: str,
                        species: str = "human") -> dict[str, str]:
    """Attempt mapping via mygene API (optional dependency)."""
    try:
        import mygene
    except ImportError:
        raise ImportError("Install mygene with install_skill_deps for fetch_mapping")

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
