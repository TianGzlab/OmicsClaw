"""
Main enrichment workflow orchestrator for ChIP-Atlas peak enrichment.

Uses the official ChIP-Atlas Enrichment Analysis API (Fisher's exact test
with Benjamini-Hochberg Q-values) to analyze gene lists against all public
ChIP-seq experiments.

API: POST https://dtn1.ddbj.nig.ac.jp/wabi/chipatlas/
Reference: Zou et al. 2024 (NAR), https://chip-atlas.org
"""

import os
import time
import pandas as pd

try:
    from scripts.query_chipatlas_api import (
        submit_enrichment_job,
        poll_job_status,
        retrieve_results,
        parse_api_results,
    )
    from scripts.filter_experiments import filter_experiments
    from scripts.convert_genes_to_regions import convert_genes_to_regions
except ImportError:
    from query_chipatlas_api import (
        submit_enrichment_job,
        poll_job_status,
        retrieve_results,
        parse_api_results,
    )
    from filter_experiments import filter_experiments
    from convert_genes_to_regions import convert_genes_to_regions


# Map legacy peak_threshold values to API threshold
_LEGACY_THRESHOLD_MAP = {
    "05": 50,
    "10": 100,
    "20": 200,
}


def run_enrichment_workflow(
    gene_list,
    genome="hg38",
    antigen_class="TFs and others",
    cell_class="All cell types",
    threshold=50,
    distance_up=5000,
    distance_down=5000,
    antigen_filter=None,
    cell_type_filter=None,
    min_fold_enrichment=1.0,
    max_qvalue=None,
    output_dir="chipatlas_results",
    # Legacy parameters (auto-mapped)
    upstream=None,
    downstream=None,
    peak_threshold=None,
    max_experiments=None,
    force_refresh_metadata=None,
):
    """
    Run complete ChIP-Atlas enrichment analysis via the official API.

    Parameters:
    -----------
    gene_list : list of str
        Gene symbols to analyze (e.g., ['TP53', 'CDKN1A', 'BAX'])
    genome : str
        Genome assembly (hg38, hg19, mm10, mm9, rn6, dm6, dm3, ce11, ce10, sacCer3)
    antigen_class : str
        Experiment type ("TFs and others", "Histone", "ATAC-Seq", etc.)
    cell_class : str
        Cell type class ("All cell types", "Blood", "Neural", etc.)
    threshold : int
        MACS2 peak threshold: 50 (1e-5), 100 (1e-10), 200 (1e-20), 500 (1e-50)
    distance_up : int
        Bases upstream of TSS (default: 5000)
    distance_down : int
        Bases downstream of TSS (default: 5000)
    antigen_filter : list of str or None
        Post-API filter: specific antigens to keep
    cell_type_filter : list of str or None
        Post-API filter: specific cell types to keep
    min_fold_enrichment : float
        Post-API filter: minimum fold enrichment
    max_qvalue : float or None
        Post-API filter: maximum Q-value
    output_dir : str
        Output directory for results

    Legacy Parameters (auto-mapped):
    ---------------------------------
    upstream : int or None -> maps to distance_up
    downstream : int or None -> maps to distance_down
    peak_threshold : str or None -> maps to threshold ("05"->50, "10"->100, "20"->200)
    max_experiments : ignored (API searches all experiments)
    force_refresh_metadata : ignored (no local metadata)

    Returns:
    --------
    dict: Complete results dictionary with:
        - enrichment_results: pd.DataFrame (experiment_id, antigen, cell_type,
          fold_enrichment, p_value, q_value, significant, overlap_rate,
          regions_with_overlaps, total_regions, total_peaks)
        - input_genes: list of original gene symbols
        - input_regions: list of promoter regions (chr, start, end, gene, strand)
        - failed_genes: list (empty for API workflow)
        - metadata: pd.DataFrame (same as enrichment_results)
        - parameters: dict of analysis parameters

    Verification:
    -------------
    Prints "✓ Enrichment analysis completed successfully!" when done
    """

    # Handle legacy parameters
    if upstream is not None:
        distance_up = upstream
    if downstream is not None:
        distance_down = downstream
    if peak_threshold is not None:
        threshold = _LEGACY_THRESHOLD_MAP.get(peak_threshold, threshold)
    if max_experiments is not None:
        print(f"   Note: max_experiments is ignored (API searches all experiments)")

    # Validate inputs
    if not gene_list or len(gene_list) == 0:
        raise ValueError("gene_list must contain at least one gene symbol")

    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "=" * 70)
    print("CHIP-ATLAS PEAK ENRICHMENT WORKFLOW (API)")
    print("=" * 70 + "\n")

    # Step 1: Submit to ChIP-Atlas API
    print("Step 1: Submitting gene list to ChIP-Atlas Enrichment Analysis API...")
    print(f"   Genome: {genome}")
    print(f"   Genes: {len(gene_list)} ({', '.join(gene_list[:5])}{'...' if len(gene_list) > 5 else ''})")
    print(f"   Antigen class: {antigen_class}")
    print(f"   Cell class: {cell_class}")
    print(f"   Threshold: {threshold} (MACS2 -10*log10(p))")
    print(f"   TSS window: {distance_up}bp upstream, {distance_down}bp downstream")

    request_id = submit_enrichment_job(
        gene_list=gene_list,
        genome=genome,
        antigen_class=antigen_class,
        cell_class=cell_class,
        threshold=threshold,
        distance_up=distance_up,
        distance_down=distance_down,
    )

    print(f"   Request ID: {request_id}")
    print(f"✓ Job submitted successfully")

    # Step 2: Poll for completion
    print("\nStep 2: Waiting for analysis to complete...")
    print(f"   (Typically 1-3 minutes for gene list enrichment)")

    status = poll_job_status(request_id, timeout=600, poll_interval=15)
    print(f"✓ Job completed (status: {status})")

    # Step 3: Retrieve and parse results
    print("\nStep 3: Retrieving results...")

    raw_df = retrieve_results(request_id)
    print(f"   Retrieved {len(raw_df)} experiment results")

    results_df = parse_api_results(raw_df, len(gene_list))
    print(f"✓ Parsed {len(results_df)} experiments")

    # Check for gene discrepancy: API may drop genes it cannot resolve
    api_total_regions = int(results_df['total_regions'].iloc[0]) if len(results_df) > 0 else len(gene_list)
    if api_total_regions != len(gene_list):
        print(f"\n   ⚠️  API analyzed {api_total_regions} regions but {len(gene_list)} genes were submitted.")
        print(f"   {len(gene_list) - api_total_regions} gene(s) may have been dropped "
              f"(unrecognized symbol, not in RefSeq, or duplicate promoter region).")

    # Step 4: Apply post-API filters
    if antigen_filter or cell_type_filter or min_fold_enrichment > 1.0 or max_qvalue:
        print("\nStep 4: Applying filters...")
        results_df = filter_experiments(
            results_df,
            antigen_filter=antigen_filter,
            cell_type_filter=cell_type_filter,
            min_fold_enrichment=min_fold_enrichment,
            max_qvalue=max_qvalue,
        )
        print(f"✓ Filtered to {len(results_df)} experiments")
    else:
        print("\nStep 4: No additional filters applied")

    # Step 5: Populate input_regions via Ensembl (optional, non-blocking)
    print("\nStep 5: Looking up gene coordinates via Ensembl...")
    input_regions = []
    failed_genes = []
    try:
        input_regions, failed_genes = convert_genes_to_regions(
            gene_list=gene_list,
            genome=genome,
            upstream=distance_up,
            downstream=distance_down,
        )
        print(f"✓ Mapped {len(input_regions)}/{len(gene_list)} genes to regions")
    except Exception as e:
        print(f"   Warning: Ensembl lookup failed ({e}), continuing without regions")
        input_regions = []
        failed_genes = []

    # Retry once if all genes failed (Ensembl may have been temporarily unavailable)
    if len(input_regions) == 0 and len(gene_list) > 0:
        print(f"\n   Ensembl lookup returned 0 regions. Retrying in 60 seconds...")
        time.sleep(60)
        try:
            input_regions, failed_genes = convert_genes_to_regions(
                gene_list=gene_list,
                genome=genome,
                upstream=distance_up,
                downstream=distance_down,
            )
            print(f"✓ Retry mapped {len(input_regions)}/{len(gene_list)} genes to regions")
        except Exception as e:
            print(f"   Retry also failed ({e}), continuing without Ensembl regions")
            input_regions = []
            failed_genes = []

    if failed_genes:
        print(f"\n   ⚠️  WARNING: {len(failed_genes)} gene(s) failed Ensembl lookup: {', '.join(failed_genes)}")
        print(f"   These genes may use retired symbols. Check HGNC (genenames.org) for current names.")
        print(f"   Common renames: IL8→CXCL8, TNFSF6→FASLG, MLL→KMT2A, RANTES→CCL5")

    # Summary
    n_significant = (results_df["q_value"] < 0.05).sum() if len(results_df) > 0 else 0

    print(f"\n   Total experiments: {len(results_df)}")
    print(f"   Significant (q < 0.05, BH-corrected): {n_significant}")

    if len(results_df) > 0:
        top = results_df.iloc[0]
        print(
            f"   Top factor: {top['antigen']} "
            f"(q={top['q_value']:.2e}, "
            f"fold: {top['fold_enrichment']:.1f}x)"
        )

    print("\n✓ Enrichment analysis completed successfully!")
    print("=" * 70 + "\n")

    return {
        "enrichment_results": results_df,
        "input_genes": gene_list,
        "input_regions": input_regions,
        "failed_genes": failed_genes,
        "metadata": results_df,
        "api_total_regions": api_total_regions,
        "parameters": {
            "genome": genome,
            "antigen_class": antigen_class,
            "cell_class": cell_class,
            "threshold": threshold,
            "distance_up": distance_up,
            "distance_down": distance_down,
            "antigen_filter": antigen_filter,
            "cell_type_filter": cell_type_filter,
        },
    }

